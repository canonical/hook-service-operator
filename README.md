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

Now you can integrate the charm with the identity-platform:

```console
juju integrate hook-service:hydra-token-hook hydra
```

Once the charms reach an active state, any users that try to log in to the identity-platform will have groups in their access tokens pulled from salesforce.

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
