# Proposal

## Why

The Hook Service runs a gRPC server on TCP port `9090` to stream group mappings, while the charm currently exposes only HTTP port `8080`. Exposing port `9090` through Kubernetes and an internal Traefik ingress controller lets in-cluster and cross-cluster clients reach the gRPC endpoint.

## What Changes

- Open TCP port `9090` on each Hook Service unit so the Kubernetes Service exposes gRPC traffic alongside HTTP port `8080`.
- Add an optional `grpc-route` relation (`traefik_route` interface, limit `1`) to publish TCP routing rules to an internal Traefik controller.
- Configure Traefik with a `grpc` entrypoint on port `9090` and a wildcard `HostSNI(*)` TCP route that terminates TLS and forwards plaintext `h2c`.
- Export `grpc-route` in the Terraform module `requires` output map.

## Non-goals

- Do not add the `groups-api` relation or dynamic `AUTHENTICATION_ALLOWED_SUBJECTS` updates in this change.
- Do not add custom SNI domain configuration or cleartext TCP ingress on Traefik.
- Do not implement Istio Gateway API `GRPCRoute` support in Phase 1.

## Capabilities

### New Capabilities
- `grpc-route-integration`: Exposes the gRPC service port on the cluster service and publishes TLS-terminated TCP routing configuration to an internal Traefik ingress controller.

### Modified Capabilities

## Workload Data Provenance

| Environment Variable | Source | Change |
| --- | --- | --- |
| *(None)* | Workload default (`GRPC_PORT=9090`) | No change. |

This change modifies no container environment variables because `hook-service` listens on `GRPC_PORT=9090` by default.

## Success Metrics

- In-cluster gRPC clients connect directly to the Kubernetes Service on TCP port `9090`.
- Cross-cluster gRPC clients connect over TLS (`ALPN: h2`) to the internal Traefik port `9090` and reach the Hook Service gRPC server.
- Existing deployments that use only `internal-route` continue to serve HTTP traffic without regression.

## Impact

- `charmcraft.yaml` and `terraform/outputs.tf` add the optional `grpc-route` relation endpoint.
- The charm runtime opens TCP port `9090` and submits static and dynamic TCP route configurations to Traefik.
