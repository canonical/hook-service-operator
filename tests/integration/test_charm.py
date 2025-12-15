#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import requests
from integration.constants import (
    APP_NAME,
    DB_APP,
    DB_CHARM,
    INGRESS_DOMAIN,
    METADATA,
    TRAEFIK_APP,
    TRAEFIK_CHARM,
)
from integration.utils import (
    remove_integration,
    unit_address,
    wait_for_active_idle,
    wait_for_status,
)

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
def test_build_and_deploy(
    model: jubilant.Juju,
    local_charm: Path | str,
    charm_config: dict,
) -> None:
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}

    model.deploy(
        str(local_charm),
        resources=resources,
        app=APP_NAME,
        config=charm_config,
    )

    model.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_APP,
        channel="latest/stable",
        config={"external_hostname": INGRESS_DOMAIN},
        trust=True,
    )

    model.deploy(
        DB_CHARM,
        app=DB_APP,
        channel="14/stable",
        trust=True,
    )

    model.integrate(TRAEFIK_APP, APP_NAME)
    model.integrate(DB_APP, APP_NAME)

    wait_for_active_idle(
        model,
        apps=[TRAEFIK_APP, DB_APP, APP_NAME],
        timeout=1000,
    )


def test_app_health(
    model: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    public_address = unit_address(model, app_name=APP_NAME, unit_num=0)

    resp = http_client.get(f"http://{public_address}:8080/api/v0/status")

    resp.raise_for_status()


def test_ingress_route(
    model: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    address = unit_address(model, app_name=TRAEFIK_APP, unit_num=0)
    url = f"https://{address}/{model.model}-{APP_NAME}/api/v0/status"
    resp = http_client.get(url)

    resp.raise_for_status()


def test_groups_api(
    model: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    address = unit_address(model, app_name=TRAEFIK_APP, unit_num=0)
    url = f"https://{address}/{model.model}-{APP_NAME}/api/v0/authz/groups"
    resp = http_client.get(url)

    resp.raise_for_status()
    assert resp.json()


def test_scaling_up(model: jubilant.Juju) -> None:
    """Test scaling up."""
    model.cli("scale-application", APP_NAME, "2")
    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


@pytest.mark.parametrize(
    "remote_app_name,integration_name,expected_status",
    [
        (TRAEFIK_APP, "internal-route", "active"),
        (DB_APP, "pg-database", "blocked"),
    ],
)
def test_remove_integration(
    model: jubilant.Juju, remote_app_name: str, integration_name: str, expected_status: str
) -> None:
    """Test removing and re-adding integration."""
    with remove_integration(model, remote_app_name, integration_name):
        wait_for_status(model, apps=[APP_NAME], status=expected_status, timeout=1000)

    wait_for_active_idle(model, apps=[APP_NAME, remote_app_name], timeout=1000)


def test_scaling_down(model: jubilant.Juju) -> None:
    """Test scaling down."""
    model.cli("scale-application", APP_NAME, "1")
    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


@pytest.mark.skip_if_keep_models
def test_remove_application(model: jubilant.Juju) -> None:
    """Test removing the application."""
    model.remove_application(APP_NAME, force=True, destroy_storage=True)
    model.wait(lambda s: APP_NAME not in s.apps, timeout=1000)
