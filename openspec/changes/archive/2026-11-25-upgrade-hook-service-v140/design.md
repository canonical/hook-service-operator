# Design

## Context

The v1.4.0 workload reads `TENANT_SERVICE_GRPC_ADDRESS` (passed to `grpc.NewClient`, which needs a bare `host:port`, not a URL), `TENANT_SERVICE_TLS_ENABLED` (selects TLS vs insecure credentials), and `TENANT_SERVICE_GRPC_TIMEOUT` (default `5s`). An empty address makes the workload use `NoopValidator` (tenant validation disabled) — identical to v1.3.1 with no `TENANT_SERVICE_URL`. Upstream `tenant-service-operator` currently publishes `grpc_url` as a scheme-less `host:port` (e.g. `tenant-service.<model>.svc.cluster.local:50051`), and `tenant_service_info` v0.2 does not mandate a URL scheme for `grpc_url`.

## Goals / Non-Goals

**Goals:**

- Upgrade the workload image to v1.4.0 while keeping tenant membership validation working.
- Derive gRPC address/TLS settings from the existing relation databag, with no new charm config.

**Non-Goals:**

- No `grpc-route`/`groups-api` wiring (separate PRs).
- No configurable gRPC timeout.
- No Istio work.

## Decisions

1. **Handle scheme-less `host:port` with `urlparse` tolerance**: address = `parsed.netloc` when non-empty, else the raw string. Because `urlparse` mis-splits scheme-less values (`tenant-service:50051` is parsed as scheme `tenant-service` with empty netloc), falling back to the raw string preserves the provider's scheme-less `host:port` verbatim while still tolerating URL-form `grpc_url` values (stripping `http://` / `https://` and enabling TLS on `https`). This satisfies `grpc.NewClient`'s bare-target requirement against both current and URL-style values.
2. **`TENANT_SERVICE_GRPC_TIMEOUT` is a constant** in `DEFAULT_CONTAINER_ENV`, not a charm config — it matches the workload default; a config option is future work if operators need tuning.
3. **`service_url` field/key removed entirely** (clean cutover — nothing else consumes it).

## Risks / Trade-offs

- Operators relying on `TENANT_SERVICE_URL` semantics must relate `tenant-service-info` with `grpc_url` set; without it, tenant validation stays disabled exactly as before. Alternatives considered: re-adding `TENANT_SERVICE_URL` (impossible — removed upstream); deferring the bump (blocks the grpc-route/groups-api stack).
- Against the current `tenant-service-operator` provider (which emits scheme-less `host:port`), `TENANT_SERVICE_TLS_ENABLED` remains `False` until the `tenant-service-info` interface exposes an explicit TLS flag (preferred over non-standard `grpc://`/`grpcs://` URI schemes).
- No DB schema changes.
