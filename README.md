# ansible-mcp

A minimal Ansible controller with an MCP interface, for AI agents.

Give it a playbook and an inventory; it runs them and keeps the history, the logs
and the artifacts of every run. One process, one SQLite file, one container. No
database server, no message broker, no worker fleet.

*Русская версия: [README.ru.md](README.ru.md)*

## Why

Running Ansible against a handful of hosts is easy. Running it *programmatically*
is not, and the moment you want that the options get heavy: AWX and Ansible
Automation Platform need PostgreSQL, Redis, RabbitMQ, Receptor and in practice
Kubernetes. For fifty hosts that control plane costs more than the problem it
solves.

And an AI agent driving infrastructure needs a machine-facing interface. A REST
API designed for a human clicking through a UI means deep object graphs and a
dozen calls to launch one job; an agent wants a handful of well-named verbs.

That is what this is: a **dumb executor** with an agent-shaped interface. It does
not write playbooks and does not decide what to run — the calling agent does
both. See [docs/concept.md](docs/concept.md).

## Quick start

The fastest path is stdio, where the client launches the process:

```bash
poetry install
poetry run ansible-mcp        # speaks MCP on stdin/stdout
```

In Claude Code, or any MCP client:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "command": "poetry",
      "args": ["run", "ansible-mcp"],
      "env": { "ANSIBLE_MCP_DATA_DIR": "/tmp/ansible-mcp" }
    }
  }
}
```

As a container, serving over HTTP:

```bash
docker build -t ansible-mcp .
docker run -p 8080:8080 -v ./data:/data \
  -e ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" ansible-mcp
```

The key is not optional there: the container listens beyond loopback, and the
server refuses to serve an unauthenticated endpoint that executes playbooks.
For a host installation, see [packaging](packaging/README.md).

## The tools

| Tool | What it does |
|---|---|
| `run_playbook` | Starts a run and returns a task id; the run continues in the background |
| `get_task_status` | pending, running, success, failed or cancelled, with timestamps and exit code |
| `get_task_logs` | What Ansible printed, last lines first by default, secrets removed |
| `cancel_task` | Stops a queued or running playbook; needs `confirm=true` |
| `list_tasks` | Recent runs, newest first, filterable by status |
| `save_playbook` / `list_playbooks` / `get_playbook` / `delete_playbook` | Playbooks by name, so a run need not carry its text |
| `add_provider` / `list_providers` / `get_inventory` / `delete_provider` | Where an inventory comes from |

A provider is a small plugin that produces an inventory: `static` ships built in,
others register through the `ansible_mcp.providers` entry point group. Cloud
providers are the next ones planned.

## What it deliberately does not do

- **No RBAC, no multi-tenancy.** One key gates the instance.
- **No horizontal scaling.** One node, concurrency bounded by a semaphore.
- **No web UI.**
- **No playbook generation.** That is the calling agent's job, and the LLM layer
  the prototype had was removed rather than ported.

Each of these is a decision with its reasoning and its rejected alternatives in
the [decision log](docs/adr/INDEX.md). Outgrowing them is the signal to move to a
full platform, and that boundary is what keeps this project small.

## Security: the API key is shell access

Read this before exposing the endpoint to anything.

**Whoever holds the API key can run arbitrary code on the controller host**, as
the user the service runs as. Not through a bug — through the feature. A playbook
with `hosts: localhost`, or an inventory line carrying
`ansible_connection=local`, executes on the controller itself, and the controller
is built to run whatever playbook it is handed: it does not inspect, judge or
restrict them ([ADR-0004](docs/adr/0004-dumb-executor.md)).

So treat the key exactly as you would an SSH login to that host. One key covers
the whole instance, there is no per-caller identity, and the audit log records
what was done rather than by whom.

What reduces the blast radius today:

- Run it as an unprivileged user. The container image and the Debian package
  both do; a manual install should too.
- Give that user only the SSH credentials it needs, and no sudo on the
  controller.
- Keep the endpoint off the network unless it has to be on it. The stdio
  transport has no port at all, and a loopback bind needs no key because
  reaching it already means being on the machine.

What would actually fix it is running each playbook inside a container rather
than on the host. That is decided and specified in
[ADR-0008](docs/adr/0008-execution-environments.md) — and **not implemented**:
the database column exists, the code does not. Until it does, the sentence above
is the whole security model, and this section is here so nobody discovers it the
hard way.

## Working on it

```bash
poetry install
poetry run task tests        # 208 tests
poetry run task lint         # ruff + ruff format + mypy
make integration             # playbooks against real hosts over SSH
poetry run task eval         # can a local model actually drive this?
```

The eval harness is not decoration: it reads the tool schemas from the running
server and measures whether a model picks the right tool. Several tool
descriptions and the whole argument-coercion layer exist because it failed first.
See [evals/README.md](evals/README.md).

Contributors, human or otherwise, start at [AGENTS.md](AGENTS.md).

## Documentation

| | |
|---|---|
| [Concept](docs/concept.md) | The problem, the consumers, the trade-offs |
| [Architecture](docs/architecture.md) | What the code does now |
| [Configuration](docs/configuration.md) | Every setting |
| [Decision log](docs/adr/INDEX.md) | Why the boundaries are where they are |
| [Packaging](packaging/README.md) | Container and Debian package |
| [Evals](evals/README.md) | Measuring whether an agent can drive it |
| [Integration](integration/README.md) | Connecting a client, and a ready-made skill |
| [Roadmap](docs/ru/roadmap.md) | What is done and what is next *(in Russian)* |

## Status

The core works: runs, cancellation, timeouts, recovery after a crash, playbook
storage, providers, redaction, an audit trail and a checked token. Not yet: the
REST surface, cloud providers, execution-environment isolation, and a license
file — see the roadmap.

## License

None yet, which means nobody may legally use, modify or redistribute this.
Apache-2.0 is intended; adding it is blocked on deciding who holds the copyright.
