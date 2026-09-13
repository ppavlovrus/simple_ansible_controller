"""Wiring the pieces together into a server that can be run.

Construction is synchronous so the tools can close over a task manager that
exists before the server starts. Everything that needs the event loop, including
the schema and the recovery of tasks interrupted by a restart, happens in the
lifespan.
"""

from __future__ import annotations

import logging
import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer

from ansible_mcp import __version__
from ansible_mcp.core import Executor, Isolation, PlaybookStore, TaskManager
from ansible_mcp.core.audit import AuditLog
from ansible_mcp.db import create_engine, create_schema, create_session_factory
from ansible_mcp.operations import Services
from ansible_mcp.providers import ProviderRegistry, Providers
from ansible_mcp.server.tools import register_all

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
    # The same services the tools were registered against: the REST surface is
    # built on them too, and both have to act on one set of objects or a run
    # started through one door would be invisible through the other.
    services: Services


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
        Executor(settings.tasks_dir, isolation=_isolation(settings)),
        max_concurrent_tasks=settings.max_concurrent_tasks,
        run_timeout_seconds=settings.run_timeout_seconds,
        keep_artifacts_days=settings.keep_artifacts_days,
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
        pruned = await manager.prune_artifacts()
        log.info(
            "started; %d interrupted task(s) failed, %d run(s) pruned",
            interrupted,
            pruned,
        )
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
    services = Services(manager=manager, playbooks=playbooks, providers=providers, audit=audit)
    register_all(server, services)
    return Application(
        server=server,
        manager=manager,
        engine=engine,
        playbooks=playbooks,
        providers=providers,
        audit=audit,
        services=services,
    )


def _isolation(settings: Settings) -> Isolation | None:
    """Return where playbooks run, or ``None`` when they run on this host.

    ``ensure_isolation_is_usable`` has already refused the configurations this
    cannot express, so an enabled mode here always has an image.
    """
    if not settings.isolation or settings.execution_image is None:
        return None
    return Isolation(runtime=settings.container_runtime, image=settings.execution_image)


def ensure_isolation_is_usable(settings: Settings) -> None:
    """Refuse an isolation mode that cannot actually isolate anything.

    An operator who turned this on did so to stop playbooks running on this
    host. Discovering at the first run -- from inside a failed playbook -- that
    there is no runtime or no image is not an acceptable way to learn that it
    never happened (ADR-0016).

    Raises:
        RuntimeError: if isolation is on without an image or without the runtime
            that would launch it.
    """
    if not settings.isolation:
        return

    if settings.execution_image is None:
        message = (
            "ANSIBLE_MCP_ISOLATION is on but ANSIBLE_MCP_EXECUTION_IMAGE is not set: "
            "name an image that is already present on this host and carries "
            "ansible-playbook on its PATH"
        )
        raise RuntimeError(message)

    if shutil.which(settings.container_runtime) is None:
        message = (
            f"ANSIBLE_MCP_ISOLATION is on but {settings.container_runtime} was not found "
            f"on PATH: install it, or set ANSIBLE_MCP_ISOLATION=false to run playbooks "
            f"on this host instead"
        )
        raise RuntimeError(message)

    if _inside_a_container():
        # Not refused: reaching a runtime from in here means its socket was
        # mounted deliberately, and that is the operator's call to have made.
        # It is said out loud because the sandbox it buys is worth less than it
        # looks -- that socket is root on the host (ADR-0008).
        log.warning(
            "isolation is on inside a container: launching containers from here needs the "
            "runtime socket, which is root on the host and undoes most of what isolation buys",
        )


def _inside_a_container() -> bool:
    """Whether this process looks like it is itself in a container."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


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
