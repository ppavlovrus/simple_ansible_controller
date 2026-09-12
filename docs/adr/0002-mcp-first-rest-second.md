# ADR-0002: MCP is the primary interface; REST is secondary

## Status

Accepted (2026-09-12)

## Context

The controller has two plausible audiences: AI agents, and humans with scripts or
curl. Existing automation platforms expose a REST API designed for a human
clicking through a UI, with deep object graphs and many calls to launch one job.
Where they offer agent access at all, it is bolted on afterwards as a wrapper.

Which audience is primary decides how tools are named and shaped, how much a
single call does, and what the responses look like.

## Decision

The MCP interface is the product. Tools are designed for an agent: a small set of
well-named verbs, each doing one useful unit of work, returning compact JSON with
the fields an agent needs to decide what to do next.

REST exists for humans and scripts and is a thin layer over the same core. Where
the two interfaces disagree about shape, MCP wins.

## Consequences

+ Agents drive the controller without glue code or an API wrapper.
+ Tool descriptions become a first-class artefact: they are what the agent reads
  when choosing an action, so they are part of the contract, not documentation.
+ Responses stay small, which keeps the agent's context usable.
- Human-facing ergonomics are a follow-on concern, and there is no UI.
- Tool descriptions must be maintained as carefully as code.

## Alternatives considered

- **REST first with an MCP wrapper.** Rejected: this is what the large platforms
  do, and it produces exactly the chatty, object-graph-shaped interface that an
  agent handles badly.
- **MCP only.** Rejected: a curl-able surface costs little on top of the same
  core and makes the service scriptable and debuggable by a human.
