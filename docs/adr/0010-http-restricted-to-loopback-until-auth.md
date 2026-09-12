# ADR-0010: HTTP stays on loopback until callers are verified

## Status

Superseded by [ADR-0012](0012-static-bearer-token-for-http.md) (2026-09-12).
Token verification now exists, so the loopback restriction it describes is no
longer in force. Kept for the reasoning, which still explains why an unverified
key must not buy a public bind.

## Context

ADR-0007 requires the server to refuse a bind beyond loopback unless
`ANSIBLE_MCP_API_KEY` is set. The setting was added with the server, but nothing
verifies it: no code compares an incoming `Authorization` header against it.

Taken literally, the earlier rule therefore produced the worst available outcome.
An operator who sets the key and binds to `0.0.0.0` gets a server that starts
without complaint, looks configured for authentication, and accepts arbitrary
playbook execution from anyone who can reach the port. A configuration that
looks protected and is not is more dangerous than one that is obviously open.

Implementing verification properly is not a small aside. The SDK's own auth path
is OAuth-shaped (an authorization server, a token verifier), and a hand-rolled
static bearer check belongs with a considered threat model, request logging and
tests, not squeezed into the milestone that introduced the tools.

## Decision

While no code verifies callers, the HTTP transport may bind only to loopback.
The presence of an API key does not buy permission to bind publicly, and the
refusal names the reason.

Remote access is reached by putting something that does authenticate in front of
the loopback endpoint (an SSH tunnel, or a reverse proxy that terminates auth),
or by using the stdio transport, where the client launches the process and no
port exists.

`ANSIBLE_MCP_API_KEY` stays in the configuration, documented as not yet
enforced, so the name does not change when verification lands.

## Consequences

+ There is no configuration that looks authenticated while being open.
+ The failure is at startup, with a message that says what to do instead.
+ A deployment that needs remote access uses a component built for the job.
- Serving directly to a network is unavailable for now, which is a real
  limitation for anyone wanting the agent on another machine without a tunnel.
- This decision has to be revisited deliberately; it is not a permanent stance.

## Alternatives considered

- **Honour the key as permission to bind publicly, as ADR-0007 literally says.**
  Rejected: that is exactly the false sense of security described above.
- **Implement a static bearer check here and now.** Rejected for this milestone,
  not on principle: security code written as an afterthought inside an unrelated
  change is how holes get shipped. It is the first item of the hardening
  milestone.
- **Drop the API key setting until it works.** Rejected: the name is already in
  the documentation and the ADRs, and removing it would churn the configuration
  surface twice.
