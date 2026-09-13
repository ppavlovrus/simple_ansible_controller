"""Assembling the REST surface.

The routes are built around the services rather than reaching for them through
a global, the same way the tools are, so a test can stand up a second instance
over its own database without touching the first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from ansible_mcp import __version__
from ansible_mcp.api.errors import install_error_handlers
from ansible_mcp.api.routes import playbooks, providers, runs

if TYPE_CHECKING:
    from starlette.types import Lifespan

    from ansible_mcp.operations import Services

API_PREFIX = "/api/v1"

DESCRIPTION = """\
A minimal Ansible controller. Give it a playbook and an inventory and it runs
them, keeping the history, the logs and the artifacts of every run.

This is the human-facing half. The agent-facing half is the MCP endpoint at
/mcp, which is the primary interface (ADR-0002) and holds the same operations
under different names. Both are guarded by the same bearer token.

Runs are asynchronous: POST /api/v1/runs answers immediately with a task id.
"""


def build_api(
    services: Services,
    *,
    lifespan: Lifespan[Any] | None = None,
) -> FastAPI:
    """Return the REST application, ready to be served or mounted into.

    Args:
        services: what the routes act on.
        lifespan: startup and shutdown to run, which is the MCP application's
            own when this app is the one being served: whatever it is mounted
            alongside, only the outermost application is given the lifespan.

    Returns:
        The application, with the routes, the error mapping and the schema.
    """
    app = FastAPI(
        title="ansible-mcp",
        version=__version__,
        description=DESCRIPTION,
        # The interactive pages load their JavaScript from a CDN, and this
        # service is meant to run where there may be no route to one. A schema
        # that is always there beats a page that is sometimes blank.
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    for module in (runs, playbooks, providers):
        app.include_router(module.router(services, API_PREFIX))
    return app
