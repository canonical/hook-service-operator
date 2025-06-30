# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from pydantic import AnyHttpUrl

from constants import PORT
from integrations import IngressData


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
