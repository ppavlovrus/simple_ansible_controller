"""The MCP tools as an agent sees them: call them and read the JSON back."""

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.db import TaskStatus, create_schema
from ansible_mcp.server import build_application, ensure_safe_to_expose

SLOW_PLAYBOOK = """---
- name: Take a while
  hosts: all
  gather_facts: false
  tasks:
    - name: Sleep
      ansible.builtin.command: sleep 30
      changed_when: false
"""


@pytest.fixture
async def application(tmp_path):
    app = build_application(Settings(data_dir=tmp_path / "state"))
    await create_schema(app.engine)
    yield app
    await app.manager.shutdown()
    await app.engine.dispose()


async def call(app, tool: str, **arguments):
    """Call a tool the way a client does and return its parsed payload.

    The SDK turns a refused or failed call into an exception here and into a
    protocol-level error for the client, so a failure comes back as {"error": ...}.
    """
    try:
        result = await app.server.call_tool(tool, arguments)
    except MCPServerError as error:
        return {"error": str(error)}
    text = "".join(block.text for block in result.content if block.type == "text")
    return json.loads(text)


async def run_local(app, playbook, inventory, **extra):
    payload = await call(app, "run_playbook", playbook=playbook, inventory=inventory, **extra)
    return payload["task_id"]


async def test_the_five_tools_are_registered(application):
    tools = await application.server.list_tools()

    assert {tool.name for tool in tools} == {
        "run_playbook",
        "get_task_status",
        "get_task_logs",
        "cancel_task",
        "list_tasks",
    }


async def test_read_only_tools_are_annotated_as_such(application):
    tools = {tool.name: tool for tool in await application.server.list_tools()}

    assert tools["get_task_status"].annotations.read_only_hint is True
    assert tools["run_playbook"].annotations.read_only_hint is False
    assert tools["cancel_task"].annotations.destructive_hint is True


async def test_tools_describe_themselves_for_an_agent(application):
    tools = {tool.name: tool for tool in await application.server.list_tools()}

    # The description is what an agent reads when choosing a tool, so it has to
    # say more than the function name does.
    for tool in tools.values():
        assert tool.description
        assert len(tool.description.splitlines()) > 1
    assert "task id" in tools["run_playbook"].description


async def test_running_a_playbook_through_to_its_logs(application, local_playbook, local_inventory):
    task_id = await run_local(application, local_playbook, local_inventory)

    task = await application.manager.wait(task_id, timeout=60)
    assert task.status is TaskStatus.SUCCESS

    status = await call(application, "get_task_status", task_id=task_id)
    assert status["status"] == "success"
    assert status["exit_code"] == 0

    logs = await call(application, "get_task_logs", task_id=task_id)
    assert "executor reached testhost" in logs["output"]
    assert logs["returned_lines"] > 0


async def test_variables_and_name_are_passed_through(application, local_playbook, local_inventory):
    task_id = await run_local(
        application,
        local_playbook,
        local_inventory,
        variables={"greeting": "from-the-tool"},
        playbook_name="greeter",
    )
    await application.manager.wait(task_id, timeout=60)

    status = await call(application, "get_task_status", task_id=task_id)
    logs = await call(application, "get_task_logs", task_id=task_id)

    assert status["playbook_name"] == "greeter"
    assert "greeting=from-the-tool" in logs["output"]


async def test_an_empty_playbook_is_refused(application, local_inventory):
    payload = await call(application, "run_playbook", playbook="  ", inventory=local_inventory)

    assert "playbook is empty" in payload["error"]


async def test_asking_about_an_unknown_task_says_so(application):
    payload = await call(application, "get_task_status", task_id="nope")

    assert "no task with id" in payload["error"]


async def test_cancelling_requires_confirmation(application, local_inventory):
    task_id = await run_local(application, SLOW_PLAYBOOK, local_inventory)
    await asyncio.sleep(2)

    refused = await call(application, "cancel_task", task_id=task_id)
    assert "not confirmed" in refused["error"]
    assert (await application.manager.get(task_id)).status is TaskStatus.RUNNING

    accepted = await call(application, "cancel_task", task_id=task_id, confirm=True)
    assert accepted["cancelled"] is True

    task = await application.manager.wait(task_id, timeout=40)
    assert task.status is TaskStatus.CANCELLED


async def test_cancelling_a_finished_task_reports_it(application, local_playbook, local_inventory):
    task_id = await run_local(application, local_playbook, local_inventory)
    await application.manager.wait(task_id, timeout=60)

    payload = await call(application, "cancel_task", task_id=task_id, confirm=True)

    assert payload["cancelled"] is False
    assert payload["status"] == "success"
    assert "already reached a final status" in payload["note"]


async def test_listing_tasks_and_filtering_by_status(application, local_playbook, local_inventory):
    for _ in range(2):
        task_id = await run_local(application, local_playbook, local_inventory)
        await application.manager.wait(task_id, timeout=60)

    everything = await call(application, "list_tasks")
    successes = await call(application, "list_tasks", status="success")

    assert everything["returned"] == 2
    assert successes["returned"] == 2
    assert everything["has_more"] is False
    assert all(task["status"] == "success" for task in successes["tasks"])


async def test_listing_rejects_an_unknown_status(application):
    payload = await call(application, "list_tasks", status="finished")

    assert "unknown status" in payload["error"]
    assert "success" in payload["error"]


async def test_limits_are_capped(application):
    listed = await call(application, "list_tasks", limit=500)
    logs = await call(application, "get_task_logs", task_id="whatever", tail=99999)

    assert "capped at 100" in listed["error"]
    assert "capped at 2000" in logs["error"]


async def test_responses_carry_only_the_fields_an_agent_needs(
    application,
    local_playbook,
    local_inventory,
):
    task_id = await run_local(application, local_playbook, local_inventory)
    await application.manager.wait(task_id, timeout=60)

    status = await call(application, "get_task_status", task_id=task_id)

    # The snapshots are deliberately absent: they are what fills a context window.
    assert "playbook_snapshot" not in status
    assert "inventory_snapshot" not in status
    assert set(status) == {
        "task_id",
        "status",
        "playbook_name",
        "provider_name",
        "created_at",
        "started_at",
        "finished_at",
        "exit_code",
        "error_message",
    }


@pytest.mark.parametrize(
    "settings",
    [
        Settings(transport="streamable-http", host="0.0.0.0", api_key=None),
        # An API key buys nothing while nothing verifies it: a configuration that
        # looks authenticated but is not would be worse than an obviously open one.
        Settings(transport="streamable-http", host="0.0.0.0", api_key="secret"),
        Settings(transport="streamable-http", host="192.168.1.10", api_key="secret"),
    ],
)
def test_serving_http_beyond_loopback_is_refused(settings):
    with pytest.raises(RuntimeError, match="restricted to loopback"):
        ensure_safe_to_expose(settings)


@pytest.mark.parametrize(
    "settings",
    [
        Settings(transport="stdio", host="0.0.0.0", api_key=None),
        Settings(transport="streamable-http", host="127.0.0.1", api_key=None),
        Settings(transport="streamable-http", host="localhost", api_key=None),
    ],
)
def test_safe_configurations_are_allowed(settings):
    ensure_safe_to_expose(settings)
