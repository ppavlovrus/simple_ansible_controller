# ADR-0006: Providers are thin plugins; credentials never reach the database

## Status

Accepted (2026-09-12)

## Context

Inventories come from different places: a static file on bare metal, or an API
call to Yandex Cloud, OpenNebula or AWS. Supporting every cloud in the core would
turn a small controller into a cloud abstraction layer, and each new provider
would mean a release of the whole product.

Providers also need credentials, and credentials in a database are a liability
that must then be encrypted, rotated and audited.

## Decision

A provider is a plugin with a narrow contract: validate its credentials, return
an Ansible inventory, and optionally provision or deprovision resources. Built-in
plugins ship with the package; third-party plugins register through
`entry_points`, so a new provider needs no change here and no fork.

Provider configuration is non-sensitive and may be stored. Credentials are read
from environment variables named by the configuration; their values never enter
the database or the configuration file.

## Consequences

+ New providers arrive without touching the core or waiting for a release.
+ A database leak exposes no credentials.
+ The plugin contract is small enough to implement in an afternoon.
- Credential lifecycle (rotation, per-task scoping, vaults) is out of scope and
  becomes the operator's responsibility.
- Plugin quality is outside our control, and a badly written plugin runs in the
  same process.

## Alternatives considered

- **Providers built into the core.** Rejected: every cloud SDK becomes a
  dependency of every deployment, and the release cadence couples to theirs.
- **Encrypted credentials in the database.** Rejected: it requires a key to
  protect the key, which is the problem a secret manager exists to solve, and
  this project is not one.
- **Inventory scripts as subprocesses, like Ansible's dynamic inventory.**
  Considered and kept as a fallback: the static plugin can point at such a script
  when someone already has one.
