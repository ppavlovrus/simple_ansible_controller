# Packaging

Two ways to run the service, for two different situations.

| | Size | Isolation | When |
|---|---|---|---|
| Container | 306MB (189MB on Alpine) | Whatever the runtime gives | Anywhere a container runtime exists |
| `.deb` | 65MB installed | systemd sandboxing, and optionally a container per run | A host, and the only way to run playbooks in an execution environment (ADR-0008) |

Both were built and exercised, not just written: the numbers above come from
`docker images` and from `du -sh` over what the package installs into
`/opt/ansible-mcp`.

## Two shapes of the installation

The package installs the same service either way. What differs is where the
playbooks run.

**Without isolation**, which is the default and needs nothing else: playbooks run
on this host, as the `ansible-mcp` user, inside the unit's systemd sandbox. The
API key is shell access to that account, which the [README says
plainly](../README.md#security-the-api-key-is-shell-access).

**With isolation**, playbooks run in a container and the host filesystem is not
there for them to touch (ADR-0008, ADR-0016). It needs rootless podman here, and
an image. Four steps:

```bash
sudo apt install podman

# 1. An execution environment, in the service user's own storage. Rootless
#    podman keeps images per user, so pulling one as yourself or as root puts it
#    somewhere the service cannot see.
sudo -u ansible-mcp env HOME=/var/lib/ansible-mcp XDG_RUNTIME_DIR=/tmp/podman-ansible-mcp \
    podman pull quay.io/ansible/awx-ee:latest

# 2. The drop-in, which is shipped disabled because it relaxes three of the
#    unit's protections. Nothing else in the unit changes.
sudo mkdir -p /etc/systemd/system/ansible-mcp.service.d
sudo cp /usr/share/ansible-mcp/systemd/isolation.conf /etc/systemd/system/ansible-mcp.service.d/

# 3. The settings, in /etc/ansible-mcp/ansible-mcp.env
#      ANSIBLE_MCP_ISOLATION=true
#      ANSIBLE_MCP_CONTAINER_RUNTIME=podman
#      ANSIBLE_MCP_EXECUTION_IMAGE=quay.io/ansible/awx-ee:latest

# 4. Restart. The service refuses to start if the runtime or the image setting
#    is missing, rather than finding out at the first run.
sudo systemctl daemon-reload && sudo systemctl restart ansible-mcp
```

`get_task_status` — or `GET /api/v1/runs/{id}` — then reports the image each run
used, because "it succeeded" should say where.

An image is usable here if it has `ansible-playbook` on its PATH, no
`ENTRYPOINT` of its own, and an ssh client. `tests/fixtures/ee/Containerfile` in
this repository is the smallest example of all three. The subordinate id ranges
podman needs are registered for the service user by the package, and the SSH
credentials at `/var/lib/ansible-mcp/.ssh` are mounted into every run read-only.

This is for the package. The container image does not gain the mode: launching
containers from inside one needs the runtime socket, which is root on the host
and undoes what the isolation was for.

## Container

```bash
docker build -f Containerfile -t ansible-mcp .
docker run -p 8080:8080 -v ./data:/data -e ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" ansible-mcp
```

The key is not optional. The container binds to `0.0.0.0`, and the server
refuses to serve an unauthenticated endpoint reachable off the machine
(ADR-0012); without one it exits 2 with a single line saying so.

`GET /healthz` needs no token and is what `HEALTHCHECK` uses.

The image runs as an unprivileged user, so a mounted volume has to be writable
by uid 1000:

```bash
mkdir -p data && sudo chown 1000:1000 data
```

### The Alpine variant

`Containerfile.alpine` produces the same service in 189MB instead of 306MB. It
is not the default. The control node is where an operator installs Ansible
collections, and a collection with a binary dependency ships manylinux wheels
far more often than musllinux ones: on glibc it installs, on musl it needs a
compiler the runtime image does not carry. Worth switching when the image is
moved around a lot and the collection set is fixed.

## Debian package

```bash
packaging/build-deb.sh            # amd64
packaging/build-deb.sh arm64
```

The build runs inside a Debian container, because the package carries its own
virtualenv and a virtualenv is neither portable across libc nor relocatable: the
console scripts get an absolute shebang, so it has to be built at the path it
will be installed to. (That was a real bug here first: a package whose shebang
pointed at the build directory installed fine and would not start.)

It is also bound to the python minor version that built it -- site-packages sits
under `lib/pythonX.Y` and no other interpreter looks there -- so the control file
declares that version with an upper bound, and `BASE_IMAGE` chooses which one to
produce:

```bash
BASE_IMAGE=ubuntu:24.04 packaging/build-deb.sh     # for a noble host
```

(Also a real bug first: a bookworm package installed happily on Ubuntu 24.04 and
the service then restarted forever on "No module named ansible_mcp".)

Installing:

```bash
sudo dpkg -i dist/ansible-mcp_0.1.0_amd64.deb
sudo editor /etc/ansible-mcp/ansible-mcp.env      # set ANSIBLE_MCP_API_KEY
sudo systemctl enable --now ansible-mcp
```

What it lays down:

| Path | What |
|---|---|
| `/opt/ansible-mcp/venv` | The service and its dependencies |
| `/etc/ansible-mcp/ansible-mcp.env` | Settings, mode 640, root:ansible-mcp |
| `/var/lib/ansible-mcp` | Database, playbooks, task artifacts, inventories |
| `/lib/systemd/system/ansible-mcp.service` | The unit |

The env file is 640 because it holds the API key. The state directory is created
by `postinst` rather than shipped in the package: a directory owned by a package
is deleted on remove, and this one holds the task history. `remove` keeps state,
`purge` drops it along with the user.

### The unit

`ProtectSystem=strict` with a single `ReadWritePaths` for the state directory,
`NoNewPrivileges`, `PrivateTmp`, and no capabilities. This service executes
playbooks, which is the reason to give it less of the host rather than more.

Settings live in the env file, not in the unit, so changing a port does not mean
overriding a unit.

## Which to choose

The container is the quickest path and the right one for CI or a workstation.
The package is the one for a host that should keep running across reboots, and
the only one where execution-environment isolation can work at all: launching
containers from inside a container needs the runtime socket, which is root on
the host and defeats the isolation being asked for (ADR-0008).
