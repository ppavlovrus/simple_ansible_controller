"""Serving over HTTP: who may call, and how to tell the service is alive.

The MCP endpoint executes playbooks on real hosts, so reaching it has to be
proof of authorization rather than proof of network access. A static bearer token
is a modest mechanism, but it is checked on every request, in constant time, and
its absence stops the server from starting at all (ADR-0012).

The health endpoint deliberately sits outside the check: a readiness probe
should not need a credential, and it reveals nothing beyond counts.
"""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any

import uvicorn
from sqlalchemy import func, select

from ansible_mcp import __version__
from ansible_mcp.core.audit import AuditEntry
from ansible_mcp.db import Task, TaskStatus

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from ansible_mcp.config import Settings
    from ansible_mcp.server.app import Application

HEALTH_PATH = "/healthz"
BEARER_PREFIX = "bearer "


class BearerTokenMiddleware:
    """Requires a bearer token on every request except the health probe.

    Pure ASGI rather than Starlette's BaseHTTPMiddleware: the MCP transport
    streams responses, and a middleware that bridges streams can race a client
    disconnect on a long-lived call.
    """

    def __init__(self, app: ASGIApp, api_key: str, *, unprotected: tuple[str, ...] = ()) -> None:
        """Wrap ``app``, letting ``unprotected`` paths through unchecked."""
        self._app = app
        self._api_key = api_key
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
        """Whether the request carries the expected token."""
        # Take the first Authorization header: a dict would keep only the last of
        # duplicates, which is a way to smuggle a second value past a check.
        raw = next(
            (value for (name, value) in scope.get("headers") or [] if name == b"authorization"),
            b"",
        )
        header = raw.decode("latin-1")
        if not header.lower().startswith(BEARER_PREFIX):
            return False
        token = header[len(BEARER_PREFIX) :].strip()
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
    """Return the ASGI application to serve, health probe and auth included.

    Raises:
        RuntimeError: if no API key is configured; serving unauthenticated is
            refused rather than warned about (ADR-0012).
    """
    from starlette.responses import JSONResponse

    @application.server.custom_route(HEALTH_PATH, methods=["GET"])
    async def healthz(_request: Any) -> JSONResponse:
        """Report liveness and a few counts, without requiring a token."""
        return JSONResponse(await health(application))

    app: ASGIApp = application.server.streamable_http_app(host=settings.host)

    if settings.api_key is None:
        message = (
            "refusing to serve HTTP without ANSIBLE_MCP_API_KEY: anyone able to reach "
            "the port could run playbooks on your hosts"
        )
        raise RuntimeError(message)

    return BearerTokenMiddleware(app, settings.api_key, unprotected=(HEALTH_PATH,))


def serve_http(application: Application, settings: Settings) -> None:
    """Serve the MCP endpoint over HTTP until interrupted."""
    uvicorn.run(
        build_http_app(application, settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
