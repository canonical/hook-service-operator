# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
from typing import Any, ClassVar, Protocol, TypeVar
from unittest.mock import MagicMock, patch

import pytest
from ops import StatusBase, testing
from pytest_mock import MockerFixture

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


class TestAuthn:
    def test_when_oauth_relation_exists(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test that correct env vars are set when OAuth relation exists."""
        config = {
            "authn_allowed_subjects": "user1, user2",
            "authn_allowed_scope": "email",
        }

        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        state_in = replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            config={**base_state.config, **config},
            secrets=[client_secret] + list(base_state.secrets),
        )

        state_out = context.run(
            context.on.pebble_ready(testing.Container(WORKLOAD_CONTAINER)), state_in
        )

        # Check that the pebble layer has the correct environment variables
        container = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container.layers["hook-service"]
        service = layer.services["hook-service"]
        env = service.environment

        assert env["AUTHENTICATION_ENABLED"]
        assert env["AUTHENTICATION_ISSUER"] == "https://hydra.example.com"
        subjects = env["AUTHENTICATION_ALLOWED_SUBJECTS"].split(",")
        assert "hook-service-client-id" in subjects
        assert "user1" in subjects
        assert "user2" in subjects
        assert env["AUTHENTICATION_REQUIRED_SCOPE"] == "email"
        assert env["AUTHENTICATION_JWKS_URL"] == ""

    def test_when_manual_config_exists(
        self,
        context: testing.Context,
        base_state: testing.State,
    ) -> None:
        """Test that correct env vars are set when manual config is provided."""
        config = {
            "authn_issuer": "https://manual.example.com",
            "authn_jwks_url": "https://manual.example.com/jwks",
            "authn_allowed_subjects": "manual_user",
            "authn_allowed_scope": "profile",
        }
        state_in = replace_state(base_state, config={**base_state.config, **config})

        state_out = context.run(
            context.on.pebble_ready(testing.Container(WORKLOAD_CONTAINER)), state_in
        )

        container = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container.layers["hook-service"]
        service = layer.services["hook-service"]
        env = service.environment

        assert env["AUTHENTICATION_ENABLED"]
        assert env["AUTHENTICATION_ISSUER"] == "https://manual.example.com"
        assert env["AUTHENTICATION_JWKS_URL"] == "https://manual.example.com/jwks"
        assert env["AUTHENTICATION_ALLOWED_SUBJECTS"] == "manual_user"
        assert env["AUTHENTICATION_REQUIRED_SCOPE"] == "profile"


class TestConfigChangedEvent:
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
        openfga_secret: testing.Secret,
        openfga_model_id: str,
    ) -> None:
        state_in = replace_state(
            base_state,
            relations=[internal_route_integration] + list(base_state.relations),
            config={**base_state.config, "authorization_enabled": True},
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
            "AUTHORIZATION_ENABLED": True,
            "OPENFGA_API_HOST": "openfga:8080",
            "OPENFGA_API_SCHEME": "http",
            "OPENFGA_API_TOKEN": openfga_secret.tracked_content["token"],
            "OPENFGA_AUTHORIZATION_MODEL_ID": openfga_model_id,
            "OPENFGA_STORE_ID": "some-store-id",
            "DSN": "postgres://username:password@postgres-k8s-primary.namespace.svc.cluster.local:5432/test-model_hook-service",
            "AUTHENTICATION_ENABLED": False,
            "AUTHENTICATION_ISSUER": "",
            "AUTHENTICATION_ALLOWED_SUBJECTS": "",
            "AUTHENTICATION_REQUIRED_SCOPE": "",
            "AUTHENTICATION_JWKS_URL": "",
            "TENANT_SERVICE_URL": "",
        }

    def test_when_authorization_disabled(
        self,
        context: testing.Context,
        base_state: testing.State,
        internal_route_integration: testing.Relation,
    ) -> None:
        state_in = replace_state(
            base_state,
            relations=[internal_route_integration] + list(base_state.relations),
            config={**base_state.config, "authorization_enabled": False},
        )

        state_out = context.run(context.on.config_changed(), state_in)

        layer = state_out.get_container("hook-service").layers["hook-service"]
        assert state_out.unit_status == testing.ActiveStatus()
        assert layer.services.get("hook-service").environment["AUTHORIZATION_ENABLED"] is False

    def test_tenant_service_url_from_relation(
        self,
        context: testing.Context,
        base_state: testing.State,
    ) -> None:
        tenant_service_info_relation = testing.Relation(
            endpoint="tenant-service-info",
            interface="tenant_service_info",
            remote_app_name="tenant-service",
            remote_app_data={
                "service_url": "http://tenant-service:8000",
                "grpc_url": "http://tenant-service:50051",
            },
        )
        state_in = replace_state(
            base_state,
            relations=[tenant_service_info_relation] + list(base_state.relations),
        )

        state_out = context.run(context.on.config_changed(), state_in)

        layer = state_out.get_container("hook-service").layers["hook-service"]
        env = layer.services.get("hook-service").environment  # type: ignore
        assert env["TENANT_SERVICE_URL"] == "http://tenant-service:8000"

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

        context.run(context.on.config_changed(), base_state)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_needed_leader_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False
        mocked_cli.return_value.migrate_up.side_effect = MigrationError("failed")

        context.run(context.on.config_changed(), base_state)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_check_failure(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.side_effect = MigrationCheckError("failed")

        state_in = replace_state(base_state, relations=[])

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

    def test_status_when_valid_oauth_relation(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test that status is Active when OAuth relation is valid and no conflicting config."""
        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )
        state_in = replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            secrets=[client_secret] + list(base_state.secrets),
        )

        state_out = context.run(context.on.collect_unit_status(), state_in)

        assert state_out.unit_status == testing.ActiveStatus()

    def test_status_when_conflicting_config(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test behavior when both relation and manual issuer/jwks config are present."""
        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        config = {
            "authn_issuer": "https://conflict.example.com",
        }
        state_in = replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            config={**base_state.config, **config},
            secrets=[client_secret] + list(base_state.secrets),
        )

        state_out = context.run(context.on.collect_unit_status(), state_in)

        assert state_out.unit_status == testing.ActiveStatus(
            "Ignoring authentication config due to OAuth integration"
        )

    def test_status_when_partial_manual_config(
        self,
        context: testing.Context,
        base_state: testing.State,
    ) -> None:
        """Test BlockedStatus when manual config is missing issuer."""
        config = {
            "authn_allowed_subjects": "user1",
        }
        state_in = replace_state(
            base_state,
            config={**base_state.config, **config},
        )

        state_out = context.run(context.on.collect_unit_status(), state_in)

        assert isinstance(state_out.unit_status, testing.BlockedStatus)

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
        state_in = testing.State(
            containers={container}, leader=leader, config={"authorization_enabled": True}
        )

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

        state_out = context.run(context.on.relation_departed(openfga_relation), base_state)

        mocked_charm_holistic_handler.assert_called_once()
        peer_rel_out = state_out.get_relation(peer_relation.id)
        assert version not in peer_rel_out.local_app_data


class TestGetAccessTokenAction:
    def test_when_oauth_integration_missing(
        self,
        context: testing.Context,
        base_state: testing.State,
    ) -> None:
        """Test action failure when integration is missing."""
        # ops raises ActionFailed when event.fail() is called.
        with pytest.raises(Exception, match="OAuth integration is not ready"):
            context.run(context.on.action("get-access-token"), base_state)

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
        mocked_requests: MagicMock,
    ) -> None:
        """Test successful token retrieval."""
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.return_value = "my-token"

        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        state_in = replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            secrets=[client_secret] + list(base_state.secrets),
        )

        context.run(context.on.action("get-access-token"), state_in)

        mock_client.get_access_token.assert_called_with(
            client_id="hook-service-client-id",
            client_secret="supersecret",
        )


class TestCreateGroupAction:
    def _state_with_oauth(
        self,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> testing.State:
        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )
        return replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            secrets=[client_secret] + list(base_state.secrets),
        )

    def test_when_unauthenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.create_group.return_value = "new-group-id"

        context.run(
            context.on.action("create-group", params={"name": "test-group"}),
            base_state,
        )

        mock_client.get_access_token.assert_not_called()
        mock_client.create_group.assert_called_once_with(
            name="test-group",
            description="",
            group_type="local",
            access_token="",
        )

    def test_when_authenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
        mocked_requests: MagicMock,
    ) -> None:
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.return_value = "jwt-token"
        mock_client.create_group.return_value = "new-group-id"

        context.run(
            context.on.action(
                "create-group",
                params={"name": "test-group", "description": "a test group"},
            ),
            self._state_with_oauth(base_state, oauth_relation),
        )

        mock_client.get_access_token.assert_called_once_with(
            client_id="hook-service-client-id",
            client_secret="supersecret",
        )
        mock_client.create_group.assert_called_once_with(
            name="test-group",
            description="a test group",
            group_type="local",
            access_token="jwt-token",
        )

    def test_when_api_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        mocked_requests.return_value.__enter__.return_value.create_group.side_effect = Exception(
            "connection refused"
        )

        with pytest.raises(Exception, match="Failed to create group"):
            context.run(
                context.on.action("create-group", params={"name": "test-group"}),
                base_state,
            )


class TestDeleteGroupAction:
    def _state_with_oauth(
        self,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> testing.State:
        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )
        return replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            secrets=[client_secret] + list(base_state.secrets),
        )

    def test_when_unauthenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        context.run(
            context.on.action("delete-group", params={"group-id": "some-group-id"}),
            base_state,
        )

        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.assert_not_called()
        mock_client.delete_group.assert_called_once_with(
            group_id="some-group-id",
            access_token="",
        )

    def test_when_authenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
        mocked_requests: MagicMock,
    ) -> None:
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.return_value = "jwt-token"

        context.run(
            context.on.action("delete-group", params={"group-id": "some-group-id"}),
            self._state_with_oauth(base_state, oauth_relation),
        )

        mock_client.get_access_token.assert_called_once_with(
            client_id="hook-service-client-id",
            client_secret="supersecret",
        )
        mock_client.delete_group.assert_called_once_with(
            group_id="some-group-id",
            access_token="jwt-token",
        )

    def test_when_api_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        mocked_requests.return_value.__enter__.return_value.delete_group.side_effect = Exception(
            "404 not found"
        )

        with pytest.raises(Exception, match="Failed to delete group"):
            context.run(
                context.on.action("delete-group", params={"group-id": "some-group-id"}),
                base_state,
            )


class TestListGroupsAction:
    def _state_with_oauth(
        self,
        base_state: testing.State,
        oauth_relation: testing.Relation,
    ) -> testing.State:
        client_secret = testing.Secret(
            id="hook-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )
        return replace_state(
            base_state,
            relations=[oauth_relation] + list(base_state.relations),
            secrets=[client_secret] + list(base_state.secrets),
        )

    def test_when_unauthenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        mocked_requests.return_value.__enter__.return_value.list_groups.return_value = []

        context.run(context.on.action("list-groups"), base_state)

        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.assert_not_called()
        mock_client.list_groups.assert_called_once_with(access_token="")

    def test_when_authenticated(
        self,
        context: testing.Context,
        base_state: testing.State,
        oauth_relation: testing.Relation,
        mocked_requests: MagicMock,
    ) -> None:
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.return_value = "jwt-token"
        mock_client.list_groups.return_value = [
            {"id": "g1", "name": "group-one"},
        ]

        context.run(
            context.on.action("list-groups"),
            self._state_with_oauth(base_state, oauth_relation),
        )

        mock_client.get_access_token.assert_called_once_with(
            client_id="hook-service-client-id",
            client_secret="supersecret",
        )
        mock_client.list_groups.assert_called_once_with(access_token="jwt-token")

    def test_when_api_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocked_requests: MagicMock,
    ) -> None:
        mocked_requests.return_value.__enter__.return_value.list_groups.side_effect = Exception(
            "connection refused"
        )

        with pytest.raises(Exception, match="Failed to list groups"):
            context.run(context.on.action("list-groups"), base_state)


class TestImportGroupsAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action("import-groups", params={"consumer-secret": "secret:id"}),
                base_state,
            )

    def test_when_consumer_secret_missing(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        with pytest.raises(Exception, match="Consumer secret ID is not provided"):
            context.run(context.on.action("import-groups"), base_state)

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.import_groups.return_value = "import output"

        consumer_secret = testing.Secret(
            tracked_content={"consumer-key": "mykey", "consumer-secret": "mysecret"},
        )
        state_in = replace_state(base_state, secrets=list(base_state.secrets) + [consumer_secret])

        out = context.run(
            context.on.action(
                "import-groups",
                params={
                    "driver": "salesforce",
                    "domain": "sf.example.com",
                    "consumer-secret": consumer_secret.id,
                },
            ),
            state_in,
        )

        assert out.unit_status == out.unit_status  # action succeeded (no exception)
        mocked_cli.return_value.import_groups.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            driver="salesforce",
            domain="sf.example.com",
            consumer_key="mykey",
            consumer_secret="mysecret",
            sync=False,
            openfga_host="",
            openfga_store_id="",
            openfga_token="",
            openfga_model_id="",
        )

    def test_when_sync_with_openfga(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
        openfga_model_id: str,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.import_groups.return_value = ""

        consumer_secret = testing.Secret(
            tracked_content={"consumer-key": "mykey", "consumer-secret": "mysecret"},
        )
        state_in = replace_state(base_state, secrets=list(base_state.secrets) + [consumer_secret])

        context.run(
            context.on.action(
                "import-groups",
                params={
                    "driver": "salesforce",
                    "domain": "sf.example.com",
                    "consumer-secret": consumer_secret.id,
                    "sync": True,
                },
            ),
            state_in,
        )

        call_kwargs = mocked_cli.return_value.import_groups.call_args.kwargs
        assert call_kwargs["sync"] is True
        assert call_kwargs["openfga_host"] != ""
        assert call_kwargs["openfga_store_id"] != ""
        assert call_kwargs["openfga_token"] != ""

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.import_groups.side_effect = Exception("connection refused")

        consumer_secret = testing.Secret(
            tracked_content={"consumer-key": "mykey", "consumer-secret": "mysecret"},
        )
        state_in = replace_state(base_state, secrets=list(base_state.secrets) + [consumer_secret])

        with pytest.raises(Exception, match="Import failed"):
            context.run(
                context.on.action(
                    "import-groups",
                    params={"consumer-secret": consumer_secret.id},
                ),
                state_in,
            )


class TestUsersDeleteAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action("users-delete", params={"user-id": "alice@example.com"}),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        context.run(
            context.on.action("users-delete", params={"user-id": "alice@example.com"}),
            base_state,
        )
        mocked_cli.return_value.users_delete.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            user_id="alice@example.com",
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.users_delete.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to delete user"):
            context.run(
                context.on.action("users-delete", params={"user-id": "alice@example.com"}),
                base_state,
            )


class TestUsersListGroupsAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action("users-list-groups", params={"user-id": "alice@example.com"}),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.users_list_groups.return_value = '[{"id": "g1"}]'
        context.run(
            context.on.action("users-list-groups", params={"user-id": "alice@example.com"}),
            base_state,
        )
        mocked_cli.return_value.users_list_groups.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            user_id="alice@example.com",
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.users_list_groups.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to list groups for user"):
            context.run(
                context.on.action("users-list-groups", params={"user-id": "alice@example.com"}),
                base_state,
            )


class TestUsersSetGroupsAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action(
                    "users-set-groups",
                    params={"user-id": "alice@example.com", "groups": "g1,g2"},
                ),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        context.run(
            context.on.action(
                "users-set-groups",
                params={"user-id": "alice@example.com", "groups": "g1, g2"},
            ),
            base_state,
        )
        mocked_cli.return_value.users_set_groups.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            user_id="alice@example.com",
            group_ids=["g1", "g2"],
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.users_set_groups.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to set groups for user"):
            context.run(
                context.on.action(
                    "users-set-groups",
                    params={"user-id": "alice@example.com", "groups": "g1"},
                ),
                base_state,
            )


class TestGroupsAddUsersAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action(
                    "groups-add-users",
                    params={"group-id": "g1", "users": "alice@example.com"},
                ),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        context.run(
            context.on.action(
                "groups-add-users",
                params={"group-id": "g1", "users": "alice@example.com, bob@example.com"},
            ),
            base_state,
        )
        mocked_cli.return_value.groups_add_users.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            group_id="g1",
            user_ids=["alice@example.com", "bob@example.com"],
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.groups_add_users.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to add users to group"):
            context.run(
                context.on.action(
                    "groups-add-users",
                    params={"group-id": "g1", "users": "alice@example.com"},
                ),
                base_state,
            )


class TestGroupsRemoveUsersAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action(
                    "groups-remove-users",
                    params={"group-id": "g1", "users": "alice@example.com"},
                ),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        context.run(
            context.on.action(
                "groups-remove-users",
                params={"group-id": "g1", "users": "alice@example.com"},
            ),
            base_state,
        )
        mocked_cli.return_value.groups_remove_users.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            group_id="g1",
            user_ids=["alice@example.com"],
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.groups_remove_users.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to remove users from group"):
            context.run(
                context.on.action(
                    "groups-remove-users",
                    params={"group-id": "g1", "users": "alice@example.com"},
                ),
                base_state,
            )


class TestGroupsListUsersAction:
    def test_when_database_not_ready(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=False,
        )
        with pytest.raises(Exception, match="Database is not ready"):
            context.run(
                context.on.action("groups-list-users", params={"group-id": "g1"}),
                base_state,
            )

    def test_when_success(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.groups_list_users.return_value = '["alice@example.com"]'
        context.run(
            context.on.action("groups-list-users", params={"group-id": "g1"}),
            base_state,
        )
        mocked_cli.return_value.groups_list_users.assert_called_once_with(
            dsn=mocked_database_config.load.return_value.dsn,
            group_id="g1",
        )

    def test_when_cli_fails(
        self,
        context: testing.Context,
        base_state: testing.State,
        mocker: MockerFixture,
        mocked_cli: MagicMock,
        mocked_database_config: MagicMock,
    ) -> None:
        mocker.patch(
            "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created",
            return_value=True,
        )
        mocked_cli.return_value.groups_list_users.side_effect = Exception("db error")
        with pytest.raises(Exception, match="Failed to list users in group"):
            context.run(
                context.on.action("groups-list-users", params={"group-id": "g1"}),
                base_state,
            )


class TestCertificateEvents:
    def test_on_certificate_changed(
        self,
        context: testing.Context,
        base_state: testing.State,
        certificate_transfer_relation: testing.Relation,
        mocked_subprocess_run: MagicMock,
        mocker: MagicMock,  # To mock path operations
    ) -> None:
        # Mock Path operations to avoid filesystem access
        mock_path = mocker.patch("charm.LOCAL_CHARM_CERTIFICATES_FILE")
        mock_path.exists.return_value = False

        # Mock parent directory creation
        mock_path.parent.mkdir.return_value = None

        # Mock TLSCertificates to bypass library issues and test charm logic
        mock_tls = mocker.patch("charm.TLSCertificates")
        mock_tls.load.return_value.ca_bundle = "some-ca-cert"

        state_in = replace_state(
            base_state,
            relations=[certificate_transfer_relation] + list(base_state.relations),
        )

        context.run(context.on.relation_changed(certificate_transfer_relation), state_in)

        mock_path.write_text.assert_called_with("some-ca-cert")
        mocked_subprocess_run.assert_called()
