# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from ops import StatusBase, testing

from constants import WORKLOAD_CONTAINER
from exceptions import MigrationCheckError, MigrationError


def replace_state(state: testing.State, **kwargs) -> testing.State:
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
        mocked_secrets: list[testing.Secret],
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container}, secrets=mocked_secrets)

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
        charm_config: dict,
    ) -> None:
        container = testing.Container("hook-service", can_connect=False)
        state_in = testing.State(containers={container}, config=charm_config)

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
            "DSN": f"postgres://username:password@postgres-k8s-primary.namespace.svc.cluster.local:5432/{state_out.model.name}_hook-service",
        }

    def test_migration_needed_not_leader(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False  # Migration needed
        mocked_database_config.load.return_value.dsn = "dsn"

        state_in = replace_state(base_state, leader=False)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_not_called()

    def test_migration_needed_leader_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False  # Migration needed
        mocked_database_config.load.return_value.dsn = "dsn"

        state_in = replace_state(base_state, leader=True)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_called_once_with(dsn="dsn")

    def test_migration_needed_leader_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False  # Migration needed
        mocked_cli.return_value.migrate_up.side_effect = MigrationError("failed")
        mocked_database_config.load.return_value.dsn = "dsn"

        state_in = replace_state(base_state, leader=True)

        context.run(context.on.config_changed(), state_in)

        mocked_cli.return_value.migrate_up.assert_called_once_with(dsn="dsn")

    def test_migration_check_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.side_effect = MigrationCheckError("failed")
        mocked_database_config.load.return_value.dsn = "dsn"

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
        "condition, condition_value, status, message",
        [
            (
                "container_connectivity",
                False,
                testing.WaitingStatus,
                "Container is not connected yet",
            ),
            (
                "WorkloadService.is_failing",
                True,
                testing.BlockedStatus,
                f"Failed to start the service, please check the {WORKLOAD_CONTAINER} container logs",
            ),
        ],
    )
    def test_when_a_condition_failed(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        condition: str,
        condition_value: bool,
        status: type[StatusBase],
        message: str,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container})

        with patch(f"charm.{condition}", return_value=condition_value):
            state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, status)
        assert state_out.unit_status.message == message

    def test_when_database_not_created(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container})

        with patch("charm.database_resource_is_created", return_value=False):
            state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        assert state_out.unit_status.message == "Waiting for database creation"

    def test_when_migration_check_failed(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container})

        with patch("charm.database_resource_is_created", return_value=True):
            with patch("charm.migration_is_ready", side_effect=MigrationCheckError("failed")):
                state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, testing.BlockedStatus)
        assert "Migration check failed" in state_out.unit_status.message

    def test_when_migration_not_ready_leader(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container}, leader=True)

        with patch("charm.database_resource_is_created", return_value=True):
            with patch("charm.migration_is_ready", return_value=False):
                state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        assert state_out.unit_status.message == "Waiting for database migration"

    def test_when_migration_not_ready_not_leader(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        container = testing.Container("hook-service", can_connect=True)
        state_in = testing.State(containers={container}, leader=False)

        with patch("charm.database_resource_is_created", return_value=True):
            with patch("charm.migration_is_ready", return_value=False):
                state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        assert state_out.unit_status.message == "Waiting for leader unit to run the migration"


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
