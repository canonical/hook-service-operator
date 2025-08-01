# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants."""

# Charm constants
WORKLOAD_CONTAINER = "hook-service"
WORKLOAD_SERVICE = "hook-service"
PEBBLE_READY_CHECK_NAME = "ready"
API_TOKEN_SECRET_KEY = "api-token"
API_TOKEN_SECRET_LABEL = "apitokensecret"
CONFIG_CONSUMER_KEY_SECRET_KEY = "consumer-key"
CONFIG_CONSUMER_SECRET_SECRET_KEY = "consumer-secret"

# Application constants
SERVICE_COMMAND = "hook-service serve"
PORT = 8080

# Integration constants
INGRESS_INTEGRATION_NAME = "ingress"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
LOGGING_INTEGRATION_NAME = "logging"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"
TEMPO_TRACING_INTEGRATION_NAME = "tracing"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
HYDRA_TOKEN_HOOK_INTEGRATION_NAME = "hydra-token-hook"
