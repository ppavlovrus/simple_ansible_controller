"""Every tool the server exposes, grouped by what it acts on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ansible_mcp.server.tools import playbooks, providers, tasks

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from ansible_mcp.operations import Services

__all__ = ["register_all"]


def register_all(server: MCPServer, services: Services) -> None:
    """Register every tool group on the server."""
    tasks.register(server, services)
    playbooks.register(server, services)
    providers.register(server, services)
