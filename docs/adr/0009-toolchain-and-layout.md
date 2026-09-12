# ADR-0009: Poetry, src-layout, and one CI gate shared with developers

## Status

Accepted (2026-09-12)

## Context

The prototype pinned nothing: a flat `requirements.txt`, `black` and `flake8`
invoked ad hoc, and a CI pipeline that installed different things than a
developer did. Reproducing a failure from CI locally was guesswork.

For a project meant to be developed with agents in the loop, this matters more
than usual. An agent needs one obvious command per intent, and it needs the
checks it runs locally to be the checks that gate the merge.

## Decision

Dependencies are declared in `pyproject.toml` and locked with Poetry, including
`ansible-core`: `ansible-runner` shells out to `ansible-playbook`, so the engine
is a runtime dependency, not a development one.

The package lives under `src/ansible_mcp/`, so tests run against the installed
package rather than the working directory.

`ruff` replaces `black` and `flake8` for both linting and formatting; `mypy` runs
in non-strict mode. Named tasks (`task tests`, `task lint`, `task fmt`) are the
single entry point, and CI runs those same tasks rather than its own command
list.

## Consequences

+ A green local run means a green CI run, for humans and agents alike.
+ The lock file makes builds reproducible and dependency drift visible in review.
+ One tool (`ruff`) instead of two, an order of magnitude faster.
- Poetry becomes a prerequisite for contributing.
- Non-strict `mypy` lets some type errors through; tightening it later is a
  separate, deliberate step.

## Alternatives considered

- **Keep `requirements.txt` with pip-tools.** Rejected: it locks dependencies but
  leaves scripts, package metadata and dev groups scattered.
- **`mypy --strict` from the start.** Rejected for now: on an empty codebase it
  is free, but it would be adopted before the shape of the core exists. Revisit
  once the core is written.
