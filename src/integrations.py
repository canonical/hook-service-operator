# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper classes for managing the charm's integrations."""

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_token_hook import (
    AuthIn,
    HydraHookProvider,
    ProviderData,
)
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template
from pydantic import AnyHttpUrl

from constants import HYDRA_TOKEN_HOOK_INTEGRATION_NAME, PORT, POSTGRESQL_DSN_TEMPLATE
from env_vars import EnvVars

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngressData:
    """The data source from the internal-ingress integration."""

    endpoint: AnyHttpUrl
    config: dict = field(default_factory=dict)

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer) -> "IngressData":
        """Load the ingress data."""
        model, app = requirer._charm.model.name, requirer._charm.app.name
        external_host = requirer.external_host
        external_endpoint = f"{requirer.scheme}://{external_host}/{model}-{app}"

        with open("templates/ingress.json.j2", "r") as file:
            template = Template(file.read())

        ingress_config = json.loads(
            template.render(
                model=model,
                app=app,
                port=PORT,
                external_host=external_host,
            )
        )

        endpoint = AnyHttpUrl(
            external_endpoint
            if external_host
            else f"http://{app}.{model}.svc.cluster.local:{PORT}"
        )

        return cls(
            endpoint=endpoint,
            config=ingress_config,
        )


@dataclass(frozen=True)
class TracingData:
    """The data source from the tracing integration."""

    is_ready: bool = False
    http_endpoint: str = ""

    def to_env_vars(self) -> EnvVars:
        """Get tracing env vars."""
        return {
            "TRACING_ENABLED": self.is_ready,
            "OTEL_HTTP_ENDPOINT": self.http_endpoint,
        }

    @classmethod
    def load(cls, requirer: TracingEndpointRequirer) -> "TracingData":
        """Load the tracing data."""
        if not (is_ready := requirer.is_ready()):
            return TracingData()

        http_endpoint = urlparse(requirer.get_endpoint("otlp_http"))

        return TracingData(
            is_ready=is_ready,
            http_endpoint=http_endpoint.geturl().replace(f"{http_endpoint.scheme}://", "", 1),  # type: ignore[arg-type]
        )


class HydraHookIntegration:
    def __init__(self, provider: HydraHookProvider) -> None:
        self._provider = provider

    def is_ready(self) -> bool:
        rel = self._provider._charm.model.get_relation(HYDRA_TOKEN_HOOK_INTEGRATION_NAME)
        return bool(rel and rel.active)

    def update_relation_data(self, hook_url: str, api_token: str) -> None:
        self._provider.update_relations_app_data(
            ProviderData(
                url=hook_url,
                auth_config_name="Authorization",
                auth_config_value=api_token,
                auth_config_in=AuthIn.header,
            )
        )


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    migration_version: str = ""

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_env_vars(self) -> EnvVars:
        return {
            "DSN": self.dsn,
        }

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> "DatabaseConfig":
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
            migration_version=f"migration_version_{integration_id}",
        )
