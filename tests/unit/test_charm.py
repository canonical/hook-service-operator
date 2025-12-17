# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
from typing import Any, ClassVar, Protocol, TypeVar
from unittest.mock import MagicMock, patch

import pytest
from ops import StatusBase, testing

from constants import OPENFGA_INTEGRATION_NAME, WORKLOAD_CONTAINER
from exceptions import MigrationCheckError, MigrationError


class DataclassInstance(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]


T = TypeVar("T", bound=DataclassInstance)


def replace_state(state: T, **kwargs: Any) -> T:
    """Helper to update state until Scenario provides a better way."""
    return dataclasses.replace(state, **kwargs)


class TestPebbleReadyEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        container: testing.Container,
        base_state: testing.State,
        mocked_open_port: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        state_out = context.run(context.on.pebble_ready(container), base_state)

        assert state_out.unit_status == testing.ActiveStatus()
        mocked_open_port.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()
        assert state_out.workload_version == mocked_workload_service_version.return_value


class TestConfigChangedEvent:
    def test_when_config_missing(
        self,
        context: testing.Context,
        base_state: testing.State,
    ) -> None:
        state_in = replace_state(base_state, config={})

        state_out = context.run(context.on.config_changed(), state_in)

        assert isinstance(state_out.unit_status, testing.BlockedStatus)

    def test_when_event_emitted(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        state_out = context.run(context.on.config_changed(), base_state)

        assert state_out.unit_status == testing.ActiveStatus()
        mocked_charm_holistic_handler.assert_called_once()


class TestIngressReadyEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        base_state: testing.State,
        internal_route_integration: testing.Relation,
    ) -> None:
        state_in = replace_state(
            base_state,
            relations=[internal_route_integration] + list(base_state.relations),
        )

        state_out = context.run(context.on.relation_joined(internal_route_integration), state_in)

        assert state_out.unit_status == testing.ActiveStatus()


class TestIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        base_state: testing.State,
        internal_route_integration: testing.Relation,
    ) -> None:
        state_in = replace_state(
            base_state,
            relations=[internal_route_integration] + list(base_state.relations),
        )

        state_out = context.run(context.on.relation_broken(internal_route_integration), state_in)

        assert state_out.unit_status == testing.ActiveStatus()


class TestHolisticHandler:
    def test_when_container_not_connected(
        self,
        context: testing.Context,
        base_state: testing.State,
        container: testing.Container,
    ) -> None:
        container = replace_state(container, can_connect=False)
        state_in = replace_state(
            base_state,
            containers=[container],
        )

        # We abuse the config_changed event, to run the unit tests on holistic_handler.
        # Scenario does not provide us with a way to
        state_out = context.run(context.on.config_changed(), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_all_conditions_satisfied(
        self,
        context: testing.Context,
        base_state: testing.State,
        internal_route_integration: testing.Relation,
        api_token: str,
        salesforce_domain: str,
        salesforce_consumer_secret: testing.Secret,
    ) -> None:
        state_in = replace_state(
            base_state,
            relations=[internal_route_integration] + list(base_state.relations),
            leader=True,
        )

        # We abuse the config_changed event, to run the unit tests on holistic_handler.
        # Scenario does not provide us with a way to
        state_out = context.run(context.on.config_changed(), state_in)

        layer = state_out.get_container("hook-service").layers["hook-service"]
        assert state_out.unit_status == testing.ActiveStatus()
        assert layer.services.get("hook-service").environment == {  # type: ignore
            "HTTPS_PROXY": "http://proxy.internal:6666",
            "HTTP_PROXY": "http://proxy.internal:6666",
            "NO_PROXY": "http://proxy.internal:6666",
            "OTEL_HTTP_ENDPOINT": "",
            "OTEL_GRPC_ENDPOINT": "",
            "TRACING_ENABLED": False,
            "LOG_LEVEL": "INFO",
            "PORT": "8080",
            "API_TOKEN": api_token,
            "SALESFORCE_ENABLED": True,
            "SALESFORCE_DOMAIN": salesforce_domain,
            "SALESFORCE_CONSUMER_KEY": salesforce_consumer_secret.tracked_content["consumer-key"],
            "SALESFORCE_CONSUMER_SECRET": salesforce_consumer_secret.tracked_content[
                "consumer-secret"
            ],
            "OPENFGA_API_HOST": "",
            "OPENFGA_API_SCHEME": "",
            "OPENFGA_API_TOKEN": "",
            "OPENFGA_AUTHORIZATION_MODEL_ID": "",
            "OPENFGA_STORE_ID": "",
            "DSN": "postgres://username:password@postgres-k8s-primary.namespace.svc.cluster.local:5432/test-model_hook-service",
        }

    def test_migration_needed_not_leader(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False

        state_in = replace_state(base_state, leader=False)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_not_called()

    def test_migration_needed_leader_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False
        state_in = replace_state(base_state, leader=True)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_needed_leader_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False
        mocked_cli.return_value.migrate_up.side_effect = MigrationError("failed")

        state_in = replace_state(base_state, leader=True)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_check_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.side_effect = MigrationCheckError("failed")

        state_in = replace_state(base_state, leader=True, relations=[])

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_not_called()


class TestCollectStatusEvent:
    def test_when_all_condition_satisfied(
        self,
        context: testing.Context,
        base_state: testing.State,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        state_out = context.run(context.on.collect_unit_status(), base_state)

        assert state_out.unit_status == testing.ActiveStatus()

    @pytest.mark.parametrize(
        "condition, condition_value, status, message, leader",
        [
            (
                "container_connectivity",
                False,
                testing.WaitingStatus,
                "Container is not connected yet",
                True,
            ),
            (
                "WorkloadService.is_failing",
                True,
                testing.BlockedStatus,
                f"Failed to start the service, please check the {WORKLOAD_CONTAINER} container logs",
                True,
            ),
            (
                "database_resource_is_created",
                False,
                testing.WaitingStatus,
                "Waiting for database creation",
                True,
            ),
            (
                "migration_is_ready",
                MigrationCheckError("failed"),
                testing.BlockedStatus,
                "Migration check failed: failed",
                True,
            ),
            (
                "migration_is_ready",
                False,
                testing.WaitingStatus,
                "Waiting for database migration",
                True,
            ),
            (
                "migration_is_ready",
                False,
                testing.WaitingStatus,
                "Waiting for leader unit to run the migration",
                False,
            ),
            (
                "openfga_integration_exists",
                False,
                testing.BlockedStatus,
                f"Missing integration {OPENFGA_INTEGRATION_NAME}",
                True,
            ),
            (
                "OpenFGAIntegration.is_store_ready",
                False,
                testing.WaitingStatus,
                "Waiting for openfga store to be created",
                True,
            ),
        ],
        ids=[
            "container_not_connected",
            "workload_service_failing",
            "database_resource_not_created",
            "migration_check_error",
            "migration_not_ready",
            "not_leader_waiting_for_migration",
            "openfga_integration_missing",
            "openfga_store_not_ready",
        ],
    )
    def test_when_a_condition_failed(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        condition: str,
        condition_value: bool | Exception,
        status: type[StatusBase],
        message: str,
        leader: bool,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container}, leader=leader)

        patch_kwargs = {}
        if isinstance(condition_value, Exception):
            patch_kwargs["side_effect"] = condition_value
        else:
            patch_kwargs["return_value"] = condition_value

        with patch(f"charm.{condition}", **patch_kwargs):
            state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, status)
        assert state_out.unit_status.message == message


class TestDatabaseEvents:
    def test_on_database_created(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
        database_relation: testing.Relation,
    ) -> None:
        context.run(context.on.relation_changed(database_relation), base_state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_database_integration_broken(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
        database_relation: testing.Relation,
    ) -> None:
        context.run(context.on.relation_broken(database_relation), base_state)

        mocked_charm_holistic_handler.assert_called_once()


class TestOpenFGAEvents:
    def test_on_openfga_store_created(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
    ) -> None:
        context.run(context.on.relation_changed(openfga_relation), base_state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_openfga_store_removed(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
    ) -> None:
        context.run(context.on.relation_departed(openfga_relation), base_state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_openfga_store_removed_leader(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
        peer_relation: testing.Relation,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        version = mocked_workload_service_version.return_value
        state_in = replace_state(
            base_state,
            leader=True,
        )

        state_out = context.run(context.on.relation_departed(openfga_relation), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        peer_rel_out = state_out.get_relation(peer_relation.id)
        assert version not in peer_rel_out.local_app_data
