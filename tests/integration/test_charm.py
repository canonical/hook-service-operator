#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import zipfile
from pathlib import Path

import jubilant
import pytest
import requests
import yaml
from integration.constants import (
    APP_NAME,
    DB_APP,
    DB_CHARM,
    GROUPS_API_INTEGRATION_NAME,
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
    assert_grpc_route,
    get_app_integration_data,
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
    assert_grpc_route(model)


def test_groups_api(
    model: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    address = unit_address(model, app_name=TRAEFIK_APP, unit_num=0)
    url = f"https://{address}/{model.model}-{APP_NAME}/api/v0/authz/groups"
    resp = http_client.get(url)

    resp.raise_for_status()
    assert resp.json()


def _build_groups_api_requirer_charm(charm_path: Path, subject: str) -> Path:
    metadata = yaml.safe_dump({
        "name": "groups-api-requirer",
        "summary": "Test requirer charm for groups-api",
        "description": "Test requirer charm for groups-api",
        "assumes": ["k8s-api"],
        "requires": {"groups-api": {"interface": "groups_api", "limit": 1}},
    })
    manifest = yaml.safe_dump({
        "charmcraft-started-at": "2026-01-01T00:00:00Z",
        "bases": [{"name": "ubuntu", "channel": "22.04", "architectures": ["amd64"]}],
    })
    default_hook = "#!/bin/sh\nset -eu\nstatus-set active\n"
    relation_hook = (
        f"#!/bin/sh\nset -eu\nrelation-set --app subject={subject} || true\nstatus-set active\n"
    )
    hooks = {
        "hooks/install": default_hook,
        "hooks/start": default_hook,
        "hooks/config-changed": default_hook,
        "hooks/upgrade-charm": default_hook,
        "hooks/groups-api-relation-created": relation_hook,
        "hooks/groups-api-relation-joined": relation_hook,
        "hooks/groups-api-relation-changed": relation_hook,
        "hooks/groups-api-relation-departed": default_hook,
        "hooks/groups-api-relation-broken": default_hook,
    }
    with zipfile.ZipFile(charm_path, "w") as archive:
        archive.writestr("metadata.yaml", metadata)
        archive.writestr("manifest.yaml", manifest)
        for rel_path, content in hooks.items():
            info = zipfile.ZipInfo(rel_path)
            info.external_attr = 0o100755 << 16
            archive.writestr(info, content)
    return charm_path


def test_groups_api_relation(model: jubilant.Juju, tmp_path: Path) -> None:
    """Test groups-api auth enforcement, endpoint resolution, and allowed subjects."""
    requirer_app = "groups-api-requirer"
    subject = "jaas-test-subject"
    requirer_charm = _build_groups_api_requirer_charm(
        tmp_path / "groups-api-requirer.charm",
        subject=subject,
    )
    model.deploy(str(requirer_charm), app=requirer_app)
    model.integrate(f"{APP_NAME}:{GROUPS_API_INTEGRATION_NAME}", f"{requirer_app}:groups-api")

    try:
        wait_for_status(model, apps=[APP_NAME], status="blocked", timeout=300)
        unauth_data = (
            get_app_integration_data(
                model, app_name=requirer_app, integration_name=GROUPS_API_INTEGRATION_NAME
            )
            or {}
        )
        assert "grpc_address" not in unauth_data

        model.config(
            APP_NAME,
            {
                "authn_issuer": "https://auth.example.com",
                "authn_jwks_url": "https://auth.example.com/.well-known/jwks.json",
            },
        )
        wait_for_active_idle(model, apps=[APP_NAME, requirer_app], timeout=600)

        ingress_data = get_app_integration_data(
            model, app_name=requirer_app, integration_name=GROUPS_API_INTEGRATION_NAME
        )
        assert ingress_data == {
            "grpc_address": f"{INGRESS_DOMAIN}:{GRPC_PORT}",
            "tls_enabled": "true",
        }

        plan_json = model.cli(
            "exec",
            "--unit",
            f"{APP_NAME}/0",
            "--",
            "python3",
            "-c",
            (
                "import socket, json; "
                "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); "
                "s.connect('/charm/containers/hook-service/pebble.socket'); "
                "s.sendall(b'GET /v1/plan?format=yaml HTTP/1.0\\r\\n\\r\\n'); "
                "raw = b''.join(iter(lambda: s.recv(65536), b'')); "
                "print(json.loads(raw.split(b'\\r\\n\\r\\n', 1)[1])['result'])"
            ),
        )
        plan = yaml.safe_load(plan_json)
        allowed_subjects = plan["services"][APP_NAME]["environment"][
            "AUTHENTICATION_ALLOWED_SUBJECTS"
        ]
        assert subject in allowed_subjects.split(",")
        with remove_integration(model, TRAEFIK_APP, GRPC_ROUTE_INTEGRATION_NAME):
            wait_for_active_idle(model, apps=[APP_NAME, requirer_app], timeout=600)
            in_cluster_data = get_app_integration_data(
                model, app_name=requirer_app, integration_name=GROUPS_API_INTEGRATION_NAME
            )
            assert in_cluster_data == {
                "grpc_address": f"{APP_NAME}.{model.model}.svc.cluster.local:{GRPC_PORT}",
                "tls_enabled": "false",
            }
    finally:
        model.remove_application(requirer_app, force=True, destroy_storage=True)
        model.wait(lambda s: requirer_app not in s.apps, timeout=300)
        model.config(APP_NAME, {"authn_issuer": "", "authn_jwks_url": ""})
        wait_for_active_idle(model, apps=[APP_NAME, TRAEFIK_APP], timeout=600)


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
    if integration_name == GRPC_ROUTE_INTEGRATION_NAME:
        # grpc-route removal and re-addition restarts Traefik twice (static
        # entrypoint withdrawn, then republished); retry until routing recovers.
        assert_grpc_route(model, timeout=120)


def test_scaling_down(model: jubilant.Juju) -> None:
    """Test scaling down."""
    model.cli("scale-application", APP_NAME, "1")
    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


@pytest.mark.skip_if_keep_models
def test_remove_application(model: jubilant.Juju) -> None:
    """Test removing the application."""
    model.remove_application(APP_NAME, force=True, destroy_storage=True)
    model.wait(lambda s: APP_NAME not in s.apps, timeout=1000)
