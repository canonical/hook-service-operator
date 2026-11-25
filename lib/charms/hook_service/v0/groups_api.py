# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for the Hook Service `groups-api` relation.

This library wraps the `groups_api` interface between `hook-service` (provider)
and gRPC consumer charms such as JAAS (requirer).

## Provider usage

```python
from charms.hook_service.v0.groups_api import GroupsApiProvider


class HookServiceCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.groups_api = GroupsApiProvider(self)
```

## Requirer usage

```python
from charms.hook_service.v0.groups_api import GroupsApiRequirer


class ConsumerCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.groups_api = GroupsApiRequirer(self, subject="my-oidc-client-id")
```
"""

from __future__ import annotations

import logging
from typing import List, Optional, Union

from ops import (
    CharmBase,
    Object,
    ObjectEvents,
    Relation,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    RelationDepartedEvent,
    RelationEvent,
)
from ops.framework import EventSource
from pydantic import BaseModel, StrictBool, ValidationError, field_serializer, field_validator

LIBID = "76420a99ce3a461e8923b5972dc6ce9c"
LIBAPI = 0
LIBPATCH = 1

PYDEPS = ["pydantic"]

RELATION_NAME = "groups-api"
INTERFACE_NAME = "groups_api"

logger = logging.getLogger(__name__)


class GroupsApiError(RuntimeError):
    """Base exception raised by the groups-api interface library."""


class GroupsApiDataValidationError(GroupsApiError):
    """Raised when databag content fails Pydantic validation."""


class GroupsApiProviderData(BaseModel):
    """Validated data published by the groups-api provider."""

    grpc_address: str
    tls_enabled: StrictBool

    @field_validator("grpc_address")
    @classmethod
    def _validate_grpc_address(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("grpc_address must not be empty")
        return stripped

    @field_validator("tls_enabled", mode="before")
    @classmethod
    def _deserialize_tls_enabled(cls, value: Union[str, bool]) -> Union[str, bool]:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        return value

    @field_serializer("tls_enabled")
    def _serialize_tls_enabled(self, value: bool) -> str:
        return str(value).lower()


class GroupsApiRequirerData(BaseModel):
    """Validated data published by a groups-api requirer."""

    subject: str

    @field_validator("subject")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("subject must not be empty")
        return stripped


class GroupsApiReadyEvent(RelationEvent):
    """Event emitted when a groups-api relation is ready."""


class GroupsApiSubjectChangedEvent(RelationEvent):
    """Event emitted when a consumer's subject state may have changed."""


class GroupsApiUnavailableEvent(RelationEvent):
    """Event emitted when a groups-api relation becomes unavailable."""


class GroupsApiProviderEvents(ObjectEvents):
    """Events emitted by `GroupsApiProvider`."""

    ready = EventSource(GroupsApiReadyEvent)
    subject_changed = EventSource(GroupsApiSubjectChangedEvent)
    unavailable = EventSource(GroupsApiUnavailableEvent)


class GroupsApiRequirerEvents(ObjectEvents):
    """Events emitted by `GroupsApiRequirer`."""

    ready = EventSource(GroupsApiReadyEvent)
    unavailable = EventSource(GroupsApiUnavailableEvent)


class GroupsApiProvider(Object):
    """Provider side of the `groups-api` relation."""

    on = GroupsApiProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_departed, self._on_relation_departed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    @property
    def active_relations(self) -> List[Relation]:
        """All active relations for this endpoint."""
        return [
            relation
            for relation in self._charm.model.relations.get(self._relation_name, [])
            if relation.active and relation.app is not None
        ]

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit(event.relation, app=event.relation.app)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        self.on.subject_changed.emit(event.relation, app=event.relation.app)

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        self.on.subject_changed.emit(event.relation, app=event.relation.app)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.on.unavailable.emit(event.relation, app=event.relation.app)

    def get_allowed_subjects(self) -> List[str]:
        """Collect sorted, deduplicated OIDC subjects across all active relations."""
        subjects = set()
        for relation in self.active_relations:
            assert relation.app is not None
            raw_data = dict(relation.data.get(relation.app, {}))
            if not raw_data or "subject" not in raw_data:
                continue
            try:
                requirer_data = GroupsApiRequirerData.model_validate(raw_data)
            except ValidationError as exc:
                logger.warning(
                    "Ignoring invalid groups-api requirer data on relation %s: %s",
                    relation.id,
                    exc,
                )
                continue
            subjects.add(requirer_data.subject)
        return sorted(subjects)

    def update_relations_app_data(
        self,
        grpc_address: str,
        tls_enabled: bool,
        relation_id: Optional[int] = None,
    ) -> None:
        """Publish gRPC endpoint data to active relations from the leader unit."""
        if not self._charm.unit.is_leader():
            return

        payload = GroupsApiProviderData(
            grpc_address=grpc_address,
            tls_enabled=tls_enabled,
        ).model_dump(mode="json")

        for relation in self.active_relations:
            if relation_id is not None and relation.id != relation_id:
                continue
            relation.data[self._charm.app].update(payload)


class GroupsApiRequirer(Object):
    """Requirer side of the `groups-api` relation."""

    on = GroupsApiRequirerEvents()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = RELATION_NAME,
        subject: Optional[str] = None,
    ) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._subject = subject

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    @property
    def active_relations(self) -> List[Relation]:
        """All active relations for this endpoint."""
        return [
            relation
            for relation in self._charm.model.relations.get(self._relation_name, [])
            if relation.active and relation.app is not None
        ]

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        if self._subject is not None:
            self.publish_subject(self._subject, relation_id=event.relation.id)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        try:
            if self.get_grpc_info(relation_id=event.relation.id) is not None:
                self.on.ready.emit(event.relation, app=event.relation.app)
        except GroupsApiDataValidationError as exc:
            logger.warning("%s", exc)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.on.unavailable.emit(event.relation, app=event.relation.app)

    def publish_subject(self, subject: str, relation_id: Optional[int] = None) -> None:
        """Publish the consumer OIDC subject to active relation databags on the leader unit."""
        if not self._charm.unit.is_leader():
            return

        payload = GroupsApiRequirerData(subject=subject).model_dump(mode="json")
        for relation in self.active_relations:
            if relation_id is not None and relation.id != relation_id:
                continue
            relation.data[self._charm.app].update(payload)

    def get_grpc_info(self, relation_id: Optional[int] = None) -> Optional[GroupsApiProviderData]:
        """Return validated provider gRPC endpoint data, or None if not yet published."""
        relation = self._charm.model.get_relation(self._relation_name, relation_id)
        if not relation or not relation.active or not relation.app:
            return None

        raw_data = dict(relation.data.get(relation.app, {}))
        if not raw_data:
            return None

        try:
            return GroupsApiProviderData.model_validate(raw_data)
        except ValidationError as exc:
            raise GroupsApiDataValidationError(
                f"Invalid groups-api provider data on relation {relation.id}: {exc}"
            ) from exc
