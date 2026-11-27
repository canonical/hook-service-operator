# Tasks

## 1. Metadata, Constants, and Terraform Contracts

- [x] 1.1 Add optional `grpc-route` relation in `charmcraft.yaml` and verify valid YAML structure.
- [x] 1.2 Add `grpc-route` to the `requires` output map in `terraform/outputs.tf` and verify the key matches `charmcraft.yaml`.
- [x] 1.3 Add `GRPC_ROUTE_INTEGRATION_NAME` to `src/constants.py` and verify the pre-existing `GRPC_PORT = 9090` (landed in `f6ba1cda3`); verify module import succeeds.

## 2. Workload Port Exposure (`pebble-ready`)

- [x] 2.1 Verify `WorkloadService.open_port()` in `src/services.py` already opens `GRPC_PORT` alongside `PORT` (landed in `f6ba1cda3`); no change needed in this change.
- [x] 2.2 Add `pebble-ready` unit tests in `tests/unit/test_charm.py` for TCP ports `8080` and `9090` and verify with `tox -e unit`.

## 3. Traefik TCP Route Template and Integration Wrapper

- [x] 3.1 Create `templates/grpc-route.json.j2` with `HostSNI(*)` TCP router and service without `proxyProtocol` and verify valid JSON rendering.
- [x] 3.2 Create `GrpcRouteIntegration` in `src/integrations.py` to submit static `:9090` entrypoint and dynamic TCP config and verify lint passes.
- [x] 3.3 Add unit tests in `tests/unit/test_integrations.py` for `GrpcRouteIntegration` leader submission and non-leader skip and verify with `tox -e unit`.

## 4. Charm `grpc-route` Relation Reconciliation

- [x] 4.1 Register `GrpcRouteIntegration` events and `_ensure_grpc_ingress` inside `_holistic_handler` in `src/charm.py` and verify `tox -e lint` passes.
- [x] 4.2 Add unit tests in `tests/unit/conftest.py` and `tests/unit/test_charm.py` for `grpc-route` join, change, broken, and `internal-route` coexistence via `tox -e unit`.
- [x] 4.3 Add integration tests in `tests/integration/test_charm.py` for `grpc-route` relation, port `9090` routing, and removal recovery via `tox -e integration`.

## 5. Documentation and Rollout

- [x] 5.1 Document internal Traefik `grpc-route` usage and rollout steps in `README.md` and verify command examples match `charmcraft.yaml`.

## 6. Verification Suite

- [x] 6.1 Run `tox -e lint` and `tox -e unit` across `src/` and `tests/` and verify zero errors.
- [x] 6.2 Run `openspec validate expose-grpc-route --strict` on `openspec/changes/expose-grpc-route/` and verify zero validation issues.

## Implementation Notes

- The `v1.4.0` workload image bump this change depends on (earlier images do not listen on gRPC port `9090`) moved to the stacked upgrade PR (#255) during review; this branch no longer bumps the image. `trust=True` was added to the `hook-service` deploy in `tests/integration/test_charm.py` because `KubernetesComputeResourcesPatch` requires cluster access.
- Verified integration tests on local `k0s-ctrl` controller using `.tox/integration/bin/pytest tests/integration` with `CHARM_PATH` (11 passed, 3 skipped in `test_upgrade.py`), bypassing `tox -e build-prerequisites` (`sudo apt-get`) since prerequisites were already installed.

## Workflow follow-up

- Archive the change with `/openspec-archive-change` after implementation and review complete.
