"""Serving over HTTP: the token is checked, the health probe is not."""

import httpx
import pytest

from ansible_mcp.config import Settings
from ansible_mcp.db import create_schema
from ansible_mcp.server import build_application, ensure_safe_to_expose
from ansible_mcp.server.http import (
    HEALTH_PATH,
    BearerTokenMiddleware,
    build_http_app,
    health,
)


@pytest.fixture
async def served(tmp_path):
    """An application with its HTTP app, reachable without a real socket."""
    settings = Settings(
        data_dir=tmp_path / "state",
        transport="streamable-http",
        host="0.0.0.0",
        api_key="correct-horse-battery-staple",
    )
    application = build_application(settings)
    await create_schema(application.engine)
    app = build_http_app(application, settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield application, client, settings
    await application.manager.shutdown()
    await application.engine.dispose()


async def test_the_health_probe_needs_no_token(served):
    _application, client, _settings = served

    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["tasks"]["success"] == 0


async def test_the_mcp_endpoint_refuses_a_request_without_a_token(served):
    _application, client, _settings = served

    response = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})

    assert response.status_code == 401
    assert "bearer token is required" in response.text
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    [
        "wrong-scheme correct-horse-battery-staple",
        "Bearer wrong-token",
        "Bearer ",
        "Bearer correct-horse-battery-stapl",  # one character short
        "",
    ],
)
async def test_a_wrong_token_is_refused(served, header):
    _application, client, _settings = served

    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "ping", "id": 1},
        headers={"Authorization": header} if header else {},
    )

    assert response.status_code == 401


async def test_the_right_token_is_passed_through_to_the_application():
    """The wrapped application is a stand-in.

    Driving the real MCP transport here would need its session manager running,
    which is the SDK's business; what needs proving is that our middleware calls
    through on a correct token and answers by itself otherwise.
    """
    reached = []

    async def application(scope, receive, send):
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    guarded = BearerTokenMiddleware(application, "correct-token", unprotected=(HEALTH_PATH,))
    transport = httpx.ASGITransport(app=guarded)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        accepted = await client.post("/mcp", headers={"Authorization": "Bearer correct-token"})
        refused = await client.post("/mcp", headers={"Authorization": "Bearer wrong"})

    assert accepted.status_code == 204
    assert refused.status_code == 401
    assert reached == ["/mcp"]


async def test_a_second_authorization_header_cannot_smuggle_a_token():
    """Only the first Authorization header counts.

    Keeping the last of duplicates, which dict(headers) would do, lets a proxy's
    header be overridden by an attacker-supplied one further down the list.
    """

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    guarded = BearerTokenMiddleware(application, "correct-token")
    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [
            (b"authorization", b"Bearer wrong"),
            (b"authorization", b"Bearer correct-token"),
        ],
    }
    statuses = []

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await guarded(scope, receive, send)

    assert statuses == [401]


async def test_serving_without_a_key_is_refused(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "state",
        transport="streamable-http",
        host="0.0.0.0",
        api_key=None,
    )
    application = build_application(settings)

    with pytest.raises(RuntimeError, match="requires ANSIBLE_MCP_API_KEY"):
        ensure_safe_to_expose(settings)
    with pytest.raises(RuntimeError, match="without ANSIBLE_MCP_API_KEY"):
        build_http_app(application, settings)

    await application.engine.dispose()


async def test_a_loopback_bind_needs_no_key(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "state",
        transport="streamable-http",
        host="127.0.0.1",
        api_key=None,
    )

    # Reaching loopback already means being on the machine.
    ensure_safe_to_expose(settings)


async def test_health_counts_what_has_happened(served, local_playbook, local_inventory):
    application, client, _settings = served
    from ansible_mcp.core import SubmitRequest

    task_id = await application.manager.submit(
        SubmitRequest(playbook=local_playbook, inventory=local_inventory),
    )
    await application.manager.wait(task_id, timeout=60)

    reported = await health(application)
    over_http = (await client.get(HEALTH_PATH)).json()

    assert reported["tasks"]["success"] == 1
    assert over_http["tasks"]["success"] == 1
