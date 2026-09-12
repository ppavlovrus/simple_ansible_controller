# ADR-0007: Write safety, no automatic retries, and an authentication gate

## Status

Accepted (2026-09-12)

## Context

This service executes arbitrary playbooks on real hosts, driven by an agent that
may be acting on an ambiguous instruction. Three failure modes follow from that
and none of them are hypothetical:

- an agent cancels or deletes something it should not have;
- a transport error triggers a retry of a non-idempotent call, and one launch
  becomes two runs;
- the endpoint is exposed on a routable address without authentication, and
  arbitrary playbook execution becomes available to the network.

## Decision

Destructive operations (cancel, delete) require an explicit `confirm=true`
argument and refuse without it.

The service performs no automatic retries on writes. A transport error surfaces
to the agent as a readable error, so a launch is never re-issued behind the
agent's back.

Long-running operations do not block by default. A call returns a task id, and
the caller polls; waiting is opt-in.

The server refuses to start when it binds beyond loopback without
`ANSIBLE_MCP_API_KEY` set. An unauthenticated public bind is not a configuration
choice, it is an incident.

Secrets are redacted from everything the service returns or logs.

## Consequences

+ No destruction without an explicit second signal from the caller.
+ No duplicate runs from a retried write.
+ The dangerous default configuration cannot be reached by accident.
- The agent must pass `confirm=true` for destructive calls. The friction is the
  point.
- Transient network errors are visible to the agent rather than smoothed over.

## Alternatives considered

- **A single global read-only flag.** Rejected: too coarse. A read-only
  deployment loses useful safe writes; a writable one loses the destructive
  guard.
- **Transport-level retries for everything.** Rejected: a retried launch starts a
  second job. Retrying reads only is a safe, separate enhancement later.
- **Warn instead of refusing on an unauthenticated public bind.** Rejected:
  warnings in logs are read after the incident, not before it.
