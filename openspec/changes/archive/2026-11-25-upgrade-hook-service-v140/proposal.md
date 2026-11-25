# Proposal

## Why

hook-service v1.4.0 brings the `GroupsMappingService` gRPC API that the upcoming `grpc-route` and `groups-api` PRs depend on, but it removed the `TENANT_SERVICE_URL` environment variable in favor of `TENANT_SERVICE_GRPC_ADDRESS`, `TENANT_SERVICE_GRPC_TIMEOUT` (default `5s`), and `TENANT_SERVICE_TLS_ENABLED` (default `false`). Upgrading the image without migrating the charm's env emission silently disables tenant membership validation (the workload falls back to `NoopValidator`) — the [High] review finding on PR #253.

## What Changes

- Bump `charmcraft.yaml` `resources.oci-image.upstream-source` to `ghcr.io/canonical/hook-service:v1.4.0`.
- Emit `TENANT_SERVICE_GRPC_ADDRESS` and `TENANT_SERVICE_TLS_ENABLED`, derived from the `tenant-service-info` relation's `grpc_url`.
- Emit `TENANT_SERVICE_GRPC_TIMEOUT=5s` (workload default) as a constant.
- Key the hydra-token-hook `tenant_service_ready` flag on `grpc_url` instead of `service_url`.

## Capabilities

### New Capabilities

- `tenant-service-grpc-connection`: publish the tenant-service gRPC connection settings to the workload environment and advertise tenant readiness on the hydra token hook.

## Workload Data Provenance

| Environment Variable | Source | Change |
| --- | --- | --- |
| `TENANT_SERVICE_GRPC_ADDRESS` | `tenant-service-info` relation `grpc_url` (scheme stripped) | new |
| `TENANT_SERVICE_TLS_ENABLED` | derived from `grpc_url` scheme (`https`/`grpcs` → true, else false) | new |
| `TENANT_SERVICE_GRPC_TIMEOUT` | constant `"5s"` (workload default) | new |
| `TENANT_SERVICE_URL` | removed upstream in v1.4.0 | dropped |

## Non-goals

- No changes to `grpc-route` or `groups-api` wiring — covered by separate PRs.
- No new charm config options.
- No Phase 2 Istio work.

## Success Metrics

With `tenant-service-info` related and `grpc_url` set, the workload starts with a gRPC tenant validator instead of `NoopValidator`. Without the relation, behavior matches v1.3.1 (validation disabled).
