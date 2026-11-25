# Proposal

## Why

External and in-cluster consumers such as JAAS need a relation to discover the Hook Service gRPC endpoint and authorize their OIDC client identities automatically. Currently, operators must manage static subject allowlists and manually track whether consumers connect directly or through Traefik TLS ingress.

## What Changes

- Add an optional one-to-many `groups-api` relation (`provides`, interface `groups_api`) with a new `v0` charm library (`charms.hook_service.v0.groups_api`).
- Collect OIDC `subject` IDs from all active `groups-api` consumers and merge them into `AUTHENTICATION_ALLOWED_SUBJECTS` alongside configured subjects and the OAuth client ID.
- Publish `grpc_address` (`host:port`) and `tls_enabled` to each `groups-api` consumer, resolving to Traefik's external host on `:9090` with TLS when `grpc-route` is active, or the Kubernetes service FQDN on `:9090` without TLS otherwise.
- Require JWT authentication (`oauth` relation or `authn_issuer` config) whenever `groups-api` has active consumers, blocking or waiting and withholding endpoint data until authentication is ready.
- Export `groups-api` in the Terraform module `provides` output map.

## Non-goals

- Do not use `use_ingress_for_relations` for gRPC endpoints; that setting stays HTTP-only.
- Do not implement Phase 2 Istio Gateway API (`istio-ingress-route` / `GRPCRoute`) support in this change.
- Do not change Charmhub library publishing pipelines or register a Charmhub library ID.

## Capabilities

### New Capabilities
- `groups-api-integration`: Provides the `groups-api` relation contract, dynamic subject allowlisting, authentication enforcement, and gRPC endpoint resolution for consumers.

### Modified Capabilities

## Workload Data Provenance

| Environment Variable | Source | Change |
| --- | --- | --- |
| `AUTHENTICATION_ALLOWED_SUBJECTS` | Config `authn_allowed_subjects`, `oauth` `client_id`, and active `groups-api` requirer `subject` values | Appends sorted, deduplicated consumer subjects when auth is configured. |

## Success Metrics

- JAAS and in-cluster consumers integrate with `hook-service:groups-api`, send an OIDC `subject`, and receive the matching `grpc_address` and `tls_enabled` state.
- Departing `groups-api` consumers have their subject removed from `AUTHENTICATION_ALLOWED_SUBJECTS` on relation removal.
- Unauthenticated `groups-api` deployments enter `BlockedStatus` or `WaitingStatus` and never expose an unauthenticated gRPC target.

## Impact

- `charmcraft.yaml` and `terraform/outputs.tf` declare the `groups-api` provider endpoint.
- `lib/charms/hook_service/v0/groups_api.py` defines the `v0` library for Hook Service and consumers such as `jimm-k8s-operator`.
- `src/charm.py`, `src/integrations.py`, and `src/utils.py` reconcile consumer subjects, endpoint resolution, and unit status.
