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
    unit_address,
    wait_for_active_idle,
)

logger = logging.getLogger(__name__)


@pytest.mark.skip
@pytest.mark.skip_if_deployed
def test_deploy_stable(
    model: jubilant.Juju,
    charm_config: dict,
) -> None:
    """Deploy the stable version of the charm."""
    # Deploy stable version
    model.deploy(
        APP_NAME,
        channel="latest/stable",
        config=charm_config,
        trust=True,
    )

    # Deploy dependencies
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

    # Integrate
    model.integrate(f"{APP_NAME}:ingress", TRAEFIK_APP)
    model.integrate(f"{APP_NAME}:pg-database", DB_APP)

    wait_for_active_idle(model, [APP_NAME, TRAEFIK_APP, DB_APP])


@pytest.mark.skip
def test_upgrade(
    model: jubilant.Juju,
    local_charm: Path | str,
) -> None:
    """Upgrade the charm to the local version."""
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}

    model.refresh(
        APP_NAME,
        path=str(local_charm),
        resources=resources,
    )

    wait_for_active_idle(model, [APP_NAME, TRAEFIK_APP, DB_APP])


@pytest.mark.skip
def test_post_upgrade_check(model: jubilant.Juju, http_client: requests.Session) -> None:
    """Verify functionality after upgrade."""
    address = unit_address(model, app_name=APP_NAME, unit_num=0)
    response = http_client.get(f"http://{address}:8080/health", timeout=10)
    assert response.status_code == 200
