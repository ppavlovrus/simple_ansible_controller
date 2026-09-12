"""Every call is recorded, including the ones that were refused."""

import json

import pytest
from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.core.audit import AuditLog, Outcome, describe_arguments
from ansible_mcp.db import create_schema
from ansible_mcp.server import build_application


@pytest.fixture
def audit(session_factory):
    return AuditLog(session_factory)


@pytest.fixture
async def application(tmp_path):
    app = build_application(Settings(data_dir=tmp_path / "state"))
    await create_schema(app.engine)
    yield app
    await app.manager.shutdown()
    await app.engine.dispose()


async def call(app, tool, **arguments):
    try:
        result = await app.server.call_tool(tool, arguments)
    except MCPServerError as error:
        return {"error": str(error)}
    return json.loads("".join(b.text for b in result.content if b.type == "text"))


def test_long_arguments_are_recorded_by_size_not_content():
    described = describe_arguments({"playbook": "- hosts: all\n" * 40, "provider": "lab"})

    assert "hosts: all" not in described
    assert "chars" in described
    assert "provider='lab'" in described


def test_secret_arguments_are_not_recorded():
    described = describe_arguments({"password": "hunter2", "user": "postgres"})

    assert "hunter2" not in described
    assert "[redacted]" in described
    assert "postgres" in described


def test_dictionaries_are_recorded_by_their_keys():
    described = describe_arguments({"variables": {"db_password": "hunter2", "env": "prod"}})

    # The names are useful for reading the log; the values are not worth the risk.
    assert "hunter2" not in described
    assert "db_password" in described
    assert "env" in described


def test_absent_arguments_are_left_out():
    assert describe_arguments({"task_id": "abc", "tail": None}) == "task_id='abc'"


async def test_a_successful_call_is_recorded(audit):
    await audit.record("list_tasks", {"limit": 5}, Outcome.OK, duration_ms=12)

    entries = await audit.recent()

    assert len(entries) == 1
    assert entries[0].tool == "list_tasks"
    assert entries[0].outcome == "ok"
    assert entries[0].arguments == "limit=5"
    assert entries[0].duration_ms == 12


async def test_entries_come_back_newest_first_and_limited(audit):
    for index in range(5):
        await audit.record("list_tasks", {"limit": index}, Outcome.OK)

    entries = await audit.recent(limit=2)

    assert len(entries) == 2
    assert entries[0].arguments == "limit=4"


async def test_a_broken_audit_log_does_not_fail_the_call(audit, monkeypatch):
    def explode():
        message = "the database is gone"
        raise RuntimeError(message)

    monkeypatch.setattr(audit, "_session_factory", explode)

    # No exception: the run already happened, and claiming otherwise is worse
    # than losing the record.
    await audit.record("run_playbook", {}, Outcome.OK)


async def test_running_a_playbook_is_audited(application, local_playbook, local_inventory):
    started = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
        variables={"db_password": "hunter2"},
    )
    await application.manager.wait(started["task_id"], timeout=60)

    entries = await application.audit.recent()

    assert entries[0].tool == "run_playbook"
    assert entries[0].outcome == "ok"
    assert entries[0].duration_ms is not None
    assert "hunter2" not in entries[0].arguments
    # The playbook text is not copied into the log; the task already has it.
    assert "chars" in entries[0].arguments


async def test_an_entry_links_to_the_task_the_call_produced(
    application,
    local_playbook,
    local_inventory,
):
    started = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
    )
    await application.manager.wait(started["task_id"], timeout=60)
    await call(application, "get_task_status", task_id=started["task_id"])

    entries = await application.audit.recent()

    # Both the call that started the run and the call that asked about it point
    # at the same run, which is what makes the log usable after an incident.
    assert entries[0].tool == "get_task_status"
    assert entries[0].task_id == started["task_id"]
    assert entries[1].tool == "run_playbook"
    assert entries[1].task_id == started["task_id"]


async def test_an_entry_without_a_task_has_none(application):
    await call(application, "list_providers")

    entries = await application.audit.recent()

    assert entries[0].task_id is None


async def test_a_refused_call_is_audited_with_the_reason(application):
    await call(application, "cancel_task", task_id="whatever")

    entries = await application.audit.recent()

    assert entries[0].tool == "cancel_task"
    assert entries[0].outcome == "refused"
    assert "not confirmed" in entries[0].detail


async def test_a_failed_lookup_is_audited_as_refused(application):
    await call(application, "get_task_status", task_id="nope")

    entries = await application.audit.recent()

    assert entries[0].outcome == "refused"
    assert "no task with id" in entries[0].detail


async def test_read_only_calls_are_audited_too(application):
    await call(application, "list_tasks")
    await call(application, "list_providers")

    entries = await application.audit.recent()

    assert [entry.tool for entry in entries] == ["list_providers", "list_tasks"]


async def test_an_unexpected_failure_is_audited_as_failed(application, monkeypatch):
    async def explode(*_args, **_kwargs):
        message = "disk on fire"
        raise RuntimeError(message)

    monkeypatch.setattr(application.manager, "list", explode)

    payload = await call(application, "list_tasks")

    entries = await application.audit.recent()
    assert "list_tasks failed" in payload["error"]
    assert entries[0].outcome == "failed"
    assert "disk on fire" in entries[0].detail
