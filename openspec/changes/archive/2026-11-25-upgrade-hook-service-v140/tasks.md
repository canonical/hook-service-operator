# Tasks

## 1. Metadata & image bump

- [x] 1.1 Bump `charmcraft.yaml` `resources.oci-image.upstream-source` to `ghcr.io/canonical/hook-service:v1.4.0`.

## 2. Integrations

- [x] 2.1 Rewrite `TenantServiceInfoData` in `src/integrations.py`: replace `service_url` with `grpc_url`, read databag key `grpc_url`, emit `TENANT_SERVICE_GRPC_ADDRESS` (scheme-stripped) and `TENANT_SERVICE_TLS_ENABLED` in `to_env_vars`.

## 3. Env defaults

- [x] 3.1 Replace the `TENANT_SERVICE_URL` entry in `src/env_vars.py::DEFAULT_CONTAINER_ENV` with `TENANT_SERVICE_GRPC_ADDRESS` (empty), `TENANT_SERVICE_TLS_ENABLED` (false), `TENANT_SERVICE_GRPC_TIMEOUT` (`5s`).

## 4. Charm readiness flag

- [x] 4.1 Change `src/charm.py::_ensure_hydra_relation` to key `tenant_service_ready` on `TenantServiceInfoData.load(self.model).grpc_url`.

## 5. Unit tests

- [x] 5.1 Update `TestHolisticHandler::test_when_all_conditions_satisfied` env dict for the new keys.
- [x] 5.2 Rename `test_tenant_service_url_from_relation` → `test_tenant_service_grpc_env_from_relation`; assert gRPC address/TLS/timeout from `grpc_url`.
- [x] 5.3 Add `test_tenant_service_grpc_tls_from_https_scheme` (https scheme → TLS true).

## 6. Verification

- [x] 6.1 `tox -e fmt && tox -e lint && tox -e unit` all green.
- [x] 6.2 `openspec validate upgrade-hook-service-v140 --strict` passes.
- [x] 6.3 Local integration suite on k8s: 9 passed, 3 skipped, 0 failed — `hook-service/0` active with workload version 1.4.0.

## 7. Docs & archive

- [x] 7.1 Sync `openspec/specs/tenant-service-grpc-connection/spec.md` in main-spec format, `openspec validate --specs --strict`, archive the change with date prefix, confirm `openspec list --json` is empty.

## Implementation Notes

- Deviation: the CLI rejected dots in change names, so the change is `upgrade-hook-service-v140` instead of `upgrade-hook-service-v1.4.0`.
- Local integration run required `juju trust hook-service --scope=cluster` granted externally right after deploy: `KubernetesComputeResourcesPatch` needs cluster access and this branch's integration suite deploys `hook-service` without `--trust` (PR #253's test commit adds it). With trust granted, all 12 tests in the suite ran (`9 passed, 3 skipped`, with all 3 skips in `test_upgrade.py`, so the charm upgrade path was not exercised locally; 2 additional `grpc-route` integration tests live on `feat/expose-grpc-route`).
