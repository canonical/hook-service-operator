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

### Managing Groups and Access

Once the charm is active and integrated, you can manage groups and access using the API.

First, set up the necessary environment variables:

```bash
# set the client ID
export CLIENT_ID="<client-id>"
# the hook service unit IP
export HOOK_SERVICE_HOST="<hook-service-ip>:8000"
export USER_EMAIL="my.email@example.com"
export GROUP_NAME="my group name"
export GROUP_DESCRIPTION="something"
```

Create a group:

```bash
export GROUP_ID=$(curl -s -XPOST "http://${HOOK_SERVICE_HOST}/api/v0/authz/groups" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$GROUP_NAME\", \"description\": \"$GROUP_DESCRIPTION\", \"type\": \"local\"}" | yq .data[0].id)
```

Add a user to the group:

```bash
curl -s -XPOST "http://${HOOK_SERVICE_HOST}/api/v0/authz/groups/${GROUP_ID}/users" \
  -H "Content-Type: application/json" \
  -d "[\"${USER_EMAIL}\"]"
```

Grant the group access to an application:

```bash
curl -s -XPOST "http://${HOOK_SERVICE_HOST}/api/v0/authz/groups/${GROUP_ID}/apps" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"$CLIENT_ID\"}"
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
