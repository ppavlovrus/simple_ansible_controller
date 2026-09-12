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
MAX_CHECK_OUTPUT_LINES = 200


async def resolve_playbook(
    services: Services,
    playbook: object,
    playbook_name: str | None,
) -> str:
    """Return the playbook text, from the argument or from the store.

    Shared by the tools that take "the playbook or its name", so the refusal
    wording and the coercion stay identical between them.

    Raises:
        UsageError: if neither or both were given, or the name is unknown.
    """
    from ansible_mcp.server.coercion import as_yaml_text
    from ansible_mcp.server.errors import found, require

    # The observed mistake is not confusion about which to use: it is reading
    # playbook_name as "the name for this text". Saying so is what gets a model
    # out of retrying the identical call.
    require(
        bool(playbook) != bool(playbook_name),
        "both playbook and playbook_name were given. playbook_name refers to a playbook "
        "already stored on this server; it is not a label for the text you are passing. "
        "To use the text you have, pass playbook alone and drop playbook_name. To store "
        "it under a name first, call save_playbook."
        if playbook and playbook_name
        else "neither playbook nor playbook_name was given; pass exactly one. Use playbook "
        "with the YAML text, or playbook_name for a playbook already stored here.",
    )

    if playbook_name:
        stored = found(
            await services.playbooks.get(playbook_name),
            f"no playbook stored as {playbook_name!r}; list_playbooks shows what there is",
        )
        return stored.content
    return as_yaml_text(playbook, "playbook")


@dataclass
class Services:
    """What the tools act on."""

    manager: TaskManager
    playbooks: PlaybookStore
    providers: Providers
    audit: AuditLog
