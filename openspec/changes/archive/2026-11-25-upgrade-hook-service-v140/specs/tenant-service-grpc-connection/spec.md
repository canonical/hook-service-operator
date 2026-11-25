# Spec Delta

## Purpose

Publish the tenant-service gRPC connection settings to the hook-service workload environment and advertise tenant readiness on the hydra token hook, matching the v1.4.0 workload configuration surface.

## ADDED Requirements

### Requirement: Publish tenant-service gRPC connection settings

WHEN `tenant-service-info` is related and publishes `grpc_url`, THEN the workload env SHALL contain `TENANT_SERVICE_GRPC_ADDRESS` as bare `host:port` (URL scheme stripped) and `TENANT_SERVICE_TLS_ENABLED` (`true` for `https`/`grpcs` schemes, `false` otherwise), and `TENANT_SERVICE_GRPC_TIMEOUT` SHALL be `5s`.

#### Scenario: http grpc_url

- **WHEN** `grpc_url` is `http://tenant-service:50051`
- **THEN** `TENANT_SERVICE_GRPC_ADDRESS` is `tenant-service:50051` and `TENANT_SERVICE_TLS_ENABLED` is `false`

#### Scenario: https grpc_url

- **WHEN** `grpc_url` is `https://tenant-service:50051`
- **THEN** `TENANT_SERVICE_GRPC_ADDRESS` is `tenant-service:50051` and `TENANT_SERVICE_TLS_ENABLED` is `true`

#### Scenario: grpc_url without a scheme

- **WHEN** `grpc_url` has no scheme (e.g. `tenant-service:50051`)
- **THEN** it is used verbatim as `TENANT_SERVICE_GRPC_ADDRESS` and `TENANT_SERVICE_TLS_ENABLED` is `false`

#### Scenario: relation absent

- **WHEN** `tenant-service-info` is not related
- **THEN** `TENANT_SERVICE_GRPC_ADDRESS` is empty and `TENANT_SERVICE_TLS_ENABLED` is `false` (tenant validation disabled, matching pre-upgrade behavior)

### Requirement: Track the v1.4.0 workload image

The `charmcraft.yaml` `resources.oci-image.upstream-source` SHALL be `ghcr.io/canonical/hook-service:v1.4.0`.

#### Scenario: image tag

- **WHEN** the charm is packed
- **THEN** the `oci-image` resource points at `ghcr.io/canonical/hook-service:v1.4.0`

### Requirement: Advertise tenant readiness on the hydra token hook

The `tenant_id` claim SHALL be advertised on the hydra token hook only WHEN the `tenant-service-info` relation provides `grpc_url`.

#### Scenario: grpc_url published

- **WHEN** `tenant-service-info` publishes a non-empty `grpc_url`
- **THEN** the hydra token hook advertises `tenant_id`

#### Scenario: grpc_url missing

- **WHEN** `tenant-service-info` is absent or publishes no `grpc_url`
- **THEN** the hydra token hook does not advertise `tenant_id`
