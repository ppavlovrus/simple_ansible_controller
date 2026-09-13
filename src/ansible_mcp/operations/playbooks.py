"""Keeping playbooks around instead of pasting them into every run."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ansible_mcp.core import InvalidPlaybookError
from ansible_mcp.operations.coercion import as_list, as_yaml_text
from ansible_mcp.operations.errors import UsageError, found, require
from ansible_mcp.operations.limits import (
    MAX_CHECK_OUTPUT_LINES,
    MAX_PLAYBOOKS_PER_CALL,
    PLAYBOOK_PREVIEW_LINES,
)

if TYPE_CHECKING:
    from ansible_mcp.operations.services import Services


async def resolve(services: Services, playbook: Any, playbook_name: str | None) -> str:
    """Return the playbook text, from the argument or from the store.

    Shared by every operation that takes "the playbook or its name", so the
    refusal wording and the coercion stay identical between them.

    Args:
        services: what to look the name up in.
        playbook: the playbook, as YAML text or as the parsed list of plays.
        playbook_name: name of a stored playbook to use instead.

    Returns:
        The playbook as text.

    Raises:
        UsageError: if neither or both were given.
        NotFoundError: if the name is unknown.
    """
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


async def save(
    services: Services,
    name: str,
    content: Any = None,
    description: str | None = None,
    tags: Any = None,
) -> dict[str, Any]:
    """Store a playbook under a name, replacing any playbook of that name.

    Args:
        services: where to store it.
        name: how the playbook will be addressed later.
        content: the playbook, as YAML text or as the parsed list of plays.
        description: what it does, for whoever lists the store next.
        tags: labels to group playbooks by.

    Returns:
        The stored name, when it was updated, and its size.

    Raises:
        UsageError: if the name or content is empty, or the playbook is malformed.
    """
    require(bool(name.strip()), "name is empty")
    require(bool(content), "content is empty: pass the playbook YAML")
    try:
        stored = await services.playbooks.save(
            name,
            as_yaml_text(content, "content"),
            description,
            as_list(tags, "tags"),
        )
    except InvalidPlaybookError as error:
        raise UsageError(str(error)) from error

    return {
        "name": stored.name,
        "updated_at": stored.updated_at,
        "lines": len(stored.content.splitlines()),
    }


async def browse(services: Services, limit: int = 50) -> dict[str, Any]:
    """List stored playbooks alphabetically, without their content.

    Args:
        services: what to list.
        limit: how many to return (at most 100).

    Returns:
        The stored playbooks and whether the limit cut the answer short.

    Raises:
        UsageError: if the limit is outside what a single call may return.
    """
    require(limit > 0, "limit must be at least 1")
    require(limit <= MAX_PLAYBOOKS_PER_CALL, f"limit is capped at {MAX_PLAYBOOKS_PER_CALL}")

    playbooks = await services.playbooks.list(limit)
    return {
        "returned": len(playbooks),
        "has_more": len(playbooks) == limit,
        "playbooks": [
            {
                "name": playbook.name,
                "description": playbook.description,
                "tags": playbook.tags,
                "lines": len(playbook.content.splitlines()),
                "updated_at": playbook.updated_at,
            }
            for playbook in playbooks
        ],
    }


async def read(services: Services, name: str, *, full: bool = False) -> dict[str, Any]:
    """Read a stored playbook, its opening lines unless the whole is asked for.

    Args:
        services: where to read it from.
        name: the stored playbook to read.
        full: return the entire content instead of the opening lines.

    Returns:
        The playbook with its metadata, and whether it was cut short.

    Raises:
        NotFoundError: if nothing is stored under that name.
    """
    playbook = found(
        await services.playbooks.get(name),
        f"no playbook stored as {name!r}; list_playbooks shows what there is",
    )

    lines = playbook.content.splitlines(keepends=True)
    truncated = not full and len(lines) > PLAYBOOK_PREVIEW_LINES
    content = "".join(lines[:PLAYBOOK_PREVIEW_LINES]) if truncated else playbook.content

    return {
        "name": playbook.name,
        "description": playbook.description,
        "tags": playbook.tags,
        "updated_at": playbook.updated_at,
        "total_lines": len(lines),
        "truncated": truncated,
        "content": content,
    }


async def syntax_check(
    services: Services,
    playbook: Any = None,
    playbook_name: str | None = None,
) -> dict[str, Any]:
    """Run Ansible's own ``--syntax-check`` over a playbook, running nothing.

    Args:
        services: what to check with, and where to resolve a name.
        playbook: the playbook, as YAML text or as the parsed list of plays.
        playbook_name: name of a stored playbook to check instead.

    Returns:
        Whether it parsed, and the output Ansible produced when it did not.

    Raises:
        UsageError: if neither or both sources were given.
        NotFoundError: if the name is unknown.
    """
    content = await resolve(services, playbook, playbook_name)
    result = await services.manager.syntax_check(content)
    output = result.output
    lines = output.splitlines()
    truncated = len(lines) > MAX_CHECK_OUTPUT_LINES
    if truncated:
        output = "\n".join(lines[:MAX_CHECK_OUTPUT_LINES])

    return {
        "ok": result.ok,
        "playbook_name": playbook_name,
        "truncated": truncated,
        "output": output,
    }


async def delete(services: Services, name: str) -> dict[str, Any]:
    """Remove a stored playbook. Runs made from it keep their own copy.

    Args:
        services: where to remove it from.
        name: the stored playbook to remove.

    Returns:
        Whether anything was removed.
    """
    deleted = await services.playbooks.delete(name)
    return {
        "name": name,
        "deleted": deleted,
        "note": None if deleted else "no playbook was stored under that name",
    }
