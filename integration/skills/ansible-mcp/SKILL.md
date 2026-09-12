---
name: ansible-mcp
description: Run Ansible playbooks through a connected ansible-mcp server and follow the runs. Use when asked to run, schedule or diagnose Ansible automation - "run this playbook", "did that run finish", "why did it fail", "what hosts would this touch", "stop that run". Requires the ansible-mcp MCP server to be connected.
---

# Driving ansible-mcp

The server executes; you decide. It will not write a playbook, pick hosts, or
judge whether an action is wise — that is your job, and it is why the tools are
as small as they are.

## The loop

Runs are asynchronous. `run_playbook` returns a task id and the playbook keeps
going in the background:

1. `run_playbook` with the playbook and where to run it
2. `get_task_status` until the status is no longer `pending` or `running`
3. `get_task_logs` when it failed, or when the output matters

Do not poll faster than about once a second, and do not fetch the whole log
first: `get_task_logs` returns the tail by default, which is where the failure
is. Widen `tail` only if the reason is not visible.

## Saying what to run, and where

Exactly one of each pair, and passing both is refused rather than resolved:

| What | How |
|---|---|
| A playbook you have as text | `playbook="- hosts: all\n  tasks: ..."` |
| A playbook stored on the server | `playbook_name="deploy-nginx"` |
| An inventory you have as text | `inventory="[web]\nweb1.example.com"` |
| A configured source of hosts | `provider="lab"` |

The playbook may be passed as YAML text or as the parsed list of plays; both are
accepted. Tags and variables may be omitted entirely.

If the user gave you both a provider name and inventory text, name the provider
and leave the inventory out.

## Before running something that changes hosts

Two cheap checks worth making when the target is not obviously right:

- `get_inventory(provider=...)` answers "what would this actually touch" without
  starting anything. For a cloud provider the answer changes between calls.
- `list_providers` shows which sources are configured and which currently work —
  a provider whose inventory file has moved is reported with the problem rather
  than failing mid-run.

## Diagnosing a failure

`get_task_status` gives the exit code and, for failures without one, a message.
`get_task_logs` gives what Ansible printed. Secrets are removed from the output
before you see it, so a redacted value in a log is expected, not a bug.

There is no restart: to run the same thing again, call `run_playbook` again. That
creates a new run, and the old one keeps its history.

## Stopping a run

`cancel_task` needs `confirm=true`, because cancelling mid-run leaves the hosts
in whatever state the playbook reached — the applied tasks are not rolled back.
Say that to the user before confirming on their behalf.

There is no "cancel everything": find the ids with `list_tasks(status="running")`
and cancel each.

## Storing playbooks

`save_playbook` keeps a playbook under a name so later runs can reference it, and
validates that it is a well-formed playbook. It is the only structural check
available — there is no separate syntax checker.

Storing a new version does not affect runs already made: each run keeps its own
copy of what it executed, which is what lets you compare two runs of the same
playbook.

## Configuring a source of hosts

```
add_provider(name="lab", plugin_type="static",
             config={"inventory": "[web]\nweb1.example.com"})
```

`static` is built in and takes either `inventory` (the text) or `inventory_file`
(a path, which must be inside a directory the server allows).

Never put a credential in `config`. Name the environment variable instead —
`{"token_env": "YC_TOKEN"}` — and a value that looks like a secret is refused.

## What the server will not do

Asking for any of these means telling the user the server cannot, rather than
reaching for the nearest tool:

- generate or lint a playbook
- restart, retry or resume a run
- schedule anything for later
- tell two callers apart in its audit log
