# Charmed Hook Service for the Canonical Identity Platform

[![CharmHub Badge](https://charmhub.io/hook-service/badge.svg)](https://charmhub.io/hook-service)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/hook-service-operator?label=License)](https://github.com/canonical/hook-service-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/hook-service-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/hook-service-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

Python Operator for the Canonical Identity Platform Hook Service

## Usage

Deploy the charms:

```shell
juju deploy hook-service --trust
juju deploy identity-platform --trust
```

You can follow the deployment status with `watch -c juju status --color`.

### Configuration

Now that we have deployed our charms, we will need to configure the charm.

First we need to create a juju secret with the consumer id/secret:

```console
juju add-secret salesforce-consumer consumer-key=<consumer_key> consumer-secret=<consumer_secret>
```

Now we need to grant access to the secret to the charm:

```console
juju grant-secret salesforce-consumer hook-service
```

Then you will have to configure the charm, eg:

```console
juju config hook-service \
  salesforce_domain=https://canonicalhr--staging.sandbox.my.salesforce.com \
  salesforce_consumer_secret=salesforce-consumer
```

If you wish to disable the access control authorization integration, you can do so by configuring the `authorization_enabled` option:

```console
juju config hook-service authorization_enabled=false
```

The charm also requires integration with a PostgreSQL database and, if `authorization_enabled` is true (the default), OpenFGA:

```console
juju integrate hook-service:pg-database postgresql-k8s
juju integrate hook-service:openfga openfga-k8s
```

Now you can integrate the charm with the identity-platform:

```console
juju integrate hook-service:hydra-token-hook hydra
```

Once the charms reach an active state, any users that try to log in to the identity-platform will have groups in their access tokens pulled from salesforce.

### Securing the API

The charm supports securing the API using an OAuth provider (like Hydra). When enabled, all API requests must be authenticated with a valid Bearer token.

There are two ways to configure the authentication provider.

#### Option 1: Using the `oauth` Relation (Recommended)

Simply integrate the charm with an OAuth provider. This will automatically configure the authentication settings and allow the charm to fetch access tokens.

```console
juju integrate hook-service:oauth hydra
```

#### Option 2: Using Configuration

Alternatively, you can manually configure the provider details using charm configuration. This is useful if you cannot use the `oauth` relation.

```console
juju config hook-service \
  authn_issuer="https://auth.example.com" \
  authn_jwks_url="https://auth.example.com/.well-known/jwks.json"
```

#### Authorization Policy

You can optionally restrict access to specific users or scopes using charm configuration:

```console
juju config hook-service \
  authn_allowed_subjects="user1,user2" \
  authn_allowed_scope="hook_service"
```

#### Obtaining an Access Token

If you are using the `oauth` relation, you can use the `get-access-token` action to obtain a token for testing:

```console
TOKEN=$(juju run hook-service/0 get-access-token --format=json | jq -r '.["hook-service/0"].results.token')
curl -H "Authorization: Bearer $TOKEN" http://<hook-service-ip>:8080/api/v0/authz/groups
```

### Managing Groups and Users

The charm exposes Juju actions for day-2 group and user management. These are
the preferred interface for operators over direct API access.

If the `oauth` relation is configured, API actions automatically obtain a JWT
token via the client credentials flow. Without the relation, requests are
unauthenticated.

#### Token

| Action | Description |
|---|---|
| `get-access-token` | Obtain a JWT Bearer token for direct API calls or testing. |

```console
juju run hook-service/0 get-access-token
```

#### Group management

These actions call the hook-service REST API.

| Action | Description |
|---|---|
| `create-group` | Create a new local group. Returns `group-id`. |
| `delete-group` | Delete a group by ID. |
| `list-groups` | List all groups. Returns a JSON array. |

```console
# Create a group
juju run hook-service/0 create-group name=admins description="Admin users"

# List all groups (useful for discovering group IDs)
juju run hook-service/0 list-groups

# Delete a group
juju run hook-service/0 delete-group group-id=<group-id>
```

#### User management

These actions interact directly with the database via the hook-service CLI and
require the PostgreSQL integration to be ready.

| Action | Description |
|---|---|
| `users-delete` | Remove a user from all groups. |
| `users-list-groups` | List all groups a user belongs to. Returns JSON. |
| `users-set-groups` | Replace a user's group memberships (comma-separated group IDs). |
| `groups-add-users` | Add users to a group (comma-separated user IDs). |
| `groups-remove-users` | Remove users from a group (comma-separated user IDs). |
| `groups-list-users` | List all users in a group. Returns JSON. |

```console
# List groups for a user
juju run hook-service/0 users-list-groups user-id=alice@example.com

# Replace a user's memberships
juju run hook-service/0 users-set-groups user-id=alice@example.com groups=<group-id-1>,<group-id-2>

# Add users to a group
juju run hook-service/0 groups-add-users group-id=<group-id> users=alice@example.com,bob@example.com

# Remove a user from all groups
juju run hook-service/0 users-delete user-id=alice@example.com
```

#### Bulk import

The `import-groups` action batch-imports group memberships from an external
driver (e.g. Salesforce). Pass the Juju secret ID that contains
`consumer-key` and `consumer-secret`:

```console
# Dry-run import (additive only)
juju run hook-service/0 import-groups consumer-secret=<secret-id> domain=<api-domain>

# Import and remove stale groups/memberships no longer in the driver
juju run hook-service/0 import-groups consumer-secret=<secret-id> domain=<api-domain> sync=true
```

## Security

Please see [SECURITY.md](https://github.com/canonical/hook-service-operator/blob/main/SECURITY.md)
for guidelines on reporting security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/hook-service-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The Charmed Hook Service is free software, distributed under the Apache
Software License, version 2.0.
See [LICENSE](https://github.com/canonical/hook-service-operator/blob/main/LICENSE)
for more information.
