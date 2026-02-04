# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants."""

# Charm constants
from pathlib import Path
from string import Template

POSTGRESQL_DSN_TEMPLATE = Template("postgres://$username:$password@$endpoint/$database")
WORKLOAD_CONTAINER = "hook-service"
WORKLOAD_SERVICE = "hook-service"
PEBBLE_READY_CHECK_NAME = "ready"
API_TOKEN_SECRET_KEY = "api-token"
API_TOKEN_SECRET_LABEL = "apitokensecret"
CONFIG_CONSUMER_KEY_SECRET_KEY = "consumer-key"
CONFIG_CONSUMER_SECRET_SECRET_KEY = "consumer-secret"
LOCAL_CERTIFICATES_PATH = Path("/tmp")
LOCAL_CERTIFICATES_FILE = Path(LOCAL_CERTIFICATES_PATH / "ca-certificates.crt")
LOCAL_CHARM_CERTIFICATES_PATH = Path("/tmp/charm")
LOCAL_CHARM_CERTIFICATES_FILE = Path(LOCAL_CHARM_CERTIFICATES_PATH / "charm-certificates.crt")


# Application constants
SERVICE_COMMAND = "hook-service serve"
PORT = 8080
CERTIFICATES_PATH = Path("/etc/ssl/certs/")
CERTIFICATES_FILE = Path(CERTIFICATES_PATH / "ca-certificates.crt")

# Integration constants
INTERNAL_ROUTE_INTEGRATION_NAME = "internal-route"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
LOGGING_INTEGRATION_NAME = "logging"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"
TEMPO_TRACING_INTEGRATION_NAME = "tracing"
HYDRA_TOKEN_HOOK_INTEGRATION_NAME = "hydra-token-hook"
DATABASE_INTEGRATION_NAME = "pg-database"
OPENFGA_INTEGRATION_NAME = "openfga"
OPENFGA_STORE_NAME = "hook-service-store"
OPENFGA_MODEL_ID = "openfga_model_id"
PEER_INTEGRATION_NAME = "hook-service"
CERTIFICATE_TRANSFER_INTEGRATION_NAME = "receive-ca-cert"
