# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
from typing import Dict

import pytest
from ops.testing import Model
from pytest_mock import MockerFixture

from configs import CharmConfig


class TestCharmConfig:
    @pytest.fixture
    def secret_content(self) -> Dict[str, str]:
        return {
            "consumer-key": "key",
            "consumer-secret": "secret",
        }

    @pytest.fixture
    def mocked_model(
        self, secret_content: Dict, mocker: MockerFixture, model: Model
    ) -> Dict[str, str]:
        mocker.patch("configs.CharmConfig._get_secret", return_value=secret_content)
        return model

    def test_to_service_configs(self, mocked_model: Model) -> None:
        config = {
            "log_level": "debug",
        }
        expected = {
            "LOG_LEVEL": "DEBUG",
            "AUTHORIZATION_ENABLED": True,
            "HTTP_PROXY": None,
            "HTTPS_PROXY": None,
            "NO_PROXY": None,
        }
        actual = CharmConfig(config, mocked_model).to_env_vars()

        assert actual == expected

    def test_to_service_configs_with_authorization_enabled(self, mocked_model: Model) -> None:
        config = {
            "log_level": "debug",
            "authorization_enabled": True,
        }
        expected = {
            "LOG_LEVEL": "DEBUG",
            "AUTHORIZATION_ENABLED": True,
            "HTTP_PROXY": None,
            "HTTPS_PROXY": None,
            "NO_PROXY": None,
        }
        actual = CharmConfig(config, mocked_model).to_env_vars()

        assert actual == expected
