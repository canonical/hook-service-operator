# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
from typing import Dict

import pytest
from ops.testing import Model
from pytest_mock import MockerFixture

from configs import CharmConfig
from exceptions import InvalidSalesforceConfig


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
            "salesforce_enabled": False,
        }
        expected = {
            "LOG_LEVEL": "DEBUG",
            "SALESFORCE_ENABLED": False,
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
            "salesforce_enabled": False,
            "authorization_enabled": True,
        }
        expected = {
            "LOG_LEVEL": "DEBUG",
            "SALESFORCE_ENABLED": False,
            "AUTHORIZATION_ENABLED": True,
            "HTTP_PROXY": None,
            "HTTPS_PROXY": None,
            "NO_PROXY": None,
        }
        actual = CharmConfig(config, mocked_model).to_env_vars()

        assert actual == expected

    def test_to_service_configs_without_salesforce_config(self, mocked_model: Model) -> None:
        config = {
            "log_level": "debug",
            "salesforce_enabled": True,
        }

        with pytest.raises(InvalidSalesforceConfig):
            CharmConfig(config, mocked_model).to_env_vars()

    def test_to_service_configs_with_salesforce_config(
        self, mocked_model: Model, secret_content: Dict
    ) -> None:
        config = {
            "log_level": "debug",
            "salesforce_enabled": True,
            "salesforce_consumer_secret": "id",
            "salesforce_domain": "http://salesforce.com",
        }
        expected = {
            "LOG_LEVEL": "DEBUG",
            "SALESFORCE_ENABLED": True,
            "AUTHORIZATION_ENABLED": True,
            "HTTP_PROXY": None,
            "HTTPS_PROXY": None,
            "NO_PROXY": None,
            "SALESFORCE_CONSUMER_KEY": secret_content["consumer-key"],
            "SALESFORCE_CONSUMER_SECRET": secret_content["consumer-secret"],
            "SALESFORCE_DOMAIN": "http://salesforce.com",
        }

        actual = CharmConfig(config, mocked_model).to_env_vars()

        assert actual == expected

    def test_get_missing_config_keys_when_salesforce_disabled(self, mocked_model: Model) -> None:
        config = {
            "log_level": "debug",
            "salesforce_enabled": False,
        }

        r = CharmConfig(config, mocked_model).get_missing_config_keys()

        assert r == []

    @pytest.mark.parametrize(
        "config, missing",
        [
            (
                {
                    "log_level": "debug",
                    "salesforce_enabled": True,
                },
                ["salesforce_domain", "salesforce_consumer_secret"],
            ),
            (
                {
                    "log_level": "debug",
                    "salesforce_enabled": True,
                    "salesforce_consumer_secret": "id",
                },
                ["salesforce_domain"],
            ),
            (
                {
                    "log_level": "debug",
                    "salesforce_enabled": True,
                    "salesforce_domain": "http://salesforce.com",
                },
                ["salesforce_consumer_secret"],
            ),
            (
                {
                    "log_level": "debug",
                    "salesforce_enabled": True,
                    "salesforce_consumer_secret": "id",
                    "salesforce_domain": "http://salesforce.com",
                },
                [],
            ),
        ],
    )
    def test_get_missing_config_keys(
        self, mocked_model: Model, config: Dict, missing: list
    ) -> None:
        r = CharmConfig(config, mocked_model).get_missing_config_keys()

        assert set(r) == set(missing)
