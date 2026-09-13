"""Serving over HTTP: who may call, what is served where, and whether it is alive.

One port carries both surfaces: the MCP endpoint at /mcp for agents, and the
REST API under /api/v1 for people and scripts (ADR-0015). Either can execute
playbooks on real hosts, so reaching the port has to be proof of authorization
rather than proof of network access. A static bearer token is a modest
mechanism, but it is checked on every request, in constant time, and its absence
stops the server from starting at all (ADR-0012).

The health endpoint deliberately sits outside the check: a readiness probe
should not need a credential, and it reveals nothing beyond counts.
"""

from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import uvicorn
from sqlalchemy import func, select

from ansible_mcp import __version__
from ansible_mcp.api import build_api
from ansible_mcp.core.audit import AuditEntry
from ansible_mcp.db import Task, TaskStatus
from ansible_mcp.server.app import LOOPBACK_ADDRESSES

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Receive, Scope, Send

    from ansible_mcp.config import Settings
    from ansible_mcp.server.app import Application

log = logging.getLogger("ansible_mcp.http")

HEALTH_PATH = "/healthz"
BEARER_PREFIX = b"bearer "


class BearerTokenMiddleware:
    """Requires a bearer token on every request except the health probe.

    Pure ASGI rather than Starlette's BaseHTTPMiddleware: the MCP transport
    streams responses, and a middleware that bridges streams can race a client
    disconnect on a long-lived call.
    """

    def __init__(self, app: ASGIApp, api_key: str, *, unprotected: tuple[str, ...] = ()) -> None:
        """Wrap ``app``, letting ``unprotected`` paths through unchecked."""
        self._app = app
        # Kept as bytes: the comparison below happens on the raw header, because
        # compare_digest refuses str arguments holding non-ASCII characters and a
        # header can hold any byte.
        self._api_key = api_key.encode()
        self._unprotected = unprotected

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check the token, or answer 401 without touching the application."""
        if scope["type"] != "http" or scope.get("path", "") in self._unprotected:
            await self._app(scope, receive, send)
            return

        if not self._authorized(scope):
            await _unauthorized(send)
            return

        await self._app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        """Whether the request carries the expected token.

        Everything happens on bytes. Decoding the header first and comparing
        strings made any request with a high byte in it raise out of the
        middleware, which uvicorn answers with 500 and a traceback: an
        anonymous caller could fill the operator's log at will.
        """
        # Take the first Authorization header: a dict would keep only the last of
        # duplicates, which is a way to smuggle a second value past a check.
        raw = next(
            (value for (name, value) in scope.get("headers") or [] if name == b"authorization"),
            b"",
        )
        if raw[: len(BEARER_PREFIX)].lower() != BEARER_PREFIX:
            return False
        token = raw[len(BEARER_PREFIX) :].strip()
        return bool(token) and secrets.compare_digest(token, self._api_key)


async def _unauthorized(send: Send) -> None:
    """Answer 401 with a body that says what is missing."""
    body = json.dumps({"error": "a bearer token is required"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ],
        },
    )
    await send({"type": "http.response.body", "body": body})


async def health(application: Application) -> dict[str, Any]:
    """Return what an operator needs to know at a glance.

    Counts come from the database rather than from in-process counters, so a
    restart does not reset them and the answer is true for the whole instance.
    """
    async with application.engine.connect() as connection:
        counted = await connection.execute(select(Task.status, func.count()).group_by(Task.status))
        # .tuples() keeps the row types, so this stays a typed dict rather than Any.
        by_status = dict(counted.tuples().all())
        failed_calls = await connection.scalar(
            select(func.count()).select_from(AuditEntry).where(AuditEntry.outcome == "failed"),
        )

    return {
        "status": "ok",
        "version": __version__,
        "tasks": {member.value: int(by_status.get(member, 0)) for member in TaskStatus},
        "failed_calls": int(failed_calls or 0),
    }


def build_http_app(application: Application, settings: Settings) -> ASGIApp:
    """Return the ASGI application to serve: both surfaces, health probe and auth.

    A loopback bind without a key is served unguarded, which is what ADR-0012
    permits: reaching it already requires being on the machine. Any other address
    requires the key, and is refused without one rather than warned about.

    Raises:
        RuntimeError: if the endpoint would be reachable off the machine with
            nothing to check callers against.
    """
    from starlette.responses import JSONResponse

    @application.server.custom_route(HEALTH_PATH, methods=["GET"])
    async def healthz(_request: Any) -> JSONResponse:
        """Report liveness and a few counts, without requiring a token."""
        return JSONResponse(await health(application))

    mcp_app = application.server.streamable_http_app(host=settings.host)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        """Run the MCP application's startup and shutdown.

        It owns everything that matters at startup -- the schema, the recovery
        of runs a restart interrupted, the session manager -- and a mounted
        application is never sent a lifespan of its own, so the outer one has to
        run it or none of that happens.
        """
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    api = build_api(application.services, lifespan=lifespan)
    # Everything the REST routes do not claim falls through to MCP, which is
    # what keeps /mcp and /healthz at the paths they have always been at.
    api.mount("/", mcp_app)
    app: ASGIApp = api

    if settings.api_key is None:
        if settings.host not in LOOPBACK_ADDRESSES:
            message = (
                "refusing to serve HTTP on "
                f"{settings.host} without ANSIBLE_MCP_API_KEY: anyone able to reach the port "
                "could run playbooks on your hosts"
            )
            raise RuntimeError(message)
        log.warning(
            "serving %s unguarded: no ANSIBLE_MCP_API_KEY is set, so every local process can "
            "run playbooks through this endpoint",
            settings.host,
        )
        return app

    return BearerTokenMiddleware(app, settings.api_key, unprotected=(HEALTH_PATH,))


def serve_http(application: Application, settings: Settings) -> None:
    """Serve both HTTP surfaces until interrupted."""
    uvicorn.run(
        build_http_app(application, settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
