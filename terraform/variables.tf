# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_name" {
  description = "The Juju model name"
  type        = string
}

variable "app_name" {
  description = "The Juju application name"
  type        = string
}

variable "config" {
  description = "The charm config"
  type        = map(string)
  default     = {}
}

variable "constraints" {
  description = "The constraints to be applied"
  type        = string
  default     = "arch=amd64"
}

variable "units" {
  description = "The number of units"
  type        = number
  default     = 1
}

variable "base" {
  description = "The charm base"
  type        = string
  default     = "ubuntu@22.04"
}

variable "channel" {
  description = "The charm channel"
  type        = string
  default     = "latest/edge"
}

variable "revision" {
  description = "The charm revision"
  type        = number
  nullable    = true
  default     = null
}

variable "salesforce_credentials_secret_id" {
  description = "The juju secret with credentials for calling the Salesforce API."
  type        = string
  sensitive   = true
}
