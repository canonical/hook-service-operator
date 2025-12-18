# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.application.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    logging        = "logging"
    tracing        = "tracing"
    openfga        = "openfga"
    pg-database    = "pg-database"
    internal-route = "internal-route"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    hydra-token-hook  = "hydra-token-hook"
    metrics-endpoint  = "metrics-endpoint"
    grafana-dashboard = "grafana-dashboard"
  }
}
