# Configuration

Everything is read from the environment under one prefix. There is no
configuration file to find, because the deployment story is a single process
with a single volume.

*Русская версия: [docs/ru/configuration.md](ru/configuration.md)*

## Settings

| Variable | Default | What it does |
|---|---|---|
| `ANSIBLE_MCP_DATA_DIR` | `/data` | Database, playbooks, task artifacts, inventories |
| `ANSIBLE_MCP_TRANSPORT` | `stdio` | `stdio` when a client launches the process, `streamable-http` to serve a port |
| `ANSIBLE_MCP_HOST` | `127.0.0.1` | Address the HTTP transport binds to |
| `ANSIBLE_MCP_PORT` | `8080` | Port the HTTP transport binds to |
| `ANSIBLE_MCP_API_KEY` | none | Bearer token every HTTP request is checked against |
| `ANSIBLE_MCP_MAX_CONCURRENT_TASKS` | `4` | How many playbooks may run at once |
| `ANSIBLE_MCP_RUN_TIMEOUT_SECONDS` | none | How long one run may take before it is cancelled and failed |
| `ANSIBLE_MCP_KEEP_ARTIFACTS_DAYS` | none | How long a finished run's artifacts are kept; unset keeps them forever |
| `ANSIBLE_MCP_EXTRA_INVENTORY_DIRS` | none | Extra directories a provider may read inventory files from |
| `ANSIBLE_MCP_LOG_LEVEL` | `INFO` | Root log level |

## The two that matter

**`ANSIBLE_MCP_API_KEY`.** Required to serve HTTP on anything but loopback, and
checked on every request in constant time. Without it the process exits 2 rather
than serving an endpoint that executes playbooks for whoever reaches the port
(ADR-0012). A loopback bind runs unguarded and says so in the log, because
reaching loopback already means being on the machine.

```bash
openssl rand -hex 32
```

**`ANSIBLE_MCP_RUN_TIMEOUT_SECONDS`.** Unset means a playbook can hang forever
and hold its slot while it does. `ansible-runner` has no timeout of its own, so
this is the only limit there is.

## What a port gives you

`streamable-http` serves both surfaces on the one port and the one token: `/mcp`
for agents, `/api/v1` for people and scripts, with `/api/v1/openapi.json`
describing the second (ADR-0015). `/healthz` is the only path served without a
token. There is no setting to serve one surface without the other: the token
that reaches either reaches both, so the distinction would protect nothing.

## What is kept on disk, and for how long

A finished run leaves its artifacts under `$ANSIBLE_MCP_DATA_DIR/tasks/<id>/`:
the output, the exit code, and one file per Ansible event. The inputs it ran
with are deleted when it ends, because the task already stores them and an
inventory can carry a password.

`ANSIBLE_MCP_KEEP_ARTIFACTS_DAYS` deletes the artifacts of runs older than that
many days, at startup. Unset, nothing is ever deleted and the directory grows
without bound: three runs of a forty-task playbook leave around 90KB across 150
files, so the count of files matters as much as their size.

The task rows are never deleted. They are the history, they are small, and they
hold the snapshots that make a run reproducible, so a pruned run can still be
read — it just has no output any more.

## Where inventory files may live

A provider configured with `inventory_file` may only read from
`$ANSIBLE_MCP_DATA_DIR/inventories` and from the directories named in
`ANSIBLE_MCP_EXTRA_INVENTORY_DIRS`. The path is resolved before it is checked, so
`..` and symlinks cannot step outside.

Provider configuration arrives through a tool call, which means an agent writes
it; without this a "provider" would be a way to read any file on the host and
have it handed back (ADR-0011).

```bash
ANSIBLE_MCP_EXTRA_INVENTORY_DIRS='["/etc/ansible", "/srv/inventories"]'
```

## Provider credentials

Credentials are never part of provider configuration. The configuration names
the environment variable to read them from, and the value stays in the
environment (ADR-0006):

```json
{"plugin_type": "yandex_cloud", "config": {"token_env": "YC_TOKEN", "folder_id": "b1g..."}}
```

A value that looks like a credential is refused when the provider is added,
rather than quietly stored.

## Examples

A client launching the process itself, which needs nothing configured:

```bash
ansible-mcp
```

A service on a host, reachable from elsewhere:

```bash
ANSIBLE_MCP_TRANSPORT=streamable-http \
ANSIBLE_MCP_HOST=0.0.0.0 \
ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" \
ANSIBLE_MCP_DATA_DIR=/var/lib/ansible-mcp \
ANSIBLE_MCP_RUN_TIMEOUT_SECONDS=3600 \
ansible-mcp
```

In a container, where the first three are already set:

```bash
docker run -p 8080:8080 -v ./data:/data -e ANSIBLE_MCP_API_KEY=... ansible-mcp
```

Installed from the package, settings live in
`/etc/ansible-mcp/ansible-mcp.env`, mode 640 because it holds the key. See
[packaging](../packaging/README.md).
