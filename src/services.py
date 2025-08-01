# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's services."""

import logging
from collections import ChainMap

from ops import Container, ModelError, Unit
from ops.pebble import Layer, LayerDict

from cli import CommandLine
from constants import (
    PORT,
    SERVICE_COMMAND,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "hook-service-operator layer",
    "description": "pebble config layer for hook-service-operator",
    "services": {
        WORKLOAD_CONTAINER: {
            "override": "replace",
            "summary": "entrypoint of the hook-service-operator image",
            "command": f"{SERVICE_COMMAND}",
            "startup": "disabled",
        }
    },
    "checks": {
        "ready": {
            "override": "replace",
            "http": {"url": f"http://localhost:{PORT}/api/v0/status"},
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""

        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        """Get the service version."""
        if not self._version:
            self._version = self._cli.get_service_version() or ""
        return self._version

    def set_version(self) -> None:
        """Set the service version."""
        try:
            self._unit.set_workload_version(self.version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)

    @property
    def is_running(self) -> bool:
        """Checks whether the service is running."""
        try:
            workload_service = self._container.get_service(WORKLOAD_CONTAINER)
        except ModelError:
            return False

        return workload_service.is_running()

    def open_port(self) -> None:
        """Open the service ports."""
        self._unit.open_port(protocol="tcp", port=PORT)


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_CONTAINER)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def _restart_service(self, restart: bool = False) -> None:
        if restart:
            self._container.restart(WORKLOAD_SERVICE)
        elif not self._container.get_service(WORKLOAD_SERVICE).is_running():
            self._container.start(WORKLOAD_SERVICE)
        else:
            self._container.replan()

    def plan(self, layer: Layer) -> None:
        """Plan the pebble service."""
        self._container.add_layer(WORKLOAD_SERVICE, layer, combine=True)

        try:
            self._restart_service()
        except Exception as e:
            raise PebbleError(f"Pebble failed to restart the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        """Render the pebble layer."""
        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore
        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **updated_env_vars,
        }
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)
