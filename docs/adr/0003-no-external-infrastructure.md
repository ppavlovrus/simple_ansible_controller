# ADR-0003: No external infrastructure, SQLite and asyncio

## Status

Accepted (2026-09-12)

## Context

The prototype followed the usual reflex for a task-executing service: PostgreSQL
for state, Redis as a broker, Celery for asynchronous execution. That is four
moving parts to install, monitor and back up before a single playbook runs.

The target user has five to fifty hosts. For them the operational cost of such a
control plane exceeds the cost of the problem it solves, which is precisely why
they do not deploy AWX either.

## Decision

State lives in SQLite in WAL mode; asynchronous execution is asyncio inside the
same process. No broker, no external database, no worker fleet. The whole product
is one process, one container, one volume.

## Consequences

+ Deployment is a single command, and there is nothing to operate.
+ No broker means no lost-task semantics to reason about, and no infrastructure
  that can be up while the product is down.
- One node only. Concurrency is bounded by a semaphore, and heavy parallel use is
  a hard architectural ceiling rather than a tuning exercise.
- Running tasks live and die with the process, so recovery on startup must be
  explicit: anything left `RUNNING` after a crash is marked failed, not resumed.

The ceiling is deliberate. Outgrowing it is the signal to move to a full
platform, and that boundary is what keeps this project small.

## Alternatives considered

- **Keep Celery and Redis.** Rejected: they are the single largest contributor to
  operational cost and buy nothing at this scale.
- **SQLite with a thread pool instead of asyncio.** Partially adopted:
  `ansible-runner` is blocking, so its calls do run in a thread pool, while the
  rest of the service stays async.
- **PostgreSQL optional, SQLite by default.** Rejected for now: two supported
  storage backends double the testing surface for a product whose selling point
  is that it has no backend.
