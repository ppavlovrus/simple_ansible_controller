# ADR-0011: A provider reads inventory files only from allowed directories

## Status

Accepted (2026-09-12)

## Context

The static provider can take its inventory from a file rather than from its own
configuration, which is what makes it useful for an inventory some other tool
maintains.

Provider configuration is supplied through a tool call, so in the intended use
an agent writes it. The first implementation read whatever path it was given.
Pointing a provider at `/etc/passwd` and calling `get_inventory` therefore
returned the file's contents to the caller: a read-annotated tool that reads any
file on the host.

The objection that the caller can already read files by running a playbook with
`slurp` is true but beside the point. A run is recorded with its snapshot, its
status and its logs; this path left no trace, and a tool described as "ask a
provider what hosts it resolves to" is not where anyone looks for file access.
Capabilities should not arrive as side effects of unrelated features.

## Decision

A plugin is constructed with the directories this installation permits it to
read from, and a plugin that touches the filesystem must confine itself to them.
The static provider resolves the configured path first, so `..` and symlinks
cannot step out, and refuses anything that does not sit inside an allowed
directory.

By default the only allowed directory is `inventories/` inside the data dir.
`ANSIBLE_MCP_EXTRA_INVENTORY_DIRS` lets the operator, who runs the process, add
more. When no directory is allowed, `inventory_file` is unusable and the error
says to pass the inventory inline instead.

The read policy is part of the plugin contract rather than a check inside one
plugin, so a third-party provider is told what it may read instead of having to
guess.

## Consequences

+ Configuring a provider grants no file access beyond a directory meant for
  inventories.
+ Widening access is an operator's decision in the environment, not a caller's
  decision in a tool call.
+ The refusal explains itself and offers the inline alternative.
- An inventory file kept elsewhere has to be moved, symlinked into an allowed
  directory, or the directory added to the configuration.
- Plugin authors have one more parameter to honour.

## Alternatives considered

- **Trust the configured path, since a playbook could read the file anyway.**
  Rejected: it hides a capability in a feature that does not advertise it, and
  leaves no record of the read.
- **Check the path inside the static provider only.** Rejected: the next plugin
  that reads a file would have to rediscover the rule, and a third-party plugin
  would not know it exists.
- **Allow any path but return only lines that parse as inventory.** Rejected:
  fragile, and still leaks the content of anything that happens to parse.
