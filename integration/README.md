# Connecting a client

Two transports, for two situations.

## stdio: the client launches the server

Nothing to configure, nothing listening on a port. The right choice on a
workstation.

Claude Code, Cursor, or anything reading an `mcpServers` block:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "command": "poetry",
      "args": ["run", "ansible-mcp"],
      "env": {
        "ANSIBLE_MCP_DATA_DIR": "/home/you/.local/share/ansible-mcp"
      }
    }
  }
}
```

Installed from the Debian package, the command is the absolute path instead:

```json
{
  "command": "/opt/ansible-mcp/venv/bin/ansible-mcp",
  "env": { "ANSIBLE_MCP_DATA_DIR": "/var/lib/ansible-mcp" }
}
```

## HTTP: the server is already running

For an agent on another machine, or a server shared by several clients.

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "type": "http",
      "url": "https://ansible-mcp.example.com/mcp",
      "headers": { "Authorization": "Bearer ${ANSIBLE_MCP_API_KEY}" }
    }
  }
}
```

The token is required for anything but a loopback endpoint, and is checked on
every request. `GET /healthz` needs no token and is what a load balancer or
systemd probe should use.

Keep the key out of the client configuration file where the client supports
environment substitution, as above. One key covers the whole instance, so the
audit log records what was done and not by whom.

## The skill

`skills/ansible-mcp/` is a ready-made skill for Claude Code: the loop to follow,
which of the paired arguments to use, what to check before touching hosts, and
the four things the server will not do. Copy it into `~/.claude/skills/` or a
project's `.claude/skills/`.

It exists because tool descriptions answer "what does this tool do" and a skill
answers "how do I work with this server" — the second does not fit in a
docstring.

## Reaching the hosts

Connecting a client is half of it; the server then needs credentials for the
hosts it will manage, and where those have to sit depends on how it was
installed — the service user's home is not yours. See
[docs/connecting-hosts.md](../docs/connecting-hosts.md), and
`docker compose --profile controller up` for a worked example with two SSH hosts.

## Checking a connection

```bash
curl -fsS http://127.0.0.1:8080/healthz
```

Returns the version and counts of tasks by status. If that answers and a tool
call returns 401, the token is wrong; if it does not answer at all, the server is
not up. Ask a connected client to list the tools to see all thirteen.
