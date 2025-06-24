#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import httpx
import pytest
from pytest_operator.plugin import OpsTest

from tests.integration.conftest import (
    APP_NAME,
    INGRESS_DOMAIN,
    METADATA,
    TRAEFIK_APP,
    TRAEFIK_CHARM,
)

logger = logging.getLogger(__name__)


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, local_charm: Path, charm_config: dict) -> None:
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
    await ops_test.model.deploy(
        local_charm,
        resources=resources,
        application_name=APP_NAME,
        config=charm_config,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_APP,
        channel="latest/stable",
        config={"external_hostname": INGRESS_DOMAIN},
        trust=True,
    )

    await ops_test.model.integrate(TRAEFIK_APP, APP_NAME)

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[TRAEFIK_APP],
            raise_on_error=False,
            raise_on_blocked=False,
            status="active",
            timeout=1000,
        ),
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
    )


async def test_app_health(ops_test: OpsTest, http_client: httpx.AsyncClient) -> None:
    public_address = await get_unit_address(ops_test, APP_NAME, 0)

    resp = await http_client.get(f"http://{public_address}:8080/api/v0/status")

    resp.raise_for_status()
