#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for Identity Platform Hook Service."""

import logging
from functools import cached_property
from secrets import token_hex

import ops
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.hydra.v0.hydra_token_hook import HydraHookProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer

from cli import CommandLine
from configs import CharmConfig
from constants import (
    API_TOKEN_SECRET_KEY,
    API_TOKEN_SECRET_LABEL,
    DATABASE_INTEGRATION_NAME,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    INGRESS_INTEGRATION_NAME,
    LOGGING_INTEGRATION_NAME,
    PEBBLE_READY_CHECK_NAME,
    PORT,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    TEMPO_TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import MigrationCheckError, MigrationError, PebbleError
from integrations import DatabaseConfig, HydraHookIntegration, IngressData, TracingData
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import (
    NOOP_CONDITIONS,
    container_connectivity,
    database_resource_is_created,
    leader_unit,
    migration_is_ready,
)

logger = logging.getLogger(__name__)


class HookServiceOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._secrets = Secrets(self.model)
        self._config = CharmConfig(self.config, self.model)

        self.hydra_token_hook = HydraHookProvider(self)
        self.hydra_token_hook_integration = HydraHookIntegration(self.hydra_token_hook)

        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
        )

        self.ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INGRESS_INTEGRATION_NAME),  # type: ignore
            INGRESS_INTEGRATION_NAME,
            raw=True,
        )

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME,
            jobs=[
                {
                    "job_name": "hook_service_metrics",
                    "metrics_path": "/api/v0/metrics",
                    "static_configs": [
                        {
                            "targets": [f"*:{PORT}"],
                        }
                    ],
                }
            ],
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.framework.observe(self.on.hook_service_pebble_ready, self._on_pebble_ready)
        self.framework.observe(
            self.on.hook_service_pebble_check_failed, self._on_pebble_check_failed
        )
        self.framework.observe(
            self.on.hook_service_pebble_check_recovered, self._on_pebble_check_recovered
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.leader_settings_changed, self._on_leader_settings_changed)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self.framework.observe(self.on.secret_changed, self._on_secret_changed)

        # Hydra token hook relation
        self.framework.observe(self.hydra_token_hook.on.ready, self._on_hydra_hook_ready)

        # COS relations
        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)

        self._grafana_dashboards = GrafanaDashboardProvider(
            self,
            relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME,
        )

        self.tracing_requirer = TracingEndpointRequirer(
            self, relation_name=TEMPO_TRACING_INTEGRATION_NAME, protocols=["otlp_http"]
        )

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # database
        self.framework.observe(
            self.database_requirer.on.database_created, self._on_database_created
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed, self._on_database_changed
        )
        self.framework.observe(
            self.on[DATABASE_INTEGRATION_NAME].relation_broken,
            self._on_database_integration_broken,
        )

        # ingress
        self.framework.observe(
            self.ingress.on.ready,
            self._on_ingress_changed,
        )

    @property
    def _pebble_layer(self) -> ops.pebble.Layer:
        return self._pebble_service.render_pebble_layer(
            TracingData.load(self.tracing_requirer),
            self._secrets,
            self._config,
        )

    @property
    def _hydra_hook_url(self) -> str:
        return (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}/api/v0/hook/hydra"
        )

    @property
    def migration_needed(self) -> bool:
        """Check if database migration is needed."""
        if not self.database_requirer.is_resource_created():
            return False

        database_config = DatabaseConfig.load(self.database_requirer)
        return self._cli.migration_check(dsn=database_config.dsn)

    @leader_unit
    def _prepare_secrets(self) -> None:
        self._secrets[API_TOKEN_SECRET_LABEL] = {API_TOKEN_SECRET_KEY: token_hex(16)}

    @leader_unit
    def _on_ingress_changed(self, event: ops.RelationEvent) -> None:
        if self.ingress.is_ready():
            ingress_config = IngressData.load(self.ingress).config
            self.ingress.submit_to_traefik(ingress_config)
        self._holistic_handler(event)

    def _on_hydra_hook_ready(self, event: ops.RelationEvent) -> None:
        self._holistic_handler(event)

    def _on_leader_elected(self, event: ops.LeaderElectedEvent) -> None:
        self._holistic_handler(event)

    def _on_leader_settings_changed(self, event: ops.LeaderSettingsChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_secret_changed(self, event: ops.SecretChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_integration_broken(self, event: ops.RelationBrokenEvent) -> None:
        self._holistic_handler(event)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        self._workload_service.open_port()
        self._holistic_handler(event)

        self._workload_service.set_version()

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Resource patching failed: {event.message}")
        self._holistic_handler(event)

    def _on_pebble_check_failed(self, event: ops.PebbleCheckFailedEvent) -> None:
        if event.info.name == PEBBLE_READY_CHECK_NAME:
            logger.warning("The service is not running")

    def _on_pebble_check_recovered(self, event: ops.PebbleCheckRecoveredEvent) -> None:
        if event.info.name == PEBBLE_READY_CHECK_NAME:
            logger.info("The service is online again")

    def _holistic_handler(self, event: ops.EventBase) -> None:
        if not all(condition(self) for condition in NOOP_CONDITIONS):
            return

        if not self._secrets.is_ready():
            if not self.unit.is_leader():
                return
            self._prepare_secrets()

        if self.hydra_token_hook_integration.is_ready():
            self.hydra_token_hook_integration.update_relation_data(
                self._hydra_hook_url,
                self._secrets.api_token,
            )

        try:
            if self.migration_needed:
                if not self.unit.is_leader():
                    logger.info(
                        "Unit does not have leadership. Wait for leader unit to run the migration."
                    )
                    return

                database_config = DatabaseConfig.load(self.database_requirer)
                try:
                    self._cli.migrate_up(dsn=database_config.dsn)
                except MigrationError:
                    logger.error("Auto migration job failed. Please use the run-migration-up action")
                    return
        except MigrationCheckError:
            return

        try:
            self._pebble_service.plan(self._pebble_layer)
        except PebbleError:
            logger.error(
                f"Failed to plan pebble layer, please check the {WORKLOAD_CONTAINER} container logs"
            )
            raise

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        if not (can_connect := container_connectivity(self)):
            event.add_status(ops.WaitingStatus("Container is not connected yet"))

        if configs := self._config.get_missing_config_keys():
            event.add_status(ops.BlockedStatus(f"Missing required configuration: {configs}"))

        if not self._secrets.is_ready():
            event.add_status(ops.WaitingStatus("Waiting for secrets creation"))

        if can_connect and not self._workload_service.is_running():
            event.add_status(
                ops.BlockedStatus(
                    f"Failed to start the service, please check the {WORKLOAD_CONTAINER} container logs"
                )
            )

        if not database_resource_is_created(self):
            event.add_status(ops.WaitingStatus("Waiting for database creation"))

        try:
            is_migration_ready = migration_is_ready(self)
        except MigrationCheckError as e:
            event.add_status(ops.BlockedStatus(f"Migration check failed: {e}"))
        else:
            if self.unit.is_leader() and not is_migration_ready:
                event.add_status(ops.WaitingStatus("Waiting for database migration"))

            if not self.unit.is_leader() and not is_migration_ready:
                event.add_status(ops.WaitingStatus("Waiting for leader unit to run the migration"))

        event.add_status(self.resources_patch.get_status())
        event.add_status(ops.ActiveStatus())

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)


if __name__ == "__main__":  # pragma: nocover
    ops.main(HookServiceOperatorCharm)
