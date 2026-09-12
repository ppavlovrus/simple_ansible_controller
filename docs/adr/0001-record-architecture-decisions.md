# ADR-0001: Record architecture decisions

## Status

Accepted (2026-09-12)

## Context

This project is small on purpose, and much of its value comes from what it
deliberately refuses to do. Those refusals are exactly what gets re-litigated:
"why not PostgreSQL", "why not generate playbooks", "why no RBAC". Until now the
reasoning lived in a concept document and in the head of one developer.

The project is also meant to be built and operated with AI agents in the loop. An
agent reads what is written down; it cannot ask why a boundary exists.

## Decision

Record every significant architectural decision as a short Markdown file in
`docs/adr/`, Nygard format (Status / Context / Decision / Consequences /
Alternatives considered), numbered sequentially and indexed in `INDEX.md`.

ADRs are immutable once accepted. To change a decision, add a new ADR that
supersedes the old one and mark the old one Superseded, never silently edit it.

## Consequences

+ Contributors and agents can read *why*, not only *what*.
+ "Alternatives considered" keeps settled debates closed unless new facts appear.
+ A boundary written down as a decision is harder to erode feature by feature.
- A small writing cost per decision.

## Alternatives considered

- **Keep the rationale in the concept document.** Rejected: it describes the
  product as a whole and cannot carry per-decision context and trade-offs without
  turning into a wall of text.
- **Rely on commit messages.** Rejected: they explain a change, not a standing
  constraint, and nobody greps history before proposing PostgreSQL again.
