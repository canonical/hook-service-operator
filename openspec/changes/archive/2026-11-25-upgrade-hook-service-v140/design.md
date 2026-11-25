# Design

## Context

The v1.4.0 workload reads `TENANT_SERVICE_GRPC_ADDRESS` (passed to `grpc.NewClient`, which needs a bare `host:port`, not a URL), `TENANT_SERVICE_TLS_ENABLED` (selects TLS vs insecure credentials), and `TENANT_SERVICE_GRPC_TIMEOUT` (default `5s`). An empty address makes the workload use `NoopValidator` (tenant validation disabled) — identical to v1.3.1 with no `TENANT_SERVICE_URL`. The `tenant-service-info` provider publishes `grpc_url` in URL form (e.g. `http://tenant-service:50051`).

## Goals / Non-Goals

**Goals:**

- Upgrade the workload image to v1.4.0 while keeping tenant membership validation working.
- Derive gRPC address/TLS settings from the existing relation databag, with no new charm config.

**Non-Goals:**

- No `grpc-route`/`groups-api` wiring (separate PRs).
- No configurable gRPC timeout.
- No Istio work.

## Decisions

1. **Parse `grpc_url` with `urlparse`**: address = `parsed.netloc` when non-empty, else the raw string. `urlparse` mis-splits scheme-less values (`tenant-service:50051` is parsed as scheme `tenant-service` with empty netloc), so falling back to the raw string handles them verbatim. TLS is derived from scheme membership in `("https", "grpcs")`. This matches `grpc.NewClient`'s bare-target requirement and the library's documented URL-style `grpc_url`.
2. **`TENANT_SERVICE_GRPC_TIMEOUT` is a constant** in `DEFAULT_CONTAINER_ENV`, not a charm config — it matches the workload default; a config option is future work if operators need tuning.
3. **`service_url` field/key removed entirely** (clean cutover — nothing else consumes it).

## Risks / Trade-offs

- Operators relying on `TENANT_SERVICE_URL` semantics must relate `tenant-service-info` with `grpc_url` set; without it, tenant validation stays disabled exactly as before. Alternatives considered: re-adding `TENANT_SERVICE_URL` (impossible — removed upstream); deferring the bump (blocks the grpc-route/groups-api stack).
- No DB schema changes.
