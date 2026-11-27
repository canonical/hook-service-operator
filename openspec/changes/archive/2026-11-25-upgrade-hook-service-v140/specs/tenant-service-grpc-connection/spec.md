# Spec Delta

## Purpose

The charm publishes tenant-service gRPC settings to the workload environment.
The charm also advertises tenant validation readiness on the `hydra-token-hook` relation.

## ADDED Requirements

### Requirement: Publish tenant-service gRPC connection settings

The charm SHALL set `TENANT_SERVICE_GRPC_TIMEOUT` to `5s` in the workload environment.
WHEN the `tenant-service-info` relation provides `grpc_url`, the charm SHALL remove any URL scheme and set `TENANT_SERVICE_GRPC_ADDRESS` to `host:port`.
WHEN `grpc_url` uses the `https` scheme, the charm SHALL set `TENANT_SERVICE_TLS_ENABLED` to `true`.
WHEN `grpc_url` does not use the `https` scheme, the charm SHALL set `TENANT_SERVICE_TLS_ENABLED` to `false`.

#### Scenario: http grpc_url

- **WHEN** `grpc_url` is `http://tenant-service:50051`
- **THEN** the charm sets `TENANT_SERVICE_GRPC_ADDRESS` to `tenant-service:50051`
- **AND** the charm sets `TENANT_SERVICE_TLS_ENABLED` to `false`
- **AND** the charm sets `TENANT_SERVICE_GRPC_TIMEOUT` to `5s`

#### Scenario: https grpc_url

- **WHEN** `grpc_url` is `https://tenant-service:50051`
- **THEN** the charm sets `TENANT_SERVICE_GRPC_ADDRESS` to `tenant-service:50051`
- **AND** the charm sets `TENANT_SERVICE_TLS_ENABLED` to `true`
- **AND** the charm sets `TENANT_SERVICE_GRPC_TIMEOUT` to `5s`

#### Scenario: grpc_url without a scheme

- **WHEN** `grpc_url` is `tenant-service:50051`
- **THEN** the charm sets `TENANT_SERVICE_GRPC_ADDRESS` to `tenant-service:50051`
- **AND** the charm sets `TENANT_SERVICE_TLS_ENABLED` to `false`
- **AND** the charm sets `TENANT_SERVICE_GRPC_TIMEOUT` to `5s`

#### Scenario: tenant-service-info relation absent

- **WHEN** the `tenant-service-info` relation does not exist
- **THEN** the charm sets `TENANT_SERVICE_GRPC_ADDRESS` to `""`
- **AND** the charm sets `TENANT_SERVICE_TLS_ENABLED` to `false`
- **AND** the charm sets `TENANT_SERVICE_GRPC_TIMEOUT` to `5s`

### Requirement: Advertise tenant readiness on the hydra-token-hook relation

WHEN the `tenant-service-info` relation provides a non-empty `grpc_url`, the charm SHALL include `tenant_id` in `enabled_claims` on the `hydra-token-hook` relation.
WHEN the `tenant-service-info` relation does not exist or omits `grpc_url`, the charm SHALL omit `tenant_id` from `enabled_claims`.

#### Scenario: grpc_url present

- **WHEN** the `tenant-service-info` relation provides a non-empty `grpc_url`
- **THEN** the charm writes `tenant_id` to `enabled_claims` on the `hydra-token-hook` relation

#### Scenario: grpc_url missing

- **WHEN** the `tenant-service-info` relation does not exist or omits `grpc_url`
- **THEN** the charm writes only `groups` to `enabled_claims` on the `hydra-token-hook` relation

### Requirement: Remove legacy TENANT_SERVICE_URL and service_url support (Breaking)

The charm SHALL NOT set `TENANT_SERVICE_URL` in the workload environment.
The charm SHALL NOT read `service_url` from the `tenant-service-info` relation databag.

#### Scenario: provider publishes only legacy service_url

- **WHEN** the `tenant-service-info` relation provides `service_url` without `grpc_url`
- **THEN** the charm sets `TENANT_SERVICE_GRPC_ADDRESS` to `""`
- **AND** the charm sets `TENANT_SERVICE_TLS_ENABLED` to `false`
- **AND** the charm omits `TENANT_SERVICE_URL` from the workload environment
