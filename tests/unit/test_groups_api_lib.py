# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import uuid

import pytest
from charms.hook_service.v0.groups_api import (
    LIBAPI,
    LIBID,
    LIBPATCH,
    GroupsApiDataValidationError,
    GroupsApiProvider,
    GroupsApiProviderData,
    GroupsApiReadyEvent,
    GroupsApiRequirer,
    GroupsApiRequirerData,
    GroupsApiSubjectChangedEvent,
    GroupsApiUnavailableEvent,
)
from ops import CharmBase, testing


class _ProviderCharm(CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self.groups_api = GroupsApiProvider(self)
        self.events_seen: list[str] = []
        self.framework.observe(self.groups_api.on.ready, self._on_ready)
        self.framework.observe(self.groups_api.on.subject_changed, self._on_subject_changed)
        self.framework.observe(self.groups_api.on.unavailable, self._on_unavailable)

    def _on_ready(self, event: GroupsApiReadyEvent) -> None:
        self.events_seen.append("ready")

    def _on_subject_changed(self, event: GroupsApiSubjectChangedEvent) -> None:
        self.events_seen.append("subject_changed")

    def _on_unavailable(self, event: GroupsApiUnavailableEvent) -> None:
        self.events_seen.append("unavailable")


class _RequirerCharm(CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self.groups_api = GroupsApiRequirer(self, subject="jaas-client-id")
        self.events_seen: list[str] = []
        self.framework.observe(self.groups_api.on.ready, self._on_ready)
        self.framework.observe(self.groups_api.on.unavailable, self._on_unavailable)

    def _on_ready(self, event: GroupsApiReadyEvent) -> None:
        self.events_seen.append("ready")

    def _on_unavailable(self, event: GroupsApiUnavailableEvent) -> None:
        self.events_seen.append("unavailable")


PROVIDER_META = {
    "name": "hook-service",
    "provides": {"groups-api": {"interface": "groups_api"}},
}

REQUIRER_META = {
    "name": "jaas",
    "requires": {"groups-api": {"interface": "groups_api", "limit": 1}},
}


def test_library_metadata() -> None:
    parsed = uuid.UUID(LIBID, version=4)
    assert parsed.hex == LIBID
    assert LIBAPI == 0
    assert LIBPATCH >= 1


def test_databag_models_validation_and_serialization() -> None:
    provider_data = GroupsApiProviderData.model_validate({
        "grpc_address": "hook-service.model.svc.cluster.local:9090",
        "tls_enabled": "false",
    })
    assert provider_data.tls_enabled is False
    assert provider_data.model_dump(mode="json") == {
        "grpc_address": "hook-service.model.svc.cluster.local:9090",
        "tls_enabled": "false",
    }

    with pytest.raises(ValueError):
        GroupsApiProviderData(grpc_address="   ", tls_enabled=True)

    with pytest.raises(ValueError):
        GroupsApiRequirerData(subject="   ")


def test_provider_collects_subjects_and_publishes_on_leader() -> None:
    ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
    rel1 = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="jaas",
        remote_app_data={"subject": "jaas-sub"},
    )
    rel2 = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="other-app",
        remote_app_data={"subject": "alpha-sub"},
    )
    rel_empty = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="pending-app",
        remote_app_data={"subject": "   "},
    )

    state_in = testing.State(relations=[rel1, rel2, rel_empty], leader=True)
    with ctx(ctx.on.relation_changed(rel1), state_in) as mgr:
        assert mgr.charm.groups_api.get_allowed_subjects() == ["alpha-sub", "jaas-sub"]
        mgr.charm.groups_api.update_relations_app_data(
            grpc_address="grpc.example.com:9090",
            tls_enabled=True,
        )
        state_out = mgr.run()
        assert mgr.charm.events_seen == ["subject_changed"]
    for rel in (rel1, rel2, rel_empty):
        assert state_out.get_relation(rel.id).local_app_data == {
            "grpc_address": "grpc.example.com:9090",
            "tls_enabled": "true",
        }


def test_provider_non_leader_skips_databag_writes() -> None:
    ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
    rel = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="jaas",
        remote_app_data={"subject": "jaas-sub"},
    )
    state_in = testing.State(relations=[rel], leader=False)
    with ctx(ctx.on.relation_changed(rel), state_in) as mgr:
        mgr.charm.groups_api.update_relations_app_data(
            grpc_address="grpc.example.com:9090",
            tls_enabled=False,
        )
        state_out = mgr.run()

    assert state_out.get_relation(rel.id).local_app_data == {}


def test_provider_emits_ready_and_unavailable() -> None:
    ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
    rel = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="jaas",
    )
    with ctx(ctx.on.relation_created(rel), testing.State(relations=[rel], leader=True)) as mgr:
        mgr.run()
        assert mgr.charm.events_seen == ["ready"]

    with ctx(ctx.on.relation_broken(rel), testing.State(relations=[rel], leader=True)) as mgr:
        mgr.run()
        assert mgr.charm.events_seen == ["unavailable"]
        assert mgr.charm.groups_api.get_allowed_subjects() == []


def test_requirer_publishes_subject_and_reads_grpc_info() -> None:
    ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
    rel = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="hook-service",
    )
    state_out = ctx.run(ctx.on.relation_created(rel), testing.State(relations=[rel], leader=True))
    assert state_out.get_relation(rel.id).local_app_data == {"subject": "jaas-client-id"}

    rel_with_data = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="hook-service",
        remote_app_data={
            "grpc_address": "hook-service.model.svc.cluster.local:9090",
            "tls_enabled": "false",
        },
    )
    with ctx(
        ctx.on.relation_changed(rel_with_data),
        testing.State(relations=[rel_with_data], leader=True),
    ) as mgr:
        info = mgr.charm.groups_api.get_grpc_info()
        assert info == GroupsApiProviderData(
            grpc_address="hook-service.model.svc.cluster.local:9090",
            tls_enabled=False,
        )
        mgr.run()
        assert mgr.charm.events_seen == ["ready"]


def test_requirer_invalid_provider_data_raises_validation_error() -> None:
    ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
    rel = testing.Relation(
        endpoint="groups-api",
        interface="groups_api",
        remote_app_name="hook-service",
        remote_app_data={"grpc_address": "host:9090", "tls_enabled": "not-a-bool"},
    )
    with ctx(ctx.on.relation_changed(rel), testing.State(relations=[rel], leader=True)) as mgr:
        mgr.run()
        assert mgr.charm.events_seen == []
        with pytest.raises(GroupsApiDataValidationError):
            mgr.charm.groups_api.get_grpc_info()
