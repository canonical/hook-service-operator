# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class with the application's the default env vars."""

from typing import Mapping, Protocol, TypeAlias, Union

from constants import PORT

EnvVars: TypeAlias = Mapping[str, Union[str, bool]]

DEFAULT_CONTAINER_ENV = {
    "OTEL_HTTP_ENDPOINT": "",
    "OTEL_GRPC_ENDPOINT": "",
    "TRACING_ENABLED": False,
    "LOG_LEVEL": "info",
    "PORT": str(PORT),
    "API_TOKEN": "",
    "SALESFORCE_ENABLED": True,
    "SALESFORCE_CONSUMER_KEY": "",
    "SALESFORCE_CONSUMER_SECRET": "",
    "SALESFORCE_DOMAIN": "",
    "AUTHORIZATION_ENABLED": False,
}


class EnvVarConvertible(Protocol):
    """An interface enforcing the contribution to workload service environment variables."""

    def to_env_vars(self) -> EnvVars:
        """Get default env vars."""
        pass
