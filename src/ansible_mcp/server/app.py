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
from ansible_mcp.core import Executor, PlaybookStore, TaskManager
from ansible_mcp.core.audit import AuditLog
from ansible_mcp.db import create_engine, create_schema, create_session_factory
from ansible_mcp.providers import ProviderRegistry, Providers
from ansible_mcp.server.tools import Services, register_all

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
get_task_status and get_task_logs follow it.

Playbooks can be stored by name and inventories can come from configured
providers, so a repeated run does not carry its text every time.

Nothing here writes playbooks or decides what to run: this controller executes,
the calling agent decides.
"""


@dataclass
class Application:
    """A server and the objects it owns."""

    server: MCPServer
    manager: TaskManager
    engine: AsyncEngine
    playbooks: PlaybookStore
    providers: Providers
    audit: AuditLog


def build_application(settings: Settings) -> Application:
    """Construct the server, its task manager and its store.

    Args:
        settings: configuration to build from.

    Returns:
        The application, ready to be run. Nothing has touched the disk yet.
    """
    engine = create_engine(settings.database_path)
    session_factory = create_session_factory(engine)
    manager = TaskManager(
        session_factory,
        Executor(settings.tasks_dir),
        max_concurrent_tasks=settings.max_concurrent_tasks,
        run_timeout_seconds=settings.run_timeout_seconds,
    )
    playbooks = PlaybookStore(session_factory)
    audit = AuditLog(session_factory)
    providers = Providers(
        session_factory,
        ProviderRegistry(settings.allowed_inventory_dirs),
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
    register_all(
        server,
        Services(manager=manager, playbooks=playbooks, providers=providers, audit=audit),
    )
    return Application(
        server=server,
        manager=manager,
        engine=engine,
        playbooks=playbooks,
        providers=providers,
        audit=audit,
    )


def ensure_safe_to_expose(settings: Settings) -> None:
    """Refuse to serve HTTP without a token to check callers against.

    Anyone who reaches this endpoint can execute arbitrary playbooks on the hosts
    it can see, so an unauthenticated endpoint is not a configuration choice, it
    is an incident. The refusal happens at startup rather than in a log nobody
    reads until afterwards (ADR-0007, ADR-0012).

    A loopback bind is allowed without a key: reaching it already requires being
    on the machine, where the stdio transport would serve the same purpose.

    Raises:
        RuntimeError: if the configuration would expose an unauthenticated
            endpoint.
    """
    if settings.transport == "stdio" or settings.host in LOOPBACK_ADDRESSES:
        return
    if settings.api_key is not None:
        return
    message = (
        f"refusing to listen on {settings.host}: serving beyond loopback requires "
        f"ANSIBLE_MCP_API_KEY, which every request is then checked against"
    )
    raise RuntimeError(message)
