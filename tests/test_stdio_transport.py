"""The server as a client actually meets it: a real process over stdio.

Everything else tests the tools in-process. This one launches
``python -m ansible_mcp`` and drives it through the protocol, so the entry point,
the transport and the lifespan are covered too.
"""

import asyncio
import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.conftest import FIXTURES

POLL_ATTEMPTS = 40


@pytest.fixture
def server_parameters(tmp_path):
    environment = dict(
        os.environ,
        ANSIBLE_MCP_DATA_DIR=str(tmp_path / "state"),
        ANSIBLE_MCP_LOG_LEVEL="WARNING",
    )
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "ansible_mcp"],
        env=environment,
    )


async def _text(result):
    return "".join(block.text for block in result.content if block.type == "text")


async def _payload(result):
    return json.loads(await _text(result))


async def test_a_client_can_run_a_playbook_end_to_end(server_parameters):
    playbook = (FIXTURES / "local_ping.yml").read_text()
    inventory = (FIXTURES / "local_inventory").read_text()

    async with (
        stdio_client(server_parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        initialization = await session.initialize()
        assert initialization.server_info.name == "ansible-mcp"
        assert initialization.server_info.version

        listed = await session.list_tools()
        assert "run_playbook" in {tool.name for tool in listed.tools}

        started = await _payload(
            await session.call_tool(
                "run_playbook",
                {"playbook": playbook, "inventory": inventory},
            ),
        )
        task_id = started["task_id"]

        for _ in range(POLL_ATTEMPTS):
            status = await _payload(
                await session.call_tool("get_task_status", {"task_id": task_id}),
            )
            if status["status"] not in {"pending", "running"}:
                break
            await asyncio.sleep(1)

        assert status["status"] == "success"
        assert status["exit_code"] == 0

        logs = await _payload(
            await session.call_tool("get_task_logs", {"task_id": task_id, "tail": 20}),
        )
        assert "executor reached testhost" in logs["output"]


async def test_a_refused_call_reaches_the_client_as_an_error(server_parameters):
    async with (
        stdio_client(server_parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        result = await session.call_tool("cancel_task", {"task_id": "whatever"})

        assert result.is_error is True
        assert "not confirmed" in await _text(result)
