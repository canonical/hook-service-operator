# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_APP = "traefik"
DB_CHARM = "postgresql-k8s"
DB_APP = "postgresql"
INGRESS_DOMAIN = "public"
INTERNAL_ROUTE_INTEGRATION_NAME = "internal-route"
