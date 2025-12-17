# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Callable
from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import CollectStatusEvent, EventBase, testing
from ops.model import ActiveStatus, Container, Unit
from ops.testing import Exec, Model
from pytest_mock import MockerFixture

from charm import HookServiceOperatorCharm


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    mock_patcher_cls = mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mock_patcher_instance = mock_patcher_cls.return_value
    mock_patcher_instance.is_failed.return_value = (False, "")
    mock_patcher_instance.is_ready.return_value = True

    mocker.patch("charm.KubernetesComputeResourcesPatch.is_ready", return_value=True)
    mocker.patch("charm.KubernetesComputeResourcesPatch.get_status", return_value=ActiveStatus())
    mocker.patch("charm.KubernetesComputeResourcesPatch._patch", return_value=True)
    mocker.patch("charm.KubernetesComputeResourcesPatch._namespace", return_value="model")


@pytest.fixture
def model() -> Model:
    return Model()


@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="1.10.0"
    )


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.HookServiceOperatorCharm._holistic_handler")


@pytest.fixture
def mocked_is_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService.is_running", return_value=True)


@pytest.fixture
def mocked_open_port(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService.open_port")


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


@pytest.fixture
def mocked_event() -> MagicMock:
    return create_autospec(EventBase)


@pytest.fixture
def internal_route_integration_data() -> dict:
    return {
        "external_host": "some-host",
        "scheme": "http",
    }


@pytest.fixture
def internal_route_integration(internal_route_integration_data: dict) -> testing.Relation:
    return testing.Relation(
        endpoint="internal-route",
        interface="traefik_route",
        remote_app_name="traefik",
        remote_app_data=internal_route_integration_data,
    )


@pytest.fixture()
def api_token() -> str:
    return "secret"


@pytest.fixture()
def salesforce_consumer_info() -> dict[str, str]:
    return {"consumer-key": "key", "consumer-secret": "secret"}


@pytest.fixture()
def api_token_secret(api_token: str) -> testing.Secret:
    return testing.Secret(
        tracked_content={"api-token": api_token},
        label="apitokensecret",
    )


@pytest.fixture()
def salesforce_consumer_secret(salesforce_consumer_info: dict[str, str]) -> testing.Secret:
    return testing.Secret(
        tracked_content=salesforce_consumer_info,
    )


@pytest.fixture()
def mocked_secrets(
    api_token_secret: testing.Secret, salesforce_consumer_secret: testing.Secret
) -> list[testing.Secret]:
    return [api_token_secret, salesforce_consumer_secret]


@pytest.fixture
def salesforce_domain() -> str:
    return "https://domain.salesforce.com"


@pytest.fixture
def charm_config(salesforce_domain: str, salesforce_consumer_secret: testing.Secret) -> dict:
    return {
        "http_proxy": "http://proxy.internal:6666",
        "https_proxy": "http://proxy.internal:6666",
        "no_proxy": "http://proxy.internal:6666",
        "salesforce_domain": salesforce_domain,
        "salesforce_consumer_secret": salesforce_consumer_secret.id,
    }


@pytest.fixture
def mocked_collect_status_event() -> MagicMock:
    return create_autospec(CollectStatusEvent)


@pytest.fixture
def all_satisfied_conditions(
    mocked_container_connectivity: MagicMock,
    mocked_secrets_is_ready: MagicMock,
    mocked_get_missing_config_keys: MagicMock,
    mocked_is_running: MagicMock,
    mocked_database_integration_exists: MagicMock,
    mocked_database_resource_is_created: MagicMock,
    mocked_migration_is_ready: MagicMock,
) -> None:
    pass


@pytest.fixture
def mocked_cli(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.CommandLine")


@pytest.fixture
def mocked_database_config(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.DatabaseConfig")


@pytest.fixture
def database_relation_data() -> dict:
    return {
        "endpoints": "postgres-k8s-primary.namespace.svc.cluster.local:5432",
        "username": "username",
        "password": "password",
    }


@pytest.fixture
def database_relation(database_relation_data: dict) -> testing.Relation:
    return testing.Relation(
        endpoint="pg-database",
        interface="postgresql_client",
        remote_app_name="postgres-k8s",
        remote_app_data=database_relation_data,
    )


@pytest.fixture
def migration_exec_factory() -> Callable[[str, str, int], Exec]:
    def _factory(command: str, stdout: str, return_code: int) -> Exec:
        return Exec(
            command_prefix=[
                "hook-service",
                "migrate",
                command,
            ],
            return_code=return_code,
            stdout=stdout,
        )

    return _factory


@pytest.fixture
def default_migration_check_exec(migration_exec_factory: Callable[[str, str, int], Exec]) -> Exec:
    return migration_exec_factory("check", '{"status": "ok"}', 0)


@pytest.fixture
def default_migration_up_exec(migration_exec_factory: Callable[[str, str, int], Exec]) -> Exec:
    return migration_exec_factory("up", "", 0)


@pytest.fixture
def context() -> testing.Context:
    return testing.Context(HookServiceOperatorCharm)


@pytest.fixture
def container(
    default_migration_check_exec: Exec, default_migration_up_exec: Exec
) -> testing.Container:
    return testing.Container(
        "hook-service",
        can_connect=True,
        execs={default_migration_check_exec, default_migration_up_exec},
    )


@pytest.fixture
def base_state(
    container: testing.Container,
    charm_config: dict,
    mocked_secrets: list[testing.Secret],
    database_relation: testing.Relation,
) -> testing.State:
    return testing.State(
        containers={container},
        config=charm_config,
        secrets=mocked_secrets,
        relations=[database_relation],
    )


@pytest.fixture
def mocked_database_integration_exists(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.database_integration_exists", return_value=True)


@pytest.fixture
def mocked_database_resource_is_created(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.database_resource_is_created", return_value=True)


@pytest.fixture
def mocked_migration_is_ready(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.migration_is_ready", return_value=True)


@pytest.fixture
def mocked_container_connectivity(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.container_connectivity", return_value=True)


@pytest.fixture
def mocked_secrets_is_ready(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.Secrets.is_ready", return_value=True)


@pytest.fixture
def mocked_get_missing_config_keys(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.CharmConfig.get_missing_config_keys", return_value=[])
