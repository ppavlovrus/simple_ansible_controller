"""Storing playbooks and checking them, over HTTP.

A stored playbook is addressed by its name, so PUT is how one is written: the
name is in the path, and saving the same name again replaces the content, which
is what PUT means. A syntax check is not a playbook, so it is not under one: it
is something you create and read the answer of, for text that need not be
stored at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from ansible_mcp.api.models import SavePlaybookRequest, SyntaxCheckRequest
from ansible_mcp.operations import playbooks
from ansible_mcp.operations.errors import NotFoundError
from ansible_mcp.operations.recording import record

if TYPE_CHECKING:
    from ansible_mcp.operations import Services


def router(services: Services, prefix: str) -> APIRouter:
    """Return the playbook routes, bound to the services they act on."""
    api = APIRouter(prefix=prefix, tags=["playbooks"])

    @api.get("/playbooks")
    async def list_playbooks(limit: int = 50) -> dict[str, Any]:
        """List stored playbooks alphabetically, without their content.

        Answers names, descriptions, tags and sizes. limit may not exceed 100.
        """
        async with record(services.audit, "list_playbooks", {"limit": limit}):
            return await playbooks.browse(services, limit)

    @api.put("/playbooks/{name}")
    async def save_playbook(name: str, body: SavePlaybookRequest) -> dict[str, Any]:
        """Store a playbook under this name, replacing what was there.

        The content is checked for being a well-formed playbook and a malformed
        one is refused. That check is shallow: POST /syntax-checks runs Ansible's
        own --syntax-check and catches what this does not.

        Runs already created from an earlier version are unaffected: each run
        keeps its own copy of what it executed.
        """
        arguments = {"name": name, **body.model_dump(exclude_none=True)}
        async with record(services.audit, "save_playbook", arguments):
            return await playbooks.save(
                services,
                name,
                body.content,
                body.description,
                body.tags,
            )

    @api.get("/playbooks/{name}")
    async def get_playbook(name: str, full: bool = False) -> dict[str, Any]:
        """Read a stored playbook.

        Only the opening lines come back unless full=true is asked for, and
        truncated says which of the two happened.
        """
        async with record(services.audit, "get_playbook", {"name": name, "full": full}):
            return await playbooks.read(services, name, full=full)

    @api.delete("/playbooks/{name}")
    async def delete_playbook(name: str) -> dict[str, Any]:
        """Remove a stored playbook.

        Runs already made from it keep their own copy, so history is not lost.
        There is no confirmation to pass: on this surface the method is the
        statement of intent (ADR-0015).
        """
        async with record(services.audit, "delete_playbook", {"name": name}):
            removed = await playbooks.delete(services, name)
            if not removed["deleted"]:
                message = f"no playbook stored as {name!r}"
                raise NotFoundError(message)
            return removed

    @api.post("/syntax-checks")
    async def check_syntax(body: SyntaxCheckRequest) -> dict[str, Any]:
        """Parse a playbook and report whether it is valid YAML and valid Ansible.

        Reads the text; contacts nothing, runs nothing, records no run. Pass the
        playbook itself or the name of a stored one, and read ok, plus the output
        Ansible produced -- with the offending line in it -- when ok is false.
        """
        async with record(
            services.audit,
            "syntax_check_playbook",
            body.model_dump(exclude_none=True),
        ):
            return await playbooks.syntax_check(services, body.playbook, body.playbook_name)

    return api
