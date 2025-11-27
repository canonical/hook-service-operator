# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions."""

import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from constants import (
    INGRESS_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)

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


def container_connectivity(charm: "HookServiceOperatorCharm") -> bool:
    """Check if charm can connect to the workload container."""
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()


def config_readiness(charm: "HookServiceOperatorCharm") -> bool:
    """Check if the charm config is ready."""
    return not charm._config.get_missing_config_keys()


def database_resource_is_created(charm: "HookServiceOperatorCharm") -> bool:
    return charm.database_requirer.is_resource_created()


def migration_is_ready(charm: "HookServiceOperatorCharm") -> bool:
    return not charm.migration_needed


ingress_integration_exists = integration_existence(INGRESS_INTEGRATION_NAME)


# Condition failure causes early return without doing anything
NOOP_CONDITIONS: tuple[Condition, ...] = (
    container_connectivity,
    config_readiness,
)
