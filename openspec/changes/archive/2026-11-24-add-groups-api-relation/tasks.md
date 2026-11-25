# Tasks

## 1. Charm Library (`charms.hook_service.v0.groups_api`)

- [x] 1.1 Create `lib/charms/hook_service/v0/groups_api.py` with `GroupsApiProvider`, `GroupsApiRequirer`, Pydantic v2 databag models (`subject`, `grpc_address`, `tls_enabled`), and a UUIDv4 `LIBID`, verifying imports succeed under Python 3.10+.
- [x] 1.2 Add unit tests in `tests/unit/test_groups_api_lib.py` covering provider/requirer databag serialization, multi-relation subject extraction, empty/invalid subject handling, non-leader skip, and event emission via `tox -e unit`.

## 2. Metadata, Constants, and Terraform Contracts

- [x] 2.1 Add optional one-to-many `groups-api` (`interface: groups_api`) under `provides` in `charmcraft.yaml` and verify valid YAML structure.
- [x] 2.2 Add `groups-api = "groups-api"` to the `provides` output map in `terraform/outputs.tf` and verify `terraform fmt -check` and `terraform validate` pass.
- [x] 2.3 Define `GROUPS_API_INTEGRATION_NAME = "groups-api"` in `src/constants.py` and verify module import succeeds.

## 3. Endpoint Resolution, Auth Enforcement, and Subject Merging

- [x] 3.1 Add `GroupsApiIntegration` and extend `OAuthProviderData` / `OAuthIntegration` subject merging in `src/integrations.py` to resolve `{grpc_address, tls_enabled}` from `model.get_relation("grpc-route")` and deduplicate sorted subjects, verifying `tox -e lint` passes.
- [x] 3.2 Update `authentication_config_status` and add `groups-api` / `grpc-route` readiness status helpers in `src/utils.py` to require auth when `groups-api` is active, verifying `tox -e lint` passes.
- [x] 3.3 Add unit tests in `tests/unit/test_integrations.py` covering `GroupsApiIntegration` in-cluster vs `grpc-route` endpoint resolution, withheld writes when `external_host` is empty, and deduplicated subject merging via `tox -e unit`.

## 4. Charm Reconciliation and Status Handling

- [x] 4.1 Instantiate `GroupsApiIntegration`, observe `groups-api` events (`relation_created`, `relation_changed`, `relation_departed`, `relation_broken`), enforce auth/ingress gating in `_ensure_groups_api_relation` within `_holistic_handler`, pass merged subjects to `_pebble_layer`, and report waiting/blocked states in `_on_collect_status` in `src/charm.py`, verifying `tox -e lint` passes.
- [x] 4.2 Add unit tests in `tests/unit/conftest.py` and `tests/unit/test_charm.py` covering `groups-api` join, multi-consumer subject merge, departure/broken subject removal, `grpc-route` coexistence/removal, unauthenticated `BlockedStatus`, pending OAuth `WaitingStatus`, and non-leader skip via `tox -e unit`.
- [x] 4.3 Add integration tests in `tests/integration/test_charm.py` (with any helper requirer setup if needed) covering `groups-api` endpoint publication and `AUTHENTICATION_ALLOWED_SUBJECTS` updates via `tox -e integration`.

## 5. Documentation and Rollout

- [x] 5.1 Document `groups-api` integration, required authentication (`oauth` or `authn_issuer`), optional `grpc-route` pairing for cross-cluster JAAS consumers, and rollout/rollback steps in `README.md`, verifying commands match `charmcraft.yaml`.

## 6. Verification Suite

- [x] 6.1 Run `tox -e fmt`, `tox -e lint`, and `tox -e unit` across `src/`, `lib/charms/hook_service/`, and `tests/` and verify zero errors.
- [x] 6.2 Run `openspec validate add-groups-api-relation --strict` on `openspec/changes/add-groups-api-relation/` and verify zero validation issues.

## Implementation Notes

- Task 4.3 builds a minimal containerless requirer charm zip (`metadata.yaml`, `manifest.yaml`, executable hooks) at test time in `tests/integration/test_charm.py`, and reads the live Pebble plan on `hook-service/0` via a raw `socket` one-liner against `/charm/containers/hook-service/pebble.socket` (the unit container lacks the `ops` package outside the charm venv path).
- Integration suite verified on local `k0s-ctrl` Juju controller: 12 passed, 3 skipped (`tests/integration/test_upgrade.py`), including `test_groups_api_relation` (auth-gate `blocked` state, `public:9090` TLS endpoint publication, allowed-subjects in live Pebble plan, and in-cluster fallback after `grpc-route` removal).

## Workflow follow-up

- Archive the change with `/openspec-archive-change` after implementation and review complete.
