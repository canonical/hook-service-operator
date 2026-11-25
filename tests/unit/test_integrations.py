# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hook_service.v0.groups_api import GroupsApiProvider
from charms.openfga_k8s.v1.openfga import OpenfgaProviderAppData, OpenFGARequires
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from ops import CharmBase, Relation
from pydantic import AnyHttpUrl

from constants import GRPC_PORT, GRPC_ROUTE_INTEGRATION_NAME, PORT
from integrations import (
    DatabaseConfig,
    GroupsApiIntegration,
    GrpcEndpointData,
    GrpcRouteIntegration,
    InternalIngressData,
    OAuthProviderData,
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


class TestGroupsApiIntegration:
    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock(spec=CharmBase)
        charm.model.name = "test-model"
        charm.app.name = "hook-service"
        charm.model.get_relation.return_value = None
        return charm

    @pytest.fixture
    def mocked_provider(self, mocked_charm: MagicMock) -> MagicMock:
        provider = create_autospec(GroupsApiProvider)
        provider._charm = mocked_charm
        provider.active_relations = [MagicMock(spec=Relation)]
        return provider

    def test_resolve_without_grpc_route(self, mocked_provider: MagicMock) -> None:
        integration = GroupsApiIntegration(mocked_provider)

        assert integration.resolve_grpc_endpoint() == GrpcEndpointData(
            grpc_address=f"hook-service.test-model.svc.cluster.local:{GRPC_PORT}",
            tls_enabled=False,
        )
        assert integration.update_relation_data() is True
        mocked_provider.update_relations_app_data.assert_called_once_with(
            grpc_address=f"hook-service.test-model.svc.cluster.local:{GRPC_PORT}",
            tls_enabled=False,
        )

    def test_resolve_with_grpc_route_external_host(
        self, mocked_charm: MagicMock, mocked_provider: MagicMock
    ) -> None:
        grpc_route_rel = MagicMock(spec=Relation)
        grpc_route_rel.active = True
        grpc_route_rel.app = "traefik"
        grpc_route_rel.data = {"traefik": {"external_host": "grpc.example.com"}}
        mocked_charm.model.get_relation.return_value = grpc_route_rel

        integration = GroupsApiIntegration(mocked_provider)

        assert integration.resolve_grpc_endpoint() == GrpcEndpointData(
            grpc_address=f"grpc.example.com:{GRPC_PORT}",
            tls_enabled=True,
        )
        assert integration.update_relation_data() is True
        mocked_provider.update_relations_app_data.assert_called_once_with(
            grpc_address=f"grpc.example.com:{GRPC_PORT}",
            tls_enabled=True,
        )

    def test_resolve_with_grpc_route_missing_external_host_withholds_write(
        self, mocked_charm: MagicMock, mocked_provider: MagicMock
    ) -> None:
        grpc_route_rel = MagicMock(spec=Relation)
        grpc_route_rel.active = True
        grpc_route_rel.app = "traefik"
        grpc_route_rel.data = {"traefik": {}}
        mocked_charm.model.get_relation.return_value = grpc_route_rel

        integration = GroupsApiIntegration(mocked_provider)

        assert integration.resolve_grpc_endpoint() is None
        assert integration.update_relation_data() is False
        mocked_provider.update_relations_app_data.assert_not_called()

    def test_update_relation_data_inactive_returns_true(self, mocked_provider: MagicMock) -> None:
        mocked_provider.active_relations = []
        integration = GroupsApiIntegration(mocked_provider)

        assert integration.update_relation_data() is True
        mocked_provider.update_relations_app_data.assert_not_called()


class TestOAuthProviderData:
    def test_to_env_vars_merges_and_deduplicates_subjects(self) -> None:
        data = OAuthProviderData(
            auth_enabled=True,
            oidc_issuer_url="https://hydra.example.com",
            allowed_subjects="sub-b, sub-a",
            client_id="client-1",
            extra_subjects=("jaas-sub", "sub-a", " "),
        )

        env = data.to_env_vars()

        assert env["AUTHENTICATION_ALLOWED_SUBJECTS"] == "client-1,jaas-sub,sub-a,sub-b"
