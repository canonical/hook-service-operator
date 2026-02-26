# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's config."""

from typing import Any, Mapping, TypeAlias, cast

from ops import ConfigData, Model

from env_vars import EnvVars

ServiceConfigs: TypeAlias = Mapping[str, Any]


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData, model: Model) -> None:
        self._config = config
        self._model = model

    def _get_secret(self, id) -> dict[str, str]:
        secret = self._model.get_secret(id=id)
        return secret.get_content(refresh=True)

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

    @property
    def authorization_enabled(self) -> bool:
        """Check whether access control authorization is enabled."""
        return self._config.get("authorization_enabled", True)

    def to_env_vars(self) -> EnvVars:
        """Get config env vars."""
        env = {
            "LOG_LEVEL": self._config["log_level"].upper(),
            "AUTHORIZATION_ENABLED": self.authorization_enabled,
            "HTTP_PROXY": self._config.get("http_proxy"),
            "HTTPS_PROXY": self._config.get("https_proxy"),
            "NO_PROXY": self._config.get("no_proxy"),
            **self.get_oauth_config(),
        }
        return env
