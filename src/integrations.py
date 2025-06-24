# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper classes for managing the charm's integrations."""

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template
from pydantic import AnyHttpUrl

from constants import PORT
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
