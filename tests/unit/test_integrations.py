# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.openfga_k8s.v1.openfga import OpenfgaProviderAppData, OpenFGARequires
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from ops import CharmBase, Relation
from pydantic import AnyHttpUrl

from constants import GRPC_PORT, GRPC_ROUTE_INTEGRATION_NAME, PORT
from integrations import (
    DatabaseConfig,
    GrpcRouteIntegration,
    InternalIngressData,
    OpenFGAIntegration,
    OpenFGAIntegrationData,
    OpenFGAModelData,
)


class TestInternalIngressData:
    @pytest.fixture
    def mocked_relation(self) -> MagicMock:
        mocked = MagicMock(spec=Relation)
        mocked.app = "app"
        mocked.data = {"app": {"external_host": "external.hook-service.com", "scheme": "http"}}
        return mocked

    @pytest.fixture
    def mocked_requirer(self, mocked_relation: MagicMock) -> MagicMock:
        mocked = create_autospec(TraefikRouteRequirer)
        mocked._charm = MagicMock()
        mocked._charm.model.name = "model"
        mocked._charm.app.name = "app"
        mocked.scheme = "http"
        mocked._charm.model.get_relation = MagicMock(return_value=mocked_relation)

        return mocked

    @pytest.fixture
    def ingress_template(self) -> str:
        return (
            '{"model": "{{ model }}", '
            '"app": "{{ app }}", '
            '"port": {{ port }}, '
            '"external_host": "{{ external_host }}"}'
        )

    def test_load_with_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "port": PORT,
            "external_host": "external.hook-service.com",
        }
        assert actual == InternalIngressData(
            url=AnyHttpUrl("http://external.hook-service.com/model-app"),
            config=expected_ingress_config,
        )

    def test_load_without_external_host(
        self, mocked_requirer: MagicMock, mocked_relation: MagicMock, ingress_template: str
    ) -> None:
        mocked_relation.data = {"app": {"external_host": "", "scheme": "http"}}

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        assert actual == InternalIngressData(
            url=None,
            config={},
        )


class TestGrpcRouteIntegration:
    @pytest.fixture
    def mocked_relation(self) -> MagicMock:
        mocked = MagicMock(spec=Relation)
        mocked.active = True
        mocked.app = "traefik"
        return mocked

    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock(spec=CharmBase)
        charm.model.name = "model"
        charm.app.name = "app"
        charm.unit.is_leader.return_value = True
        return charm

    @pytest.fixture
    def mocked_requirer(self, mocked_relation: MagicMock) -> MagicMock:
        requirer = create_autospec(TraefikRouteRequirer)
        requirer.is_ready.return_value = True
        requirer._relation = mocked_relation
        return requirer

    def test_default_requirer_uses_raw_false(self, mocked_charm: MagicMock) -> None:
        relation = MagicMock(spec=Relation)
        mocked_charm.model.get_relation.return_value = relation

        with patch("integrations.TraefikRouteRequirer") as requirer_cls:
            integration = GrpcRouteIntegration(mocked_charm)

        requirer_cls.assert_called_once_with(
            mocked_charm,
            relation,
            GRPC_ROUTE_INTEGRATION_NAME,
            raw=False,
        )
        assert integration.requirer is requirer_cls.return_value

    def test_submit_to_traefik_leader(
        self, mocked_charm: MagicMock, mocked_requirer: MagicMock
    ) -> None:
        integration = GrpcRouteIntegration(mocked_charm, requirer=mocked_requirer)

        integration.submit_to_traefik()

        expected_config = {
            "tcp": {
                "routers": {
                    "juju-model-app-grpc-router": {
                        "entryPoints": ["grpc"],
                        "rule": "HostSNI(`*`)",
                        "service": "juju-model-app-grpc-service",
                        "tls": {"passthrough": False},
                    }
                },
                "services": {
                    "juju-model-app-grpc-service": {
                        "loadBalancer": {
                            "servers": [{"address": f"app.model.svc.cluster.local:{GRPC_PORT}"}]
                        }
                    }
                },
            }
        }
        expected_static = {"entryPoints": {"grpc": {"address": f":{GRPC_PORT}"}}}
        mocked_requirer.submit_to_traefik.assert_called_once_with(
            config=expected_config,
            static=expected_static,
        )

    def test_submit_to_traefik_non_leader_skips(
        self, mocked_charm: MagicMock, mocked_requirer: MagicMock
    ) -> None:
        mocked_charm.unit.is_leader.return_value = False
        integration = GrpcRouteIntegration(mocked_charm, requirer=mocked_requirer)

        integration.submit_to_traefik()

        mocked_requirer.submit_to_traefik.assert_not_called()

    @pytest.mark.parametrize(
        "is_ready, active, app",
        [
            (False, True, "traefik"),
            (True, False, "traefik"),
            (True, True, None),
        ],
    )
    def test_submit_to_traefik_not_ready_skips(
        self,
        mocked_charm: MagicMock,
        mocked_requirer: MagicMock,
        mocked_relation: MagicMock,
        is_ready: bool,
        active: bool,
        app: str | None,
    ) -> None:
        mocked_requirer.is_ready.return_value = is_ready
        mocked_relation.active = active
        mocked_relation.app = app
        integration = GrpcRouteIntegration(mocked_charm, requirer=mocked_requirer)

        integration.submit_to_traefik()

        mocked_requirer.submit_to_traefik.assert_not_called()


class TestDatabaseConfig:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(DatabaseRequires)
        mocked.database = "test_db"
        mocked.relations = [MagicMock(id=1)]
        mocked.fetch_relation_data.return_value = {
            1: {
                "endpoints": "host:5432",
                "username": "user",
                "password": "password",
            }
        }
        return mocked

    def test_load(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.endpoint == "host:5432"
        assert config.database == "test_db"
        assert config.username == "user"
        assert config.password == "password"

    def test_dsn(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.dsn == "postgres://user:password@host:5432/test_db"

    def test_to_env_vars(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.to_env_vars() == {"DSN": "postgres://user:password@host:5432/test_db"}


class TestOpenFGAModelData:
    def test_load(self) -> None:
        source = {"openfga_model_id": "test-model-id"}
        data = OpenFGAModelData.load(source)
        assert data.model_id == "test-model-id"

    def test_load_empty(self) -> None:
        source = {}
        data = OpenFGAModelData.load(source)
        assert data.model_id == ""

    def test_to_env_vars(self) -> None:
        data = OpenFGAModelData(model_id="test-model-id")
        assert data.to_env_vars() == {"OPENFGA_AUTHORIZATION_MODEL_ID": "test-model-id"}


class TestOpenFGAIntegrationData:
    def test_properties(self) -> None:
        data = OpenFGAIntegrationData(
            url="http://openfga.local:8080",
            api_token="token",
            store_id="store-id",
        )
        assert data.api_scheme == "http"
        assert data.api_host == "openfga.local:8080"

    def test_to_env_vars(self) -> None:
        data = OpenFGAIntegrationData(
            url="http://openfga.local:8080",
            api_token="token",
            store_id="store-id",
        )
        expected = {
            "OPENFGA_STORE_ID": "store-id",
            "OPENFGA_API_TOKEN": "token",
            "OPENFGA_API_SCHEME": "http",
            "OPENFGA_API_HOST": "openfga.local:8080",
        }
        assert data.to_env_vars() == expected


class TestOpenFGAIntegration:
    @pytest.fixture(autouse=True)
    def mocked_openfga_integration(self) -> None:
        """Override the autouse fixture from conftest.py to do nothing."""
        pass

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(OpenFGARequires)

    def test_is_store_ready_true(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id="store-id",
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        assert integration.is_store_ready()

    def test_is_store_ready_false_no_info(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = None
        integration = OpenFGAIntegration(mocked_requirer)
        assert not integration.is_store_ready()

    def test_is_store_ready_false_no_id(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id=None,
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        assert not integration.is_store_ready()

    def test_openfga_integration_data(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = OpenfgaProviderAppData(
            store_id="store-id",
            token="token",
            http_api_url="http://url",
            grpc_api_url="grpc://url",
        )
        integration = OpenFGAIntegration(mocked_requirer)
        data = integration.openfga_integration_data

        assert data.store_id == "store-id"
        assert data.api_token == "token"
        assert data.url == "http://url"

    def test_openfga_integration_data_empty(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_store_info.return_value = None
        integration = OpenFGAIntegration(mocked_requirer)
        data = integration.openfga_integration_data

        assert data == OpenFGAIntegrationData()
