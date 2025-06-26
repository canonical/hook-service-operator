# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Exceptions."""


class CharmError(Exception):
    """Base class for custom charm errors."""


class InvalidSalesforceConfig(CharmError):
    """Error for invalid salesforce config."""


class PebbleError(CharmError):
    """Error for pebble related operations."""
