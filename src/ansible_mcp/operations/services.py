"""What an operation acts on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ansible_mcp.core import PlaybookStore, TaskManager
    from ansible_mcp.core.audit import AuditLog
    from ansible_mcp.providers import Providers


@dataclass
class Services:
    """The long-lived objects every operation is performed against."""

    manager: TaskManager
    playbooks: PlaybookStore
    providers: Providers
    audit: AuditLog
