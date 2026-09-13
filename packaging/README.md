# Packaging

Two ways to run the service, for two different situations.

| | Size | Isolation | When |
|---|---|---|---|
| Container | 351MB (237MB on Alpine) | Whatever the runtime gives | Anywhere a container runtime exists |
| `.deb` | 65MB installed | systemd sandboxing | A host, and the only way to enable execution environments (ADR-0008) |

Both were built and exercised, not just written: the numbers above come from
`docker images` and from `du -sh` over what the package installs into
`/opt/ansible-mcp`.

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

`Containerfile.alpine` produces the same service in 237MB instead of 351MB. It
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
