"""Tools for keeping playbooks around instead of pasting them into every run."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.operations import playbooks
from ansible_mcp.operations.errors import confirmed
from ansible_mcp.server.instrumentation import instrumented
from ansible_mcp.server.tools._shared import DELETE, READ, WRITE

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from ansible_mcp.operations import Services


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
        return json.dumps(await playbooks.save(services, name, content, description, tags))

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
        return json.dumps(await playbooks.browse(services, limit))

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
        read = await playbooks.read(services, name, full=full)
        hint = "call again with full=true for the whole playbook" if read["truncated"] else None
        return json.dumps({**read, "hint": hint})

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
        return json.dumps(await playbooks.syntax_check(services, playbook, playbook_name))

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
        return json.dumps(await playbooks.delete(services, name))
