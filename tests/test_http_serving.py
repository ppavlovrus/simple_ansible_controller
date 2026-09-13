"""Both surfaces on one port, from a real process.

Everything else drives the application through an ASGI transport, which never
sends a lifespan. The MCP endpoint's session manager and this controller's own
startup -- the schema, the recovery of interrupted runs -- happen there, and
since the REST surface became the outer application it is the one responsible
for running it. That arrangement can only be wrong at startup, so this test
starts the thing.
"""

import asyncio
import json
import os
import socket
import sys

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from tests.conftest import FIXTURES

TOKEN = "correct-horse-battery-staple"
STARTUP_ATTEMPTS = 100
POLL_ATTEMPTS = 60


@pytest.fixture(autouse=True)
def _ignore_any_proxy(monkeypatch):
    """Talk to 127.0.0.1 directly, whatever this machine routes through.

    A developer box may send everything through a SOCKS proxy; httpx then
    refuses the request outright unless its socks extra is installed, and the
    failure looks nothing like "your server is broken".
    """
    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
async def server(tmp_path):
    """A real `python -m ansible_mcp` serving HTTP, gone when the test ends."""
    port = _free_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ansible_mcp",
        env=dict(
            os.environ,
            ANSIBLE_MCP_DATA_DIR=str(tmp_path / "state"),
            ANSIBLE_MCP_TRANSPORT="streamable-http",
            ANSIBLE_MCP_HOST="127.0.0.1",
            ANSIBLE_MCP_PORT=str(port),
            ANSIBLE_MCP_API_KEY=TOKEN,
            ANSIBLE_MCP_LOG_LEVEL="WARNING",
        ),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        await _wait_until_serving(base, process)
        yield base
    finally:
        process.terminate()
        await process.wait()


async def _wait_until_serving(base, process):
    async with httpx.AsyncClient() as client:
        for _ in range(STARTUP_ATTEMPTS):
            if process.returncode is not None:
                pytest.fail(f"the server exited with {process.returncode} before serving")
            try:
                if (await client.get(f"{base}/healthz", timeout=1)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    pytest.fail("the server never answered its health probe")


@pytest.fixture
def rest(server):
    return httpx.AsyncClient(
        base_url=f"{server}/api/v1",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=10,
    )


async def test_a_script_can_run_a_playbook_over_rest_end_to_end(rest):
    async with rest as client:
        created = await client.post(
            "/runs",
            json={
                "playbook": (FIXTURES / "local_ping.yml").read_text(),
                "inventory": (FIXTURES / "local_inventory").read_text(),
            },
        )
        assert created.status_code == 202
        task_id = created.json()["task_id"]

        for _ in range(POLL_ATTEMPTS):
            run = (await client.get(f"/runs/{task_id}")).json()
            if run["status"] in {"success", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.5)

        assert run["status"] == "success"
        logs = (await client.get(f"/runs/{task_id}/logs")).json()
        assert "executor reached testhost" in logs["output"]


async def test_an_agent_and_a_script_reach_the_same_controller(server, rest):
    # The point of serving both on one port: what one door does, the other sees.
    async with rest as client:
        created = await client.post(
            "/runs",
            json={
                "playbook": (FIXTURES / "local_ping.yml").read_text(),
                "inventory": (FIXTURES / "local_inventory").read_text(),
            },
        )
    task_id = created.json()["task_id"]

    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {TOKEN}"})
    async with (
        streamable_http_client(f"{server}/mcp", http_client=http_client) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("get_task_status", {"task_id": task_id})

    payload = json.loads("".join(b.text for b in result.content if b.type == "text"))
    assert payload["task_id"] == task_id


async def test_the_schema_says_where_the_routes_are(rest):
    async with rest as client:
        schema = (await client.get("/openapi.json")).json()

    assert "/api/v1/runs" in schema["paths"]
