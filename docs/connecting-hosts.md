# Reaching hosts

The controller runs `ansible-playbook`, so it needs whatever Ansible needs to
reach a host: a key or a password, and a decision about host keys. Nothing here
is invented by this project — but where the credential has to sit depends on how
the controller was installed, and that is not obvious.

*Русская версия: [docs/ru/connecting-hosts.md](ru/connecting-hosts.md)*

Everything below was verified by running it; the container path is covered by
`tests/test_integration_container.py`, which CI runs.

## Where the credential goes

The service runs as an unprivileged user, and that user's home is where ssh
looks. It is not your home.

| Install | Runs as | Home | Put the key at |
|---|---|---|---|
| Container | uid 1000 (`ansible-mcp`) | `/var/lib/ansible-mcp` | `/var/lib/ansible-mcp/.ssh/id_ed25519` |
| Debian package | `ansible-mcp` | `/var/lib/ansible-mcp` | `/var/lib/ansible-mcp/.ssh/id_ed25519` |
| stdio, run by a client | you | your home | `~/.ssh/id_ed25519`, as usual |

A key at the default path is found without an inventory mentioning it. Any other
location has to be named with `ansible_ssh_private_key_file`.

**The mode must be 600.** ssh ignores a key that is group- or world-readable and
the run fails with `Permission denied (publickey)`, which is a confusing way to
learn about a file mode. Checked: at 644 the key is skipped with `bad
permissions`.

## Container

Mount the key read-only at the default path:

```bash
docker run -p 8080:8080 \
  -v ./data:/data \
  -v ./secrets/id_ed25519:/var/lib/ansible-mcp/.ssh/id_ed25519:ro \
  -e ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" \
  ansible-mcp
```

On Linux the file's owner has to be uid 1000 or root, because ssh refuses a key
owned by someone else:

```bash
sudo chown 1000 ./secrets/id_ed25519 && chmod 600 ./secrets/id_ed25519
```

Docker Desktop on macOS maps ownership for you, so this step looks unnecessary
there and is not.

A worked example lives in `docker-compose.yml` under the `controller` profile: it
mounts a key, waits for two SSH test hosts and serves on 8080.

```bash
make keygen
ANSIBLE_MCP_API_KEY=$(openssl rand -hex 32) docker compose --profile controller up -d --wait
```

Then an inventory that says nothing about keys is enough:

```ini
[hosts]
ansible_host_1
ansible_host_2

[hosts:vars]
ansible_user=root
```

## Debian package

The package creates the `ansible-mcp` user and its state directory. The key goes
in that user's `.ssh`, owned by it:

```bash
sudo install -d -o ansible-mcp -g ansible-mcp -m 700 /var/lib/ansible-mcp/.ssh
sudo install -o ansible-mcp -g ansible-mcp -m 600 \
  ~/.ssh/id_ed25519 /var/lib/ansible-mcp/.ssh/id_ed25519
sudo systemctl restart ansible-mcp
```

The unit sets `ProtectHome=true`, so the service cannot read any human's home
directory even if an inventory points at one. `/var/lib/ansible-mcp` is the one
writable path it has.

## Passwords instead of keys

Ansible takes them from the inventory, and `sshpass` is installed in the image
for exactly this:

```ini
[hosts:vars]
ansible_user=deploy
ansible_password=...
ansible_become_password=...
```

Both names contain `password`, so their values are removed from tool output,
error messages and the audit log ([redaction](architecture.md)). Two things that
are still true: the inventory is stored with the task, so the password is in the
database in the clear, and anything Ansible prints that redaction does not
recognize can still leak. A key is better.

Passing them as variables (`variables={"ansible_password": "..."}`) works the
same way and is redacted the same way.

## Host keys

By default ssh refuses an unknown host, which is the behaviour you want and the
one that stops a first run. Two honest options:

**Provide a `known_hosts` file.** Same rules as the key: the service user's home.

```bash
ssh-keyscan -H host1.example.com > known_hosts
sudo install -o ansible-mcp -g ansible-mcp -m 644 \
  known_hosts /var/lib/ansible-mcp/.ssh/known_hosts
```

In a container, mount it at `/var/lib/ansible-mcp/.ssh/known_hosts`.

**Turn checking off, for a lab only.** In the process environment:

```bash
ANSIBLE_HOST_KEY_CHECKING=False
```

or per inventory:

```ini
[hosts:vars]
ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
```

What that gives up: any host that answers on the address is trusted, so anything
able to intercept the connection can impersonate your servers and collect
whatever the playbook sends — including a password from the inventory. The test
hosts in `docker-compose.yml` do this because they are rebuilt constantly and
reachable only on loopback. A real fleet should not.

## Where credentials are never stored

- **Not in a provider's configuration.** A value that looks like a credential is
  refused when the provider is added; the configuration names an environment
  variable instead (ADR-0006).
- **Not in the image.** The key arrives by mount or by install, never by `COPY`.
- **Not in the run directory after the run.** The inventory and the variables
  file are deleted when a run ends, because the task already stores them.

They *are* in the database: `Task.inventory_snapshot` and `Task.variables` hold
what a run was given, because a run cannot be reproduced without them. Treat the
database file accordingly.

## When it does not work

| Symptom | Usually |
|---|---|
| `Permission denied (publickey)` | Key mode not 600, or owned by another user, or not the key the host authorizes |
| `Load key ...: bad permissions` | Mode is 644; ssh skipped the key entirely |
| `Host key verification failed` | No `known_hosts` entry, and checking is on |
| `UNREACHABLE ... Connection timed out` | Routing, not credentials: the container has its own network |
| Works from your shell, not from the service | You are looking at your `~/.ssh`; the service is not |

`get_task_logs` carries the ssh error verbatim, so the line above is in the
output of the failed task.
