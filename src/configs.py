# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's config."""

from typing import Any, Mapping, Tuple, TypeAlias, cast

from ops import ConfigData, Model

from constants import (
    CONFIG_CONSUMER_KEY_SECRET_KEY,
    CONFIG_CONSUMER_SECRET_SECRET_KEY,
)
from env_vars import EnvVars
from exceptions import InvalidSalesforceConfig

ServiceConfigs: TypeAlias = Mapping[str, Any]


class CharmConfig:
    """A class representing the data source of charm configurations."""

    REQUIRED_KEYS = ["salesforce_domain", "salesforce_consumer_secret"]

    def __init__(self, config: ConfigData, model: Model) -> None:
        self._config = config
        self._model = model

    def _get_secret(self, id) -> dict[str, str]:
        secret = self._model.get_secret(id=id)
        return secret.get_content(refresh=True)

    def _get_salesforce_consumer_info(self) -> Tuple[str, str]:
        try:
            secret_id = self._config["salesforce_consumer_secret"]
            content = self._get_secret(secret_id)
            return content[CONFIG_CONSUMER_KEY_SECRET_KEY], content[
                CONFIG_CONSUMER_SECRET_SECRET_KEY
            ]
        except Exception as e:
            raise InvalidSalesforceConfig from e

    def get_oauth_config(self) -> dict[str, str | None]:
        """Get OAuth config."""
        return {
            k: cast(str, v)
            for k in [
                "authn_allowed_subjects",
                "authn_allowed_scope",
                "authn_issuer",
                "authn_jwks_url",
            ]
            if (v := self._config.get(k))
        }

    def get_missing_config_keys(self) -> list:
        """Get missing config keys."""
        if not self._config.get("salesforce_enabled"):
            return []
        return [k for k in self.REQUIRED_KEYS if not self._config.get(k)]

    def to_env_vars(self) -> EnvVars:
        """Get config env vars."""
        env = {
            "LOG_LEVEL": self._config["log_level"].upper(),
            "SALESFORCE_ENABLED": self._config.get("salesforce_enabled", True),
            "HTTP_PROXY": self._config.get("http_proxy"),
            "HTTPS_PROXY": self._config.get("https_proxy"),
            "NO_PROXY": self._config.get("no_proxy"),
            **self.get_oauth_config(),
        }
        if self._config.get("salesforce_enabled"):
            consumer = self._get_salesforce_consumer_info()
            env.update({
                "SALESFORCE_CONSUMER_KEY": consumer[0],
                "SALESFORCE_CONSUMER_SECRET": consumer[1],
                "SALESFORCE_DOMAIN": self._config.get("salesforce_domain"),
            })
        return env
