"""Pieces every tool module needs: annotations, limits, and what tools act on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from ansible_mcp.core import PlaybookStore, TaskManager
    from ansible_mcp.core.audit import AuditLog
    from ansible_mcp.providers import Providers

# Hints a client uses to decide how much rope to give a call. "Destructive" here
# means "changes something outside this process", which running a playbook very
# much does.
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
EXECUTE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)
STOP = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

MAX_TASKS_PER_CALL = 100
MAX_PLAYBOOKS_PER_CALL = 100
MAX_LOG_LINES_PER_CALL = 2000
DEFAULT_LOG_LINES = 100
PLAYBOOK_PREVIEW_LINES = 40


@dataclass
class Services:
    """What the tools act on."""

    manager: TaskManager
    playbooks: PlaybookStore
    providers: Providers
    audit: AuditLog
