# ADR-0005: Snapshot the playbook and the inventory into every task

## Status

Accepted (2026-09-12)

## Context

Playbooks change. Inventories change even faster when they are generated from a
cloud API: two runs an hour apart legitimately target different hosts. A task
record that stores only a playbook name and a provider name therefore cannot
answer the question that matters after an incident, which is "what exactly did
this run do, and where".

Agents make this sharper. An agent may store a playbook, run it, adjust it and
run it again within a minute, and it needs to compare the two runs afterwards.

## Decision

When a task is created, the full text of the playbook and of the resolved
inventory is copied into the task record, together with the variables used. The
run executes from that snapshot, not from the live store.

## Consequences

+ A run is reproducible and auditable after the fact even if the playbook was
  edited or the cloud inventory changed.
+ Re-running a historical task is well defined.
+ Diagnosing a failure needs no archaeology across the store and the provider.
- Storage grows with the number of tasks; playbooks are small, but retention
  becomes a real setting rather than an afterthought.
- Editing a stored playbook does not affect tasks already created from it, which
  is intended but can surprise.

## Alternatives considered

- **Store references (playbook name, provider name, timestamp).** Rejected: it
  cannot reconstruct a run whose inputs have since changed, which is exactly the
  case worth reconstructing.
- **Content-addressed storage with deduplication.** Deferred: it solves a storage
  problem the project does not have yet and complicates the simplest read path.
