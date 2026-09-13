# AGENTS.md

Guidance for anyone working in this repository, human or AI agent.

> **Single source of truth.** This file is canonical. `CLAUDE.md` and
> `.cursorrules` are symlinks to it — edit **this** file, never the mirrors.

## What this project is

A minimal Ansible controller with an MCP interface. An agent hands it a playbook
and an inventory; it runs them and keeps the history, logs and artifacts. One
process, SQLite, no broker.

It is a **dumb executor**: it does not write playbooks, does not decide what to
run, and does not judge what a playbook does. Intelligence lives in the caller.
If a change makes the controller smarter, it is probably the wrong change.

Start with [docs/concept.md](docs/concept.md) for what it is for, and
[docs/architecture.md](docs/architecture.md) for how it is built.

## Commands

```bash
poetry install

poetry run task tests        # the suite
poetry run task lint         # ruff check + ruff format --check + mypy
poetry run task fmt          # fix what ruff can fix
poetry run task eval         # tool-selection eval against a local model
poetry run ansible-mcp       # run it, stdio transport

make integration             # SSH tests; brings up the test hosts first
make image                   # container
make deb                     # Debian package, built in a container
```

CI runs `task lint` and `task tests`, the same commands, plus a container build.
A green local run means a green CI run.

`task lint` starts with `poetry check --lock`, because that promise was broken
once: editing a dependency line by hand after `poetry add` leaves the lock's
content hash stale, `poetry run` never notices, and CI fails on `poetry install`
before a single test runs. If you touch `[project] dependencies`, run
`poetry lock` and commit the result.

## Before changing anything

**Read the relevant ADR.** [docs/adr/INDEX.md](docs/adr/INDEX.md) is short and
most records exist to defend a boundary: no external infrastructure, no playbook
generation, no RBAC, providers as thin plugins, HTTP only with a checked token.
These are decisions with rejected alternatives, not defaults nobody got round to
changing.

To deviate, add a new ADR that supersedes the old one. Do not silently edit an
accepted record — ADR-0001 says so, and that rule is what makes the rest
trustworthy.

**Check the installed version of the MCP SDK before using its API.** It moves
fast and has already renamed `FastMCP` to `MCPServer`, moved result fields to
snake_case (`is_error`, `server_info`, `input_schema`) and changed `call_tool` to
raise rather than return an error payload. Every one of those was found by
inspecting the installed package, not by recalling the docs:

```bash
poetry run python -c "import inspect; from mcp.server.mcpserver import MCPServer; print(inspect.signature(MCPServer.tool))"
```

## Conventions that matter here

**A tool's docstring is its contract.** It is what an agent reads when choosing
between tools, so it says what the tool does, when to choose it over the
neighbouring one, what each argument is, and what comes back. Three tool
descriptions in this repository were rewritten because a model picked wrong, and
the eval harness caught it. If you add a tool, run the eval.

**Responses carry what a decision needs, and nothing more.** No snapshots, no
raw rows, everything unbounded capped with a default. Filling the caller's
context is a failure mode, not a detail.

**Refusals are written for the caller.** `require`, `found` and `confirmed` in
`server/errors.py` produce messages that say what to do differently. A refusal
an agent cannot act on makes it retry the identical call — that is observed
behaviour, not a theory.

**Accept equivalent argument shapes, refuse ambiguous ones.**
`operations/coercion.py` takes a parsed playbook where text is declared, and an
empty string where a list is. It still refuses a bare inventory where an object
belongs, with an example.

**A rule lives in `operations/`, never in a surface.** There are two callers now:
the MCP tools and the REST routes. A tool keeps its description, the argument
shapes agents send and the confirm gate; a route keeps its method, status code
and schema; everything either of them *decides* -- what is refused, what is
capped, what comes back -- sits below both, where there is one copy of it
(ADR-0015). If you find yourself validating in a route, you are writing the
second copy.

**Destructive tools take `confirm=false` by default.** Cancel and delete refuse
without it.

**Every path out of a background task writes a terminal status.** A task stuck at
`running` is the one failure a polling agent cannot recover from.

**Secrets never leave the process.** `core/redaction.py` runs over output, error
messages and audit entries. If you add a surface that returns text, it goes
through redaction, and a test proves it.

## Style

Match what is there. Concretely:

- Comments explain *why*, never *what*. If a line needs a comment to say what it
  does, rewrite the line.
- Docstrings on public functions, Google style, with `Args:` and `Returns:`.
  `ruff` enforces their presence; usefulness is on you.
- Tests are named after the behaviour they pin, not the function they call:
  `test_recovery_leaves_this_process_own_tasks_alone`, not `test_recover`.
- A test for a bug says, in a comment, what the bug was. Several here do.
- No `Any` where a type is knowable. `mypy` is not strict yet; do not make that
  worse.
- Line length 100, `ruff format` decides the rest. Do not argue with it.

## Testing

The suite runs real `ansible-playbook` processes against the control node with
`connection: local` — no SSH, no containers, fast enough for CI. That is why
`tests/fixtures/local_ping.yml` exists.

`tests/test_integration_ssh.py` uses the containers from `docker-compose.yml` and
is skipped when they are not up. The chain eval executes tools for real against
throwaway instances.

Do not mock what can be run. Most defects in this repository were found by
executing something (a playbook, a deb install, an image, a model) and looking at
what happened, not by reading code.

## Things known to be wrong or missing

Worth knowing before you trip over them:

- `Task.variables` sit in the database in the clear, because a run cannot be
  reproduced without them. The database file is sensitive.
- One token for the whole instance, so the audit log records what was done and
  not by whom.
- No license file, which blocks any external use. Apache-2.0 is intended.
- Execution-environment isolation (ADR-0008, exposed as ADR-0016 describes) is
  decided but not implemented; the `execution_environment` column exists and is
  unused. Note before writing it: the operator enables the mode, a run may pick
  an image but may not turn the mode off.

## What not to do

- Do not add a tool that calls a language model. ADR-0004.
- Do not add PostgreSQL, Redis or a task queue. ADR-0003.
- Do not resolve "exactly one of" arguments by precedence. A run that quietly
  used a different inventory than the caller believed is worse than a refusal.
- Do not let an API key buy a public bind without the check that validates it.
  ADR-0010 is kept in the log as the record of getting that wrong.
- Do not loosen an eval scenario to make it pass. A suite that always passes
  measures nothing.
