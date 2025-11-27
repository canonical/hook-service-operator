# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from pydantic import AnyHttpUrl

from constants import PORT
from integrations import DatabaseConfig, IngressData


class TestIngressData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(TraefikRouteRequirer)
        mocked._charm = MagicMock()
        mocked._charm.model.name = "model"
        mocked._charm.app.name = "app"
        mocked.scheme = "http"
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
        mocked_requirer.external_host = "external.hook-service.com"

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = IngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "port": PORT,
            "external_host": "external.hook-service.com",
        }
        assert actual == IngressData(
            endpoint=AnyHttpUrl("http://external.hook-service.com/model-app"),
            config=expected_ingress_config,
        )

    def test_load_without_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        mocked_requirer.external_host = ""

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = IngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "port": PORT,
            "external_host": "",
        }
        assert actual == IngressData(
            endpoint=AnyHttpUrl(f"http://app.model.svc.cluster.local:{PORT}"),
            config=expected_ingress_config,
        )


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
        assert config.migration_version == "migration_version_1"

    def test_dsn(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.dsn == "postgres://user:password@host:5432/test_db"

    def test_to_env_vars(self, mocked_requirer: MagicMock) -> None:
        config = DatabaseConfig.load(mocked_requirer)
        assert config.to_env_vars() == {
            "DSN": "postgres://user:password@host:5432/test_db"
        }
