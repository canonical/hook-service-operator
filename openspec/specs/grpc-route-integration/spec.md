# grpc-route-integration Specification

## Purpose

Exposes the Hook Service gRPC endpoint on TCP port `9090` within Kubernetes and configures TLS-terminated TCP routing through an internal Traefik ingress controller. This capability requires the `hook-service` workload image `v1.4.0` or later; earlier images do not listen on `:9090`.

## Requirements

### Requirement: Open the gRPC service port on units
The charm SHALL open TCP port `9090` alongside TCP port `8080` when the workload container becomes ready.

#### Scenario: Workload container starts
- **WHEN** the workload container connects and emits its readiness event
- **THEN** the charm opens TCP ports `8080` and `9090` on the unit so the Kubernetes Service routes gRPC traffic

### Requirement: Declare the optional grpc-route integration
The charm SHALL declare an optional `grpc-route` relation endpoint that requires the `traefik_route` interface with a limit of `1`. The Terraform module SHALL map the endpoint name in its `requires` output.

#### Scenario: Operator inspects charm metadata
- **WHEN** an operator inspects the charm metadata `requires` map
- **THEN** it includes `grpc-route` as an optional `traefik_route` endpoint limited to one relation

#### Scenario: Operator inspects the Terraform module outputs
- **WHEN** an operator inspects the Terraform module `requires` output map
- **THEN** it maps `grpc-route = "grpc-route"`

### Requirement: Publish TCP entrypoint and TLS-terminated route to Traefik
When the `grpc-route` relation exists, the leader unit SHALL publish a static `grpc` entrypoint on `:9090` and a dynamic `HostSNI(*)` TCP route. The TCP route SHALL terminate TLS at Traefik (`passthrough: false`) and forward plaintext HTTP/2 traffic without PROXY protocol headers to `<app>.<model>.svc.cluster.local:9090`.

#### Scenario: Leader unit configures an active grpc-route relation
- **WHEN** an operator relates `hook-service:grpc-route` to Traefik, all reconciliation preconditions pass, and the leader unit runs reconciliation
- **THEN** the leader unit writes static entrypoint `:9090` and dynamic `HostSNI(*)` TLS-terminated TCP route data to the relation databag

#### Scenario: Non-leader unit skips relation databag writes
- **WHEN** a non-leader unit reconciles while the `grpc-route` relation is active
- **THEN** the non-leader unit does not write to the `grpc-route` application databag and raises no authorization error

### Requirement: Gate route publication on reconciliation preconditions
Route publication SHALL happen as part of the leader's reconciliation loop, and SHALL only occur once its preconditions pass: workload container reachable, `pg-database` integrated with its database resource created, OpenFGA integrated when authorization requires it, and valid authentication configuration.

#### Scenario: All reconciliation preconditions pass
- **WHEN** the `grpc-route` relation is active and all reconciliation preconditions pass on the leader unit
- **THEN** the leader unit publishes the TCP route configuration during reconciliation

#### Scenario: A reconciliation precondition fails
- **WHEN** the `grpc-route` relation is active but a reconciliation precondition fails (for example, the `pg-database` relation is absent)
- **THEN** the leader unit does not write the TCP route configuration until the preconditions pass again

### Requirement: Handle incomplete or removed grpc-route relations safely
The charm SHALL keep the workload active when the `grpc-route` relation has incomplete remote data or when an operator removes the relation.

#### Scenario: Remote application has not published host metadata yet
- **WHEN** the `grpc-route` relation joins before Traefik publishes `external_host` or `scheme`, and all reconciliation preconditions pass
- **THEN** the leader unit still publishes the TCP route configuration and keeps the charm free of blocked or error states

#### Scenario: Operator removes the grpc-route relation
- **WHEN** an operator removes the `grpc-route` relation
- **THEN** the charm completes reconciliation without error and continues to serve HTTP on port `8080` and in-cluster gRPC on port `9090`

### Requirement: Preserve backward compatibility and HTTP ingress isolation
The charm SHALL keep `grpc-route` optional and independent from `internal-route` so existing deployments upgrade and serve HTTP traffic without breaking changes.

#### Scenario: Existing deployment runs without grpc-route
- **WHEN** an operator deploys or upgrades the charm without relating `grpc-route`
- **THEN** the charm reaches active status and serves HTTP endpoints and `internal-route` ingress normally

#### Scenario: Both internal-route and grpc-route are active
- **WHEN** an operator relates both `internal-route` and `grpc-route` to Traefik
- **THEN** the charm maintains HTTP routing on `internal-route` and TCP gRPC routing on `grpc-route` without interference
