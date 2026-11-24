# Spec Delta

## Purpose

Defines the `groups-api` relation contract for Hook Service to publish gRPC connection endpoints and dynamically authorize OIDC consumer subjects.

## ADDED Requirements

### Requirement: Declare the optional groups-api provider endpoint
The charm SHALL declare an optional `groups-api` relation endpoint under `provides` using the `groups_api` interface without a relation limit. The Terraform module SHALL include `groups-api` in its `provides` output map.

#### Scenario: Operator inspects provider metadata and Terraform outputs
- **WHEN** an operator inspects `charmcraft.yaml` or Terraform module outputs
- **THEN** the `provides` map includes `groups-api` with interface `groups_api` and supports multiple consumer relations

### Requirement: Exchange consumer subject and provider gRPC endpoint data
The `charms.hook_service.v0.groups_api` library SHALL accept a non-empty OIDC `subject` string in each requirer application databag and publish `grpc_address` (`<host>:9090`) and `tls_enabled` (`true` or `false`) in the provider application databag.

#### Scenario: Leader publishes endpoint data to an active consumer
- **WHEN** a consumer integrates via `groups-api`, provides a valid `subject`, and authentication is ready
- **THEN** the leader unit writes `grpc_address` and `tls_enabled` to that relation's application databag

#### Scenario: Requirer omits or supplies an empty subject
- **WHEN** a `groups-api` relation exists without a non-empty `subject` in the requirer databag
- **THEN** the charm ignores the empty subject without error and keeps the unit free of crash failures

#### Scenario: Non-leader unit skips relation databag writes
- **WHEN** a non-leader unit reconciles active `groups-api` relations
- **THEN** the non-leader unit writes nothing to any `groups-api` application databag and raises no authorization error

### Requirement: Resolve gRPC endpoint and TLS mode from grpc-route presence
The charm SHALL resolve `grpc_address` and `tls_enabled` solely from the presence and readiness of `grpc-route`, without using `use_ingress_for_relations`.

#### Scenario: No grpc-route relation is present
- **WHEN** `groups-api` is active and `grpc-route` is not integrated
- **THEN** the leader publishes `<app>.<model>.svc.cluster.local:9090` with `tls_enabled` set to `false`

#### Scenario: Active grpc-route has published an external host
- **WHEN** `groups-api` is active and `grpc-route` has a non-empty `external_host`
- **THEN** the leader publishes `<external_host>:9090` with `tls_enabled` set to `true`

#### Scenario: Active grpc-route has not published an external host yet
- **WHEN** `groups-api` is active and `grpc-route` exists with an empty `external_host`
- **THEN** the leader withholds `grpc_address` from `groups-api` databags and sets `WaitingStatus`

#### Scenario: Operator removes grpc-route while groups-api remains active
- **WHEN** an operator removes `grpc-route` while `groups-api` stays related
- **THEN** the leader updates `groups-api` databags to `<app>.<model>.svc.cluster.local:9090` with `tls_enabled` set to `false`

### Requirement: Dynamically manage allowed JWT subjects for consumers
The charm SHALL merge subjects from all active `groups-api` relations with `authn_allowed_subjects` and the `oauth` client ID into `AUTHENTICATION_ALLOWED_SUBJECTS`, and SHALL remove a consumer subject when its relation departs or breaks.

#### Scenario: Multiple consumers relate via groups-api
- **WHEN** two consumer applications relate via `groups-api` with distinct `subject` values while auth is active
- **THEN** the workload environment contains both consumer subjects alongside configured subjects and the OAuth client ID without duplicates

#### Scenario: Consumer relation is removed
- **WHEN** an operator removes one `groups-api` relation
- **THEN** the charm replans the workload without that consumer's subject in `AUTHENTICATION_ALLOWED_SUBJECTS`

### Requirement: Enforce authentication when groups-api is integrated
The charm SHALL require JWT authentication (`oauth` integration ready or `authn_issuer` configured) whenever at least one active `groups-api` relation exists, and SHALL withhold `groups-api` endpoint publication until authentication is ready.

#### Scenario: Consumer relates without oauth or manual issuer configuration
- **WHEN** `groups-api` is integrated while neither an `oauth` relation nor `authn_issuer` is present
- **THEN** the charm enters `BlockedStatus` and does not publish `grpc_address` to `groups-api`

#### Scenario: Consumer relates while oauth client creation is pending
- **WHEN** `groups-api` and `oauth` are integrated before the OAuth client credentials arrive
- **THEN** the charm enters `WaitingStatus` and does not publish `grpc_address` to `groups-api`

#### Scenario: Existing deployment runs without groups-api
- **WHEN** no `groups-api` relation exists and neither `oauth` nor `authn_issuer` is configured
- **THEN** the charm preserves existing behavior and reaches `ActiveStatus` without blocking on authentication
