# User guide

Installing the controller, connecting a client, and everything it can do — in
the order you will need it.

*Русская версия: [docs/ru/user-guide.md](ru/user-guide.md)*

Every response shown below was captured from a running server, not written by
hand. Timestamps and ids differ; the shapes do not.

## What you are installing

A service that runs Ansible playbooks on request and keeps the history, logs and
artifacts of every run. Its primary interface is MCP, so an AI agent drives it
directly.

It is a **dumb executor**: it does not write playbooks, choose hosts, or judge
whether running something is wise. You (or your agent) decide; it executes and
records. If you were expecting a platform that reviews your automation, this is
not it, and [the concept](concept.md) explains why.

## 1. Install

Three ways, for three situations.

### From the source tree, for a client to launch

The shortest path, and the one with no network surface at all: the client starts
the process and talks to it over stdin/stdout.

```bash
git clone https://github.com/ppavlovrus/simple_ansible_controller
cd simple_ansible_controller
poetry install
poetry run ansible-mcp        # speaks MCP on stdio; ctrl-c to stop
```

Needs Python 3.11 or newer and Poetry.

### As a container, to serve over HTTP

For an agent on another machine, or several clients sharing one controller.

```bash
docker build -f Containerfile -t ansible-mcp .
mkdir -p data && sudo chown 1000:1000 data     # the image runs as uid 1000

docker run -d --name ansible-mcp -p 8080:8080 \
  -v ./data:/data \
  -e ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" \
  ansible-mcp
```

The key is not optional. The container listens beyond loopback, and the server
exits rather than serve an endpoint that executes playbooks for anyone who
reaches the port.

Check it came up — this endpoint needs no token:

```console
$ curl -s http://127.0.0.1:8080/healthz
{"status":"ok","version":"0.1.0","tasks":{"pending":0,"running":0,"success":0,"failed":0,"cancelled":0},"failed_calls":0}
```

`Containerfile.alpine` builds the same service in a noticeably smaller image at
the cost of musl; [packaging](../packaging/README.md) has the sizes and when that
trade is worth making.

### As a Debian package, to run as a service

For a host that should keep the controller running across reboots. This is also
the only install where execution-environment isolation will be able to work (ADR-0008).

```bash
packaging/build-deb.sh amd64                      # or arm64
sudo dpkg -i dist/ansible-mcp_0.1.0_amd64.deb
sudo editor /etc/ansible-mcp/ansible-mcp.env      # set ANSIBLE_MCP_API_KEY
sudo systemctl enable --now ansible-mcp
```

Settings live in that env file, not in the unit. Everything it installs and what
survives a remove is in [packaging](../packaging/README.md).

## 2. Connect a client

For stdio, point the client at the command:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "command": "poetry",
      "args": ["run", "ansible-mcp"],
      "env": { "ANSIBLE_MCP_DATA_DIR": "/home/you/.local/share/ansible-mcp" }
    }
  }
}
```

For HTTP, point it at the URL and pass the token:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "type": "http",
      "url": "http://your-host:8080/mcp",
      "headers": { "Authorization": "Bearer ${ANSIBLE_MCP_API_KEY}" }
    }
  }
}
```

More variants, and a ready-made skill that teaches an agent the workflow, are in
[integration](../integration/README.md).

## 3. Give it access to your hosts

The controller reaches hosts the way Ansible does: a key or a password, plus a
decision about host keys. The one thing that catches everybody out is *where* the
credential has to sit — the service user's home is not yours.

[Reaching hosts](connecting-hosts.md) covers it per install method, with the
exact paths, modes and owners. Read it before the first run against a real host.

## 4. Your first run, end to end

This is the whole workflow. Run these as tool calls from your client; the
responses are what the server actually returned.

**Check the playbook parses.** Contacts nothing, records nothing:

```console
syntax_check_playbook(playbook: "---\n- name: Make sure nginx is installed\n  hosts: all\n  ...")

{"ok": true, "playbook_name": null, "truncated": false, "output": "playbook: playbook.yml"}
```

**Store it under a name**, so later runs need not carry the text:

```console
save_playbook(name: "install-nginx", content: "...", description: "Installs nginx", tags: ["web"])

{"name": "install-nginx", "updated_at": "2026-09-12T18:38:15+00:00", "lines": 8}
```

**Configure where the hosts come from:**

```console
add_provider(name: "lab", plugin_type: "static", config: {"inventory": "[web]\nweb1.example.com\n"})

{"name": "lab", "plugin_type": "static", "usable": true}
```

**Ask what it would resolve to**, before anything runs:

```console
get_inventory(provider: "lab")

{"provider": "lab", "total_lines": 2, "truncated": false, "inventory": "[web]\nweb1.example.com\n"}
```

**Dry run first.** This contacts the hosts and changes nothing:

```console
run_playbook(playbook_name: "install-nginx", provider: "lab", check: true, diff: true)

{"task_id": "321e2d74...", "status": "pending", "check_mode": true,
 "hint": "poll get_task_status; read output with get_task_logs"}
```

**Poll until it is finished.** Note `check_mode` in the answer: a successful
check run has applied nothing, and this is how you know which it was:

```console
get_task_status(task_id: "321e2d74...")

{"task_id": "321e2d74...", "status": "success", "playbook_name": "install-nginx",
 "provider_name": "lab", "started_at": "...", "finished_at": "...", "exit_code": 0,
 "error_message": null, "check_mode": true, "diff_mode": true}
```

**Then run it for real** — same call without `check` — and read the output:

```console
get_task_logs(task_id: "b4890876...", tail: 6)

{"task_id": "b4890876...", "returned_lines": 6, "next_line": 10,
 "may_have_more": false, "output": "ok: [web1] => {\n    \"msg\": \"...\"\n}\n\nPLAY RECAP ..."}
```

That is the loop: check, dry run, run, poll, read.

## What it can do

### Run a playbook

`run_playbook` takes what to run and where, one of each pair:

| What to run | Where |
|---|---|
| `playbook` — the YAML itself | `inventory` — the inventory text |
| `playbook_name` — something stored here | `provider` — a configured source |

Passing both of a pair is refused rather than resolved, because a run that
quietly used the other source than you meant is worse than an error. The playbook
may be YAML text or the already-parsed list of plays.

Extras: `variables` (Ansible's `--extra-vars`), `tags`, `check` (dry run), `diff`.

### Follow a run

`get_task_status` gives the status — `pending`, `running`, `success`, `failed`,
`cancelled` — with timestamps, exit code, and whether it was a dry run.

`get_task_logs` gives the output, the last lines by default. When following a run
that is still going, pass the previous `next_line` back as `after_line` to get
only what is new instead of the same tail again.

`list_tasks` lists recent runs, newest first, filterable by status — useful for
"is anything still running" and for finding an id you did not keep.

### Stop a run

`cancel_task` needs `confirm=true`:

```console
cancel_task(task_id: "b4890876...")

{"error": "cancelling task b4890876... is destructive and was not confirmed.
           Re-issue the call with confirm=true if this is intended."}
```

Cancelling mid-run leaves the hosts in whatever state the playbook reached: the
tasks already applied are not rolled back. There is no restart — to run the same
thing again, call `run_playbook` again, which creates a new run and leaves the
old one in the history.

### Keep playbooks

`save_playbook`, `list_playbooks`, `get_playbook`, `delete_playbook`.

Storing a new version under the same name does not change runs already made: each
run keeps its own copy of exactly what it executed. That is what lets you compare
two runs of "the same" playbook months apart.

`get_playbook` returns the first 40 lines unless you pass `full=true`, because a
long playbook in an agent's context is rarely what was wanted.

### Configure where hosts come from

`add_provider`, `list_providers`, `get_inventory`, `delete_provider`.

`static` is the built-in plugin: an inventory written into the configuration, or
read from a file at run time. Other plugins register through the
`ansible_mcp.providers` entry point group; cloud providers are planned, not
built.

`list_providers` says whether each one currently works, so a provider whose file
has moved shows up with the problem rather than failing in the middle of a run.

**Credentials never go in a provider's configuration.** Name the environment
variable instead — `{"token_env": "YC_TOKEN"}` — and a value that looks like a
secret is refused outright.

### Check without running

`syntax_check_playbook` parses a playbook — text or stored — and says whether it
is valid, contacting nothing and recording no task. It runs Ansible's own
`--syntax-check`, so it catches more than the shape check `save_playbook` does.

For "what would this *do*", that is `run_playbook` with `check=true`: a dry run
connects to the hosts and reports what would change.

## What it will not do

Not missing features — decisions, each with its reasoning in the
[decision log](adr/INDEX.md):

- **Write or lint playbooks.** Generation belongs to the agent calling this.
- **Judge whether a playbook is safe.** The prototype's pattern-matching
  "safety" was removed because it gave the illusion of a guarantee.
- **Restart, retry or resume a run.**
- **Schedule anything.** No cron, no delayed runs.
- **Tell two callers apart.** One key per instance; the audit log records what
  was done, not by whom.
- **Serve a web UI**, or scale past one node.

Outgrowing these is the signal to move to a full platform like AWX or Ansible
Automation Platform.

## Security, in one paragraph

Whoever holds the API key can execute arbitrary code on the controller host: a
playbook with `hosts: localhost` runs *here*, and the controller runs whatever it
is handed. Treat the key as an SSH login to that machine. Run the service
unprivileged, keep the endpoint off the network unless it must be on it, and
prefer stdio where the client launches the process and no port exists. The full
version of this, including what would actually fix it, is in the
[README](../README.md#security-the-api-key-is-shell-access).

## When something goes wrong

| What you see | What it means |
|---|---|
| `refusing to listen on 0.0.0.0: ... requires ANSIBLE_MCP_API_KEY` | Serving beyond loopback without a token. Set one. |
| `401` from `/mcp`, but `/healthz` answers | The server is fine; the token is wrong or missing. |
| `both playbook and playbook_name were given` | `playbook_name` refers to something already stored, not a label for text you are passing. |
| `the playbook is not valid YAML: ... on line N` | Exactly that; the line is quoted in the message. |
| Task stays `pending` | All run slots are busy. `list_tasks(status: "running")` shows what is holding them; `ANSIBLE_MCP_MAX_CONCURRENT_TASKS` raises the limit. |
| `Permission denied (publickey)` in the logs | The credential, not the controller. [Reaching hosts](connecting-hosts.md) has a table of these. |
| `[redacted]` where you expected a value | Working as intended: secret-looking values are removed from output, messages and the audit log. |
| Escape codes in the log output | Ansible's colour codes, passed through verbatim. Harmless to an agent; strip them if a human is reading. |

The audit trail in the database answers "what was called, how it ended, and which
run it produced" — including calls that were refused. No tool exposes it; read it
with sqlite3 against `$ANSIBLE_MCP_DATA_DIR/ansible_mcp.db`.

## Where to go next

| | |
|---|---|
| [Configuration](configuration.md) | Every setting, including retention and timeouts |
| [Reaching hosts](connecting-hosts.md) | Keys, passwords, host keys |
| [Packaging](../packaging/README.md) | Container and package details |
| [Integration](../integration/README.md) | Client configuration and the bundled skill |
| [Concept](concept.md) | Why it is shaped this way |
| [Architecture](architecture.md) | How it works inside |
| [Decision log](adr/INDEX.md) | Why each boundary is where it is |
