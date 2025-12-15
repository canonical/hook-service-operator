# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from contextlib import contextmanager
from typing import Iterator, Optional

import jubilant
import pytest
import yaml
from integration.constants import APP_NAME
from tenacity import retry, stop_after_attempt, wait_exponential


def create_temp_juju_model(
    request: pytest.FixtureRequest, *, model: str = ""
) -> Iterator[jubilant.Juju]:
    """Create a temporary Juju model."""
    keep_models = bool(request.config.getoption("--keep-models"))

    # jubilant.temp_model is a context manager provided by the library
    with jubilant.temp_model(keep=keep_models) as juju:
        # Hack to get around `jubilant.temp_model` not accepting a custom model name
        if model:
            assert juju.model is not None
            # Destroy `jubilant-*` model created by default
            juju.destroy_model(juju.model, destroy_storage=True, force=True)

            # `CLIError` will be emitted if `--model` already exists so silently ignore
            # error and set the `model` attribute to the value of model.
            try:
                juju.add_model(model)
            except jubilant.CLIError:
                juju.model = model

        juju.wait_timeout = 10 * 60

        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end="")


def get_unit_data(model: jubilant.Juju, unit_name: str) -> dict:
    """Get the data for a given unit."""
    stdout = model.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    model: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    """Get the integration data for a given integration."""
    data = get_unit_data(model, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    model: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    """Get the application data for a given integration."""
    data = get_integration_data(model, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def unit_address(model: jubilant.Juju, *, app_name: str, unit_num: int = 0) -> str:
    """Get the address of a unit."""
    status_yaml = model.cli("status", "--format", "yaml")
    status = yaml.safe_load(status_yaml)
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


def wait_for_active_idle(model: jubilant.Juju, apps: list[str], timeout: float = 1000) -> None:
    """Wait for all applications and their units to be active and idle."""

    def condition(s: jubilant.Status) -> bool:
        return jubilant.all_active(s, *apps) and jubilant.all_agents_idle(s, *apps)

    model.wait(condition, error=jubilant.any_error, timeout=timeout)


def wait_for_status(
    model: jubilant.Juju, apps: list[str], status: str, timeout: float = 1000
) -> None:
    """Wait for all applications and their units to reach the given status."""

    def condition(s: jubilant.Status) -> bool:
        return all(s.apps[app_name].app_status.current == status for app_name in apps)

    model.wait(condition, timeout=timeout)


@contextmanager
def remove_integration(
    juju: jubilant.Juju, /, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Temporarily remove an integration from the application.

    Integration is restored after the context is exited.
    """

    # The pre-existing integration instance can still be "dying" when the `finally` block
    # is called, so `tenacity.retry` is used here to capture the `jubilant.CLIError`
    # and re-run `juju integrate ...` until the previous integration instance has finished dying.
    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _reintegrate() -> None:
        juju.integrate(f"{APP_NAME}:{integration_name}", remote_app_name)

    juju.remove_relation(f"{APP_NAME}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        _reintegrate()
