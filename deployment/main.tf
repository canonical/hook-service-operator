terraform {
  required_providers {
    juju = {
      version = ">= 0.15.0"
      source  = "juju/juju"
    }
  }
}

variable "client_id" {
  type      = string
  sensitive = true
}

variable "client_secret" {
  type      = string
  sensitive = true
}

variable "jimm_url" {
  type = string
}

variable "model" {
  type = string
}

variable "charm" {
  description = "The configurations of the application."
  type = object({
    units  = optional(number, 1)
    base   = optional(string, "ubuntu@22.04")
    trust  = optional(string, true)
    config = optional(map(string), {})
  })
  default = {}
}

variable "application_name" {
  type = string
}

variable "revision" {
  type = number
}

variable "channel" {
  type = string
}

provider "juju" {
  controller_addresses = var.jimm_url

  client_id     = var.client_id
  client_secret = var.client_secret

}

data "juju_secret" "salesforce_consumer_secret" {
  // The secret is created when we deploy the service. The name must be
  // the same with whatever we have in
  // https://github.com/canonical/cd-identity-core-infrastructure/blob/main/modules/hook_service/main.tf
  name  = "hook_service_salesforce_credentials"
  model = var.model
}

module "application" {
  source                           = "../terraform"
  model_name                       = var.model
  app_name                         = var.application_name
  units                            = var.charm.units
  base                             = var.charm.base
  config                           = var.charm.config
  salesforce_credentials_secret_id = sensitive(data.juju_secret.salesforce_consumer_secret.secret_id)
  channel                          = var.channel
  revision                         = var.revision
}
