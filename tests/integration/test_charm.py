#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import socket
import ssl
from pathlib import Path

import jubilant
import pytest
import requests
import yaml
from integration.constants import (
    APP_NAME,
    DB_APP,
    DB_CHARM,
    GRPC_PORT,
    GRPC_ROUTE_INTEGRATION_NAME,
    INGRESS_DOMAIN,
    METADATA,
    OPENFGA_APP,
    OPENFGA_CHARM,
    TRAEFIK_APP,
    TRAEFIK_CHARM,
)
from integration.utils import (
    get_unit_data,
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
        trust=True,
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

    model.deploy(
        OPENFGA_CHARM,
        app=OPENFGA_APP,
        channel="latest/edge",
        trust=True,
    )

    model.integrate(TRAEFIK_APP, f"{APP_NAME}:internal-route")
    model.integrate(TRAEFIK_APP, f"{APP_NAME}:{GRPC_ROUTE_INTEGRATION_NAME}")
    model.integrate(DB_APP, APP_NAME)
    model.integrate(f"{DB_APP}:database", f"{OPENFGA_APP}:database")
    model.integrate(OPENFGA_APP, f"{APP_NAME}:openfga")

    wait_for_active_idle(
        model,
        apps=[TRAEFIK_APP, DB_APP, OPENFGA_APP, APP_NAME],
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


def test_grpc_route(model: jubilant.Juju) -> None:
    """Test gRPC TCP routing through Traefik on port 9090."""
    traefik_unit_data = get_unit_data(model, f"{TRAEFIK_APP}/0")
    grpc_relations = [
        rel["application-data"]
        for rel in traefik_unit_data["relation-info"]
        if rel["endpoint"] == "traefik-route" and "static" in rel.get("application-data", {})
    ]
    assert len(grpc_relations) == 1
    static_cfg = yaml.safe_load(grpc_relations[0]["static"])
    assert static_cfg == {"entryPoints": {"grpc": {"address": f":{GRPC_PORT}"}}}

    address = unit_address(model, app_name=TRAEFIK_APP, unit_num=0)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    ssl_ctx.set_alpn_protocols(["h2"])

    with socket.create_connection((address, GRPC_PORT), timeout=10) as raw_sock:
        with ssl_ctx.wrap_socket(raw_sock, server_hostname=INGRESS_DOMAIN) as tls_sock:
            assert tls_sock.selected_alpn_protocol() == "h2"
            tls_sock.sendall(
                b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n\x00\x00\x00\x04\x00\x00\x00\x00\x00"
            )
            header = tls_sock.recv(9)
            assert len(header) == 9
            assert header[3] == 0x04


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
        (TRAEFIK_APP, GRPC_ROUTE_INTEGRATION_NAME, "active"),
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
