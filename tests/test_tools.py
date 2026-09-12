"""The MCP tools as an agent sees them: call them and read the JSON back."""

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.db import TaskStatus, create_schema
from ansible_mcp.server import build_application

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


async def test_every_tool_is_registered(application):
    tools = await application.server.list_tools()

    assert {tool.name for tool in tools} == {
        "run_playbook",
        "get_task_status",
        "get_task_logs",
        "cancel_task",
        "list_tasks",
        "save_playbook",
        "list_playbooks",
        "get_playbook",
        "delete_playbook",
        "add_provider",
        "list_providers",
        "get_inventory",
        "delete_provider",
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


async def test_variables_are_passed_through(application, local_playbook, local_inventory):
    task_id = await run_local(
        application,
        local_playbook,
        local_inventory,
        variables={"greeting": "from-the-tool"},
    )
    await application.manager.wait(task_id, timeout=60)

    logs = await call(application, "get_task_logs", task_id=task_id)

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


# The exposure gate and the token check live in test_http.py, which drives them
# over real requests.


async def test_an_inline_playbook_that_is_not_a_playbook_is_refused(application, local_inventory):
    """Found by review: run_playbook only checked for non-empty.

    save_playbook validated and run_playbook did not, so the same mistake got an
    actionable refusal on one path and an opaque ansible error on the other.
    """
    payload = await call(
        application,
        "run_playbook",
        playbook="just some text, not a playbook",
        inventory=local_inventory,
    )

    assert "list of plays" in payload["error"]
    # Nothing was persisted for it.
    assert (await call(application, "list_tasks"))["returned"] == 0
