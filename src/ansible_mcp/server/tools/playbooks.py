"""Tools for keeping playbooks around instead of pasting them into every run."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.core import InvalidPlaybookError
from ansible_mcp.server.coercion import as_list, as_yaml_text
from ansible_mcp.server.errors import UsageError, confirmed, found, require
from ansible_mcp.server.instrumentation import instrumented
from ansible_mcp.server.tools._shared import (
    DELETE,
    MAX_CHECK_OUTPUT_LINES,
    MAX_PLAYBOOKS_PER_CALL,
    PLAYBOOK_PREVIEW_LINES,
    READ,
    WRITE,
    Services,
    resolve_playbook,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def register(server: MCPServer, services: Services) -> None:
    """Register the playbook tools."""
    audited = instrumented(services.audit)

    @server.tool(annotations=WRITE)
    @audited
    async def save_playbook(
        name: str,
        content: Any = None,
        description: str | None = None,
        tags: Any = None,
    ) -> str:
        """Store a playbook under a name so runs can refer to it.

        Saving the same name again replaces the content. Runs already created from
        an earlier version are unaffected: each run keeps its own copy of what it
        executed.

        The content is checked for being a well-formed playbook (valid YAML, a
        list of plays) and a malformed one is refused. That check is shallow:
        syntax_check_playbook runs Ansible's own --syntax-check and catches things this
        does not, so reach for it when a playbook is about to be run. Neither
        judges whether the playbook is a good idea.

        Args:
            name: how the playbook will be addressed later.
            content: the playbook, as YAML text or as the parsed list of plays.
            description: what it does, for whoever lists the store next.
            tags: labels to group playbooks by.

        Returns:
            A JSON object with the stored name and when it was updated.
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

        return json.dumps(
            {
                "name": stored.name,
                "updated_at": stored.updated_at,
                "lines": len(stored.content.splitlines()),
            },
        )

    @server.tool(annotations=READ)
    @audited
    async def list_playbooks(limit: int = 50) -> str:
        """List stored playbooks, alphabetically.

        Returns names, descriptions and sizes, not the playbooks themselves: use
        get_playbook to read one.

        Args:
            limit: how many to return (at most 100).

        Returns:
            A JSON object with the stored playbooks.
        """
        require(limit > 0, "limit must be at least 1")
        require(limit <= MAX_PLAYBOOKS_PER_CALL, f"limit is capped at {MAX_PLAYBOOKS_PER_CALL}")

        playbooks = await services.playbooks.list(limit)
        return json.dumps(
            {
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
            },
        )

    @server.tool(annotations=READ)
    @audited
    async def get_playbook(name: str, full: bool = False) -> str:
        """Read a stored playbook.

        Only the first lines are returned by default, because a long playbook in
        the context window is rarely what is wanted: ask for the whole thing
        explicitly when it needs editing.

        Args:
            name: the stored playbook to read.
            full: return the entire content instead of the opening lines.

        Returns:
            A JSON object with the content, and whether it was cut short.
        """
        playbook = found(
            await services.playbooks.get(name),
            f"no playbook stored as {name!r}; list_playbooks shows what there is",
        )

        lines = playbook.content.splitlines(keepends=True)
        truncated = not full and len(lines) > PLAYBOOK_PREVIEW_LINES
        content = "".join(lines[:PLAYBOOK_PREVIEW_LINES]) if truncated else playbook.content

        return json.dumps(
            {
                "name": playbook.name,
                "description": playbook.description,
                "tags": playbook.tags,
                "updated_at": playbook.updated_at,
                "total_lines": len(lines),
                "truncated": truncated,
                "content": content,
                "hint": "call again with full=true for the whole playbook" if truncated else None,
            },
        )

    @server.tool(annotations=READ)
    @audited
    async def syntax_check_playbook(playbook: Any = None, playbook_name: str | None = None) -> str:
        """Parse a playbook and report whether it is valid YAML and valid Ansible.

        Reads the text; contacts nothing. Catches broken YAML, a malformed play
        or an unknown top-level key, by running Ansible's own --syntax-check. No
        task is recorded, because nothing was run.

        This answers "is this playbook well formed", and nothing else. Two
        questions it does NOT answer:

        - "what would this do to the hosts" -- that is run_playbook with
          check=true, which connects to them and reports what would change.
        - "is this playbook a good idea" -- nobody here judges that.

        Args:
            playbook: the playbook, as YAML text or as the parsed list of plays.
            playbook_name: name of a stored playbook to check instead.

        Returns:
            A JSON object with ok, and the output Ansible produced when it is
            false. The offending line is in that output.
        """
        content = await resolve_playbook(services, playbook, playbook_name)
        result = await services.manager.syntax_check(content)
        output = result.output
        lines = output.splitlines()
        truncated = len(lines) > MAX_CHECK_OUTPUT_LINES
        if truncated:
            output = "\n".join(lines[:MAX_CHECK_OUTPUT_LINES])

        return json.dumps(
            {
                "ok": result.ok,
                "playbook_name": playbook_name,
                "truncated": truncated,
                "output": output,
            },
        )

    @server.tool(annotations=DELETE)
    @audited
    async def delete_playbook(name: str, confirm: bool = False) -> str:
        """Remove a stored playbook.

        Runs already made from it keep their own copy, so history is not lost.
        The playbook itself is gone for good, which is why this needs
        confirmation.

        Args:
            name: the stored playbook to remove.
            confirm: must be true for the deletion to happen.

        Returns:
            A JSON object saying whether anything was removed.
        """
        confirmed(confirm, f"deleting playbook {name!r}")
        deleted = await services.playbooks.delete(name)
        return json.dumps(
            {
                "name": name,
                "deleted": deleted,
                "note": None if deleted else "no playbook was stored under that name",
            },
        )
