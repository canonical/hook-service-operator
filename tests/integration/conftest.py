# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import os
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Optional

import httpx
import pytest_asyncio
import yaml
from pytest_operator.plugin import OpsTest

from constants import INTERNAL_ROUTE_INTEGRATION_NAME

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_APP = "traefik"
DB_CHARM = "postgresql-k8s"
DB_APP = "postgresql"
INGRESS_DOMAIN = "public"


async def get_unit_data(ops_test: OpsTest, unit_name: str) -> dict:
    show_unit_cmd = (f"show-unit {unit_name}").split()
    _, stdout, _ = await ops_test.juju(*show_unit_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


async def get_integration_data(
    ops_test: OpsTest, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    data = await get_unit_data(ops_test, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


async def get_app_integration_data(
    ops_test: OpsTest,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


@pytest_asyncio.fixture
async def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test)


@pytest_asyncio.fixture
async def leader_ingress_integration_data(app_integration_data: Callable) -> dict:
    data = await app_integration_data(APP_NAME, INTERNAL_ROUTE_INTEGRATION_NAME)
    assert data
    return data


async def unit_address(ops_test: OpsTest, *, app_name: str, unit_num: int = 0) -> str:
    status = await ops_test.model.get_status()
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest_asyncio.fixture
async def internal_address() -> Callable[[OpsTest, int], Awaitable[str]]:
    return functools.partial(unit_address, app_name=TRAEFIK_APP)


@pytest_asyncio.fixture(scope="module")
async def local_charm(ops_test: OpsTest) -> Path:
    # in GitHub CI, charms are built with charmcraftcache and uploaded to $CHARM_PATH
    charm = os.getenv("CHARM_PATH")
    if not charm:
        # fall back to build locally - required when run outside of GitHub CI
        charm = await ops_test.build_charm(".")
    return charm


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def charm_config(ops_test: OpsTest) -> dict:
    return {
        "salesforce_enabled": False,
    }
