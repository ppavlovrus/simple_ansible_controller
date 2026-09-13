"""Hints a client uses to decide how much rope to give a tool call."""

from __future__ import annotations

from mcp.types import ToolAnnotations

# "Destructive" here means "changes something outside this process", which
# running a playbook very much does.
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
EXECUTE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)
STOP = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
