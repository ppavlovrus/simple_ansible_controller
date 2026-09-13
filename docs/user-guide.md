# User guide

Installing the controller, connecting a client, and everything it can do — in
the order you will need it.

*Русская версия: [docs/ru/user-guide.md](ru/user-guide.md)*

Every response shown below was captured from a running server, not written by
hand. Timestamps and ids differ; the shapes do not.

## What you are installing

A service that runs Ansible playbooks on request and keeps the history, logs and
artifacts of every run. Its primary interface is MCP, so an AI agent drives it
directly; when it serves HTTP, the same operations are also at `/api/v1` for a
person with curl.

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

## The REST surface, for people and scripts

Everything above goes through an agent. When you want to drive the controller
yourself, the same operations are at `/api/v1`, on the same port as `/mcp` and
behind the same token. MCP is still the primary interface (ADR-0002); this is
the door for curl, cron and whatever you already script with.

It is only served by the HTTP transport. Running over stdio, there is no port
and no REST.

| Tool | Route |
|---|---|
| `run_playbook` | `POST /api/v1/runs` |
| `get_task_status` | `GET /api/v1/runs/{id}` |
| `get_task_logs` | `GET /api/v1/runs/{id}/logs?tail=&after_line=` |
| `cancel_task` | `POST /api/v1/runs/{id}/cancel` |
| `list_tasks` | `GET /api/v1/runs?status=&limit=` |
| `save_playbook` | `PUT /api/v1/playbooks/{name}` |
| `list_playbooks` / `get_playbook` | `GET /api/v1/playbooks` / `GET /api/v1/playbooks/{name}?full=` |
| `delete_playbook` | `DELETE /api/v1/playbooks/{name}` |
| `syntax_check_playbook` | `POST /api/v1/syntax-checks` |
| `add_provider` / `list_providers` | `PUT /api/v1/providers/{name}` / `GET /api/v1/providers` |
| `get_inventory` | `GET /api/v1/providers/{name}/inventory?full=` |
| `delete_provider` | `DELETE /api/v1/providers/{name}` |

The whole loop, against a server started with `ANSIBLE_MCP_API_KEY=s3cret`:

```console
$ export AUTH="Authorization: Bearer s3cret"
$ export API=http://127.0.0.1:8080/api/v1

$ curl -s -X PUT $API/playbooks/site -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"content\": $(jq -Rs . < site.yml), \"description\": \"say hello\"}"
{"name":"site","updated_at":"2026-09-13T09:05:56.480931+00:00","lines":8}

$ curl -s -X PUT $API/providers/lab -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"plugin_type":"static","config":{"inventory":"[all]\nlocalhost ansible_connection=local\n"}}'
{"name":"lab","plugin_type":"static","usable":true}

$ curl -si -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site","provider":"lab"}'
HTTP/1.1 202 Accepted
location: /api/v1/runs/8aeac1aeb682464c81b55b0a338e45ec

{"task_id":"8aeac1aeb682464c81b55b0a338e45ec","status":"pending","check_mode":false}

$ curl -s $API/runs/8aeac1aeb682464c81b55b0a338e45ec -H "$AUTH" | jq -c '{status, exit_code, check_mode}'
{"status":"success","exit_code":0,"check_mode":false}

$ curl -s "$API/runs/8aeac1aeb682464c81b55b0a338e45ec/logs?tail=3" -H "$AUTH" | jq -r .output
PLAY RECAP *********************************************************************
localhost                  : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

(Ansible's colour codes are in there too; your terminal renders them, and an
agent ignores them.)

A dry run is the same call with `"check": true`, and the answer says so — as
does the run afterwards, because "succeeded" would otherwise read as "applied":

```console
$ curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site","provider":"lab","check":true}'
{"task_id":"359ae9d780144e42bb38023161d78c8a","status":"pending","check_mode":true}
```

Checking a playbook parses it and runs nothing, so no run appears in the list:

```console
$ curl -s -X POST $API/syntax-checks -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site"}'
{"ok":true,"playbook_name":"site","truncated":false,"output":"playbook: playbook.yml"}
```

Refusals come back as one sentence with a status code, never as a stack trace:

```console
$ curl -s $API/runs/no-such-run -H "$AUTH"
{"error":"no task with id 'no-such-run'"}

$ curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' -d '{"playbook_name":"site"}'
{"error":"neither inventory nor provider was given; pass exactly one. Use inventory with the INI or YAML text, or provider with the name of a configured source."}

$ curl -s $API/runs -H 'Authorization: Bearer wrong'
{"error": "a bearer token is required"}
```

| Code | Meaning |
|---|---|
| 202 | The run was accepted; it has not finished |
| 400 | The request was wrong — including a field you misspelled, which is refused rather than ignored |
| 401 | No token, or the wrong one |
| 404 | What you named is not here |
| 500 | A defect in this service; the traceback is in its log, not in the answer |

Two differences from the tools are deliberate (ADR-0015). There is no
`confirm=true`: `DELETE` and `POST .../cancel` already say what you meant.
And `DELETE` answers 404 when there was nothing to delete, where the tool
answers `deleted: false`.

The schema is at `/api/v1/openapi.json`, behind the token like everything else.
The interactive pages are off on purpose: they load their JavaScript from a CDN,
and this service is built to run where there may be no route to one.

## Running playbooks in a container

By default a playbook runs on the controller itself, which is why the API key is
shell access to that machine. Turning isolation on moves execution into a
container, and `hosts: localhost` then means the container rather than your
host:

```bash
ANSIBLE_MCP_ISOLATION=true
ANSIBLE_MCP_CONTAINER_RUNTIME=podman
ANSIBLE_MCP_EXECUTION_IMAGE=quay.io/ansible/awx-ee:latest
```

It is off by default because it needs a container runtime, and this service
promises to need none. The [packaging notes](../packaging/README.md#two-shapes-of-the-installation)
have the whole setup for the Debian package: rootless podman, the image in the
service user's own storage, a systemd drop-in. The container deployment does not
offer the mode — it is already isolated from its host, and reaching a runtime
from inside a container means handing over the runtime socket.

You turn it on for the installation; a run cannot turn it off. It may name a
different image, and what it actually ran in comes back with its status:

```console
$ curl -s $API/runs/8aeac1ae... -H "$AUTH" | jq -c '{status, execution_environment}'
{"status":"success","execution_environment":"quay.io/ansible/awx-ee:latest"}
```

An image works here if it has three things. `ansible-playbook` on its PATH; no
`ENTRYPOINT` of its own, because the command to run is appended after the image
name and an entrypoint swallows it; and an ssh client, without which the run
reaches nothing but localhost. Any execution environment built for AWX has all
three; `tests/fixtures/ee/Containerfile` in this repository is the smallest
thing that does.

Two consequences worth knowing before you turn it on. Ansible and its
collections now come from the image rather than from the host, which is the
point — reproducibility — and also a new way to fail: a playbook needing a
collection the image does not carry. And a playbook that legitimately wrote
something on the controller writes it inside the container instead, where it
disappears with the run.

What isolation does not do is protect the hosts you manage. Whoever holds the
API key can still run any playbook against everything your credentials reach.
It bounds the damage on the controller, not on the fleet.

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
prefer stdio where the client launches the process and no port exists. What
actually fixes the first sentence is turning isolation on, so that "here" is a
container rather than your host; what it does not fix is the fleet. The full
version is in the
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
| `Unable to execute ssh command line on a controller: ... No such file or directory: b'ssh'` | Isolation is on and the execution environment has no ssh client. It needs one; see the image requirements above. |
| Every run fails with `table tasks has no column named ...` | The data directory was created by an older version, and there are no migrations yet: the schema is created, never altered. Start with a fresh data directory, or move `ansible_mcp.db` aside and lose the run history. A container keeps `/data` in a volume, so this survives a new image. |

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
