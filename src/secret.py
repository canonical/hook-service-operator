# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's secrets."""

from typing import Optional, ValuesView

from ops import Model, SecretNotFoundError

from configs import ServiceConfigs
from constants import API_TOKEN_SECRET_KEY, API_TOKEN_SECRET_LABEL


class Secrets:
    """An abstraction of the charm secret management."""

    KEYS = (API_TOKEN_SECRET_KEY,)
    LABELS = (API_TOKEN_SECRET_LABEL,)

    def __init__(self, model: Model) -> None:
        self._model = model

    def __getitem__(self, label: str) -> Optional[dict[str, str]]:
        """Get a secret."""
        if label not in self.LABELS:
            return None

        try:
            secret = self._model.get_secret(label=label)
        except SecretNotFoundError:
            return None

        return secret.get_content()

    def __setitem__(self, label: str, content: dict[str, str]) -> None:
        """Set a secret."""
        if label not in self.LABELS:
            raise ValueError(f"Invalid label: '{label}'. Valid labels are: {self.LABELS}.")

        self._model.app.add_secret(content, label=label)

    def values(self) -> ValuesView:
        """Get the ValuesView."""
        secret_contents = {}
        for key, label in zip(self.KEYS, self.LABELS):
            try:
                secret = self._model.get_secret(label=label)
            except SecretNotFoundError:
                return ValuesView({})
            else:
                secret_contents[key] = secret.get_content()

        return secret_contents.values()

    def to_env_vars(self) -> ServiceConfigs:
        """Get secret env vars."""
        return {
            "API_TOKEN": self.api_token,
        }

    def is_ready(self) -> bool:
        """Check whether the service secrets are ready."""
        values = self.values()
        return all(values) if values else False

    @property
    def api_token(self) -> str:
        """Get the api token."""
        return self[API_TOKEN_SECRET_LABEL][API_TOKEN_SECRET_KEY]
