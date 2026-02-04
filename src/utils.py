# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions."""

import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from ops import ActiveStatus, BlockedStatus, StatusBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    OPENFGA_MODEL_ID,
    PEER_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import MigrationCheckError

if TYPE_CHECKING:
    from charm import HookServiceOperatorCharm

logger = logging.getLogger(__name__)

CharmEventHandler = TypeVar("CharmEventHandler", bound=Callable[..., Any])
Condition = Callable[["HookServiceOperatorCharm"], bool]


def leader_unit(func: CharmEventHandler) -> CharmEventHandler:
    """Validate unit leadership."""

    @wraps(func)
    def wrapper(charm: "HookServiceOperatorCharm", *args: Any, **kwargs: Any) -> Optional[Any]:
        if not charm.unit.is_leader():
            return None

        return func(charm, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def integration_existence(integration_name: str) -> Condition:
    """Integration existence condition factory."""

    def wrapped(charm: "HookServiceOperatorCharm") -> bool:
        return bool(charm.model.relations[integration_name])

    return wrapped


database_integration_exists = integration_existence(DATABASE_INTEGRATION_NAME)
peer_integration_exists = integration_existence(PEER_INTEGRATION_NAME)
openfga_integration_exists = integration_existence(OPENFGA_INTEGRATION_NAME)


def container_connectivity(charm: "HookServiceOperatorCharm") -> bool:
    """Check if charm can connect to the workload container."""
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()


def config_readiness(charm: "HookServiceOperatorCharm") -> bool:
    """Check if the charm config is ready."""
    return not charm._config.get_missing_config_keys()


def database_resource_is_created(charm: "HookServiceOperatorCharm") -> bool:
    return charm.database_requirer.is_resource_created()


def migration_is_ready(charm: "HookServiceOperatorCharm") -> bool:
    try:
        return not charm.migration_needed
    except MigrationCheckError:
        return False


def openfga_store_readiness(charm: "HookServiceOperatorCharm") -> bool:
    return charm.openfga_integration.is_store_ready()


def openfga_model_readiness(charm: "HookServiceOperatorCharm") -> bool:
    version = charm._workload_service.version

    if not (openfga_model := charm.peer_data[version]):
        return False

    return bool(openfga_model.get(OPENFGA_MODEL_ID))


def authentication_config_status(charm: "HookServiceOperatorCharm") -> StatusBase:
    """Check if the authentication is valid and return the proper status.

    Requirements:
    - If the OAuth integration exists, then the "authn_issuer" and "authn_jwks_url"
      config keys must be unset.
    - If the OAuth integration does not exist, then if any of the authn_* config keys
      are set, then the authn_issuer must be set.
    """
    oauth_config = charm._config.get_oauth_config()
    oauth_relation_ready = charm.oauth_integration.is_ready()

    if oauth_relation_ready and (
        oauth_config.get("authn_issuer") or oauth_config.get("authn_jwks_url")
    ):
        logger.error(
            "OAuth integration cannot be used with authn_issuer and authn_jwks_url config keys."
        )
        return ActiveStatus("Ignoring authentication config due to OAuth integration")

    if not oauth_relation_ready and (
        any(oauth_config.values()) and not oauth_config.get("authn_issuer")
    ):
        logger.error("authn_issuer config key must be set when using authentication config.")
        return BlockedStatus("Invalid authentication configuration")

    return ActiveStatus()


def authentication_config_is_valid(charm: "HookServiceOperatorCharm") -> bool:
    status = authentication_config_status(charm)
    return isinstance(status, ActiveStatus)


# Condition failure causes early return without doing anything
NOOP_CONDITIONS: tuple[Condition, ...] = (
    container_connectivity,
    database_integration_exists,
    database_resource_is_created,
    config_readiness,
    openfga_integration_exists,
    authentication_config_is_valid,
)
