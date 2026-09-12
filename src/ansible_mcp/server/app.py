"""Wiring the pieces together into a server that can be run.

Construction is synchronous so the tools can close over a task manager that
exists before the server starts. Everything that needs the event loop, including
the schema and the recovery of tasks interrupted by a restart, happens in the
lifespan.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer

from ansible_mcp import __version__
from ansible_mcp.core import Executor, TaskManager
from ansible_mcp.db import create_engine, create_schema, create_session_factory
from ansible_mcp.server.tools import register

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from ansible_mcp.config import Settings

log = logging.getLogger("ansible_mcp.server")

LOOPBACK_ADDRESSES = frozenset({"127.0.0.1", "::1", "localhost"})

INSTRUCTIONS = """\
A minimal Ansible controller. Give it a playbook and an inventory and it runs
them, keeping the history, the logs and the artifacts of every run.

Runs are asynchronous: run_playbook returns a task id immediately, then
get_task_status and get_task_logs follow it. Nothing here writes playbooks or
decides what to run: that is the calling agent's job.
"""


@dataclass
class Application:
    """A server and the objects it owns."""

    server: MCPServer
    manager: TaskManager
    engine: AsyncEngine


def build_application(settings: Settings) -> Application:
    """Construct the server, its task manager and its store.

    Args:
        settings: configuration to build from.

    Returns:
        The application, ready to be run. Nothing has touched the disk yet.
    """
    engine = create_engine(settings.database_path)
    manager = TaskManager(
        create_session_factory(engine),
        Executor(settings.tasks_dir),
        max_concurrent_tasks=settings.max_concurrent_tasks,
        run_timeout_seconds=settings.run_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        await create_schema(engine)
        interrupted = await manager.recover_interrupted()
        log.info("started; %d interrupted task(s) failed on startup", interrupted)
        try:
            yield {}
        finally:
            await manager.shutdown()
            await engine.dispose()

    server = MCPServer(
        name="ansible-mcp",
        version=__version__,
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
    )
    register(server, manager)
    return Application(server=server, manager=manager, engine=engine)


def ensure_safe_to_expose(settings: Settings) -> None:
    """Refuse to serve HTTP anywhere but loopback.

    Anyone who reaches this endpoint can execute arbitrary playbooks on the hosts
    it can see, and nothing verifies a caller yet: ``ANSIBLE_MCP_API_KEY`` is
    read but not checked against incoming requests. Accepting the key as
    permission to bind publicly would be worse than refusing outright, because
    the configuration would look protected while being open.

    Until token verification exists, remote access belongs behind something that
    does authenticate, reached over loopback (ADR-0007, ADR-0010).

    Raises:
        RuntimeError: if the configuration would expose an open endpoint.
    """
    if settings.transport == "stdio" or settings.host in LOOPBACK_ADDRESSES:
        return
    message = (
        f"refusing to listen on {settings.host}: incoming requests are not "
        f"authenticated yet, so HTTP is restricted to loopback. Put a "
        f"proxy that authenticates in front of it, or use the stdio transport."
    )
    raise RuntimeError(message)
