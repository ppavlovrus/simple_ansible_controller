# ADR-0012: A static bearer token guards the HTTP endpoint

## Status

Accepted (2026-09-12). Supersedes ADR-0010.

## Context

ADR-0010 confined the HTTP transport to loopback because nothing verified
callers: the API key was read from the environment and never compared against a
request. That was the right stopgap and an obvious dead end. An agent on another
machine is a real use case, and "put a reverse proxy in front of it" is a large
ask for a product whose selling point is that it deploys in one command.

The SDK offers an OAuth-shaped path: an authorization server, a token verifier,
discovery. That is the correct answer for a platform with user identities. This
service has no users (ADR-0003), so there is no identity to federate, and
adopting OAuth would mean standing up an authorization server to protect a single
process holding a SQLite file.

## Decision

Every HTTP request carries `Authorization: Bearer <token>` and is compared
against `ANSIBLE_MCP_API_KEY` with a constant-time comparison. A request without
it, or with a wrong one, is answered 401 by a pure-ASGI middleware that never
reaches the application.

Serving beyond loopback without the key is refused at startup, in two places: the
configuration gate and the construction of the HTTP application. A loopback bind
needs no key, because reaching it already requires being on the machine, where
the stdio transport serves the same purpose.

`GET /healthz` is exempt. A readiness probe should not need a credential, and the
response holds a version and counts of tasks and failed calls: useful to an
operator, worthless to an attacker.

Only the first `Authorization` header is read. Collapsing headers into a
dictionary keeps the last of any duplicates, which turns a second header into a
way to override the first.

## Consequences

+ An agent on another machine can reach the service without a proxy in front.
+ The dangerous configuration cannot be reached by accident: it fails at startup.
+ Pure ASGI means the check does not interfere with streamed responses.
- One token for the whole instance: there is no way to tell two callers apart, so
  the audit log records what was done and not by whom.
- Rotating the token restarts the process.
- A token in an environment variable is a token on disk in whatever launches the
  process.

The first of those is the honest limit of a service with no users. When telling
callers apart matters, the answer is a platform with identities, not a second
token here.

## Alternatives considered

- **Stay on loopback, as ADR-0010 had it.** Rejected now that verification
  exists: the restriction was a consequence of not checking the token, and the
  tunnel-or-proxy workaround pushed real cost onto every remote deployment.
- **The SDK's OAuth support.** Rejected: it presumes identities this service does
  not have, and the operational cost dwarfs what it protects.
- **mTLS.** Rejected for now: stronger, and defensible later, but it needs
  certificate distribution and rotation that a one-command deployment does not
  have.
- **Token per caller, stored in the database.** Rejected: it looks like identity
  without providing it, and invites an authorization model the design says no to
  (ADR-0003).
