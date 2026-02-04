#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for Identity Platform Hook Service."""

import logging
import subprocess
from os.path import join
from secrets import token_hex

import ops
from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
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
from charms.openfga_k8s.v1.openfga import (
    OpenFGARequires,
    OpenFGAStoreCreateEvent,
    OpenFGAStoreRemovedEvent,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer

from cli import CommandLine
from clients import HTTPClient
from configs import CharmConfig
from constants import (
    API_TOKEN_SECRET_KEY,
    API_TOKEN_SECRET_LABEL,
    CERTIFICATE_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    INTERNAL_ROUTE_INTEGRATION_NAME,
    LOCAL_CERTIFICATES_PATH,
    LOCAL_CHARM_CERTIFICATES_FILE,
    LOCAL_CHARM_CERTIFICATES_PATH,
    LOGGING_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    OPENFGA_MODEL_ID,
    OPENFGA_STORE_NAME,
    PEBBLE_READY_CHECK_NAME,
    PORT,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    TEMPO_TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import (
    CharmError,
    CreateFgaStoreError,
    MigrationCheckError,
    MigrationError,
    PebbleError,
)
from integrations import (
    DatabaseConfig,
    HydraHookIntegration,
    InternalIngressData,
    OpenFGAIntegration,
    OpenFGAModelData,
    PeerData,
    TLSCertificates,
    TracingData,
)
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import (
    NOOP_CONDITIONS,
    container_connectivity,
    database_integration_exists,
    database_resource_is_created,
    migration_is_ready,
    openfga_integration_exists,
    peer_integration_exists,
)

logger = logging.getLogger(__name__)


class HookServiceOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)
        self.peer_data = PeerData(self.model)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._secrets = Secrets(self.model)
        self._config = CharmConfig(self.config, self.model)

        self.hydra_token_hook = HydraHookProvider(self)
        self.hydra_token_hook_integration = HydraHookIntegration(self.hydra_token_hook)

        self.openfga_requirer = OpenFGARequires(
            self, store_name=OPENFGA_STORE_NAME, relation_name=OPENFGA_INTEGRATION_NAME
        )
        self.openfga_integration = OpenFGAIntegration(self.openfga_requirer)

        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
        )

        self.internal_ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME),  # type: ignore
            INTERNAL_ROUTE_INTEGRATION_NAME,
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

        self.certificate_transfer_requirer = CertificateTransferRequires(
            self,
            relationship_name=CERTIFICATE_TRANSFER_INTEGRATION_NAME,
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

        # Oauth relation
        self.framework.observe(
            self.oauth_requirer.on.oauth_info_changed,
            self._on_oauth_info_changed,
        )
        self.framework.observe(
            self.oauth_requirer.on.oauth_info_removed,
            self._on_oauth_info_changed,
        )

        # Certificate transfer relation
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificate_set_updated,
            self._on_certificate_transfer_changed,
        )
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificates_removed,
            self._on_certificate_transfer_changed,
        )

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

        # internal route
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_joined,
            self._on_internal_route_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_changed,
            self._on_internal_route_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_ROUTE_INTEGRATION_NAME].relation_broken,
            self._on_internal_route_changed,
        )

        self.framework.observe(
            self.openfga_requirer.on.openfga_store_created,
            self._on_openfga_store_created,
        )
        self.framework.observe(
            self.openfga_requirer.on.openfga_store_removed,
            self._on_openfga_store_removed,
        )

    @property
    def _pebble_layer(self) -> ops.pebble.Layer:
        return self._pebble_service.render_pebble_layer(
            TracingData.load(self.tracing_requirer),
            DatabaseConfig.load(self.database_requirer),
            self._secrets,
            self._config,
            OpenFGAModelData.load(self.peer_data[self._workload_service.version]),
            self.openfga_integration.openfga_integration_data,
        )

    @property
    def _hydra_hook_url(self) -> str:
        if internal_url := InternalIngressData.load(self.internal_ingress).url:
            return join(str(internal_url), "api/v0/hook/hydra")
        return (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}/api/v0/hook/hydra"
        )

    @property
    def migration_needed(self) -> bool:
        """Check if database migration is needed."""
        if not self.database_requirer.is_resource_created():
            return False

        database_config = DatabaseConfig.load(self.database_requirer)
        return not self._cli.migration_check(dsn=database_config.dsn)

    def _ensure_secrets(self) -> bool:
        if self._secrets.is_ready():
            return True

        if self.unit.is_leader():
            self._secrets[API_TOKEN_SECRET_LABEL] = {API_TOKEN_SECRET_KEY: token_hex(16)}
            return True
        return False

    def _ensure_hydra_relation(self) -> bool:
        if self.unit.is_leader() and self.hydra_token_hook_integration.is_ready():
            self.hydra_token_hook_integration.update_relation_data(
                self._hydra_hook_url,
                self._secrets.api_token,
            )
        return True

    def _ensure_internal_ingress(self) -> bool:
        # This always returns true if the unit is not the leader, can't we simplify this function?
        if (
            self.unit.is_leader()
            and self.internal_ingress.is_ready()
            and self.internal_ingress._relation.app is not None
        ):
            internal_route_config = InternalIngressData.load(self.internal_ingress).config
            self.internal_ingress.submit_to_traefik(internal_route_config)
        return True

    def _ensure_database_migration(self) -> bool:
        if migration_is_ready(self):
            return True

        if not self.unit.is_leader():
            logger.info(
                "Unit does not have leadership. Wait for leader unit to run the migration."
            )
            return False

        database_config = DatabaseConfig.load(self.database_requirer)
        try:
            self._cli.migrate_up(dsn=database_config.dsn)
        except MigrationError:
            logger.error("Auto migration job failed. Please use the run-migration-up action")
            return False
        return True

    def _ensure_openfga_model(self) -> bool:
        if not self.openfga_integration.is_store_ready():
            return False

        if not peer_integration_exists(self):
            return False

        if self.peer_data[self._workload_service.version].get(OPENFGA_MODEL_ID):
            return True

        if not self.unit.is_leader():
            return False

        try:
            openfga_model_id = self._workload_service.create_openfga_model(
                self.openfga_integration.openfga_integration_data
            )
        except CreateFgaStoreError:
            logger.exception("Failed to create OpenFGA model")
            return False

        self.peer_data[self._workload_service.version] = {OPENFGA_MODEL_ID: openfga_model_id}
        return True

    def _ensure_tls(self) -> bool:
        LOCAL_CHARM_CERTIFICATES_FILE.parent.mkdir(parents=True, exist_ok=True)

        if certificates := TLSCertificates.load(self.certificate_transfer_requirer).ca_bundle:
            LOCAL_CHARM_CERTIFICATES_FILE.write_text(certificates)
        elif LOCAL_CHARM_CERTIFICATES_FILE.exists():
            LOCAL_CHARM_CERTIFICATES_FILE.unlink()

        subprocess.run([
            "update-ca-certificates",
            "--fresh",
            "--etccertsdir",
            LOCAL_CERTIFICATES_PATH,
            "--localcertsdir",
            LOCAL_CHARM_CERTIFICATES_PATH,
        ])
        self._workload_service.update_ca_certs()
        return True

    def _on_internal_route_changed(self, event: ops.RelationEvent) -> None:
        # needed due to how traefik_route lib is handling the event
        self.internal_ingress._relation = event.relation
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

    def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent) -> None:
        self._holistic_handler(event)

    def _on_openfga_store_removed(self, event: OpenFGAStoreRemovedEvent) -> None:
        if self.unit.is_leader():
            self.peer_data.pop(key=self._workload_service.version)

        self._holistic_handler(event)

    def _on_certificate_transfer_changed(self, event: ops.EventBase) -> None:
        self._holistic_handler(event)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        self._workload_service.open_port()
        self._holistic_handler(event)

        self._workload_service.set_version()

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error("Resource patching failed: %s", event.message)
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

        can_plan = True
        for f in [
            self._ensure_secrets,
            self._ensure_hydra_relation,
            self._ensure_internal_ingress,
            self._ensure_database_migration,
            self._ensure_openfga_model,
            self._ensure_tls,
        ]:
            try:
                can_plan = can_plan and f()
            except CharmError:
                can_plan = False

        if not can_plan:
            return

        try:
            self._pebble_service.plan(self._pebble_layer)
        except PebbleError:
            logger.error(
                "Failed to plan pebble layer, please check the %s container logs",
                WORKLOAD_CONTAINER,
            )
            raise

    def _get_migration_status(self) -> ops.StatusBase | None:
        try:
            is_migration_ready = migration_is_ready(self)
        except MigrationCheckError as e:
            return ops.BlockedStatus(f"Migration check failed: {e}")

        if not is_migration_ready:
            if self.unit.is_leader():
                return ops.WaitingStatus("Waiting for database migration")
            return ops.WaitingStatus("Waiting for leader unit to run the migration")
        return None

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        if not (can_connect := container_connectivity(self)):
            event.add_status(ops.WaitingStatus("Container is not connected yet"))

        if configs := self._config.get_missing_config_keys():
            event.add_status(ops.BlockedStatus(f"Missing required configuration: {configs}"))

        if not self._secrets.is_ready():
            event.add_status(ops.WaitingStatus("Waiting for secrets creation"))

        if can_connect and self._workload_service.is_failing():
            event.add_status(
                ops.BlockedStatus(
                    f"Failed to start the service, please check the {WORKLOAD_CONTAINER} container logs"
                )
            )

        if not database_integration_exists(self):
            event.add_status(ops.BlockedStatus(f"Missing integration {DATABASE_INTEGRATION_NAME}"))

        if not database_resource_is_created(self):
            event.add_status(ops.WaitingStatus("Waiting for database creation"))

        if not openfga_integration_exists(self):
            event.add_status(ops.BlockedStatus(f"Missing integration {OPENFGA_INTEGRATION_NAME}"))

        if not self.openfga_integration.is_store_ready():
            event.add_status(ops.WaitingStatus("Waiting for openfga store to be created"))

        if migration_status := self._get_migration_status():
            event.add_status(migration_status)

        event.add_status(self.resources_patch.get_status())
        event.add_status(ops.ActiveStatus())

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)


if __name__ == "__main__":  # pragma: nocover
    ops.main(HookServiceOperatorCharm)
