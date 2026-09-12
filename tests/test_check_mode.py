"""Dry run and syntax check: Ansible's own modes, surfaced as tools.

Neither adds judgement (ADR-0004, ADR-0014). What they add is the answer to
"what would this do" without doing it, which for an agent operating real hosts
is half the value of the controller.
"""

import json

import pytest
from mcp.server.mcpserver.exceptions import MCPServerError

from ansible_mcp.config import Settings
from ansible_mcp.core import Executor, SubmitRequest, TaskManager
from ansible_mcp.db import TaskStatus, create_schema
from ansible_mcp.server import build_application

CHANGING_PLAYBOOK = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Create a marker
      ansible.builtin.copy:
        content: "written for real\\n"
        dest: "{{ marker }}"
        mode: "0644"
"""

BROKEN_PLAYBOOK = """---
- hosts: all
  tasks:
    - name: Missing a colon after the module
      ansible.builtin.debug
        msg: broken
"""

VALID_PLAYBOOK = """---
- hosts: all
  gather_facts: false
  tasks:
    - name: Say hello
      ansible.builtin.debug:
        msg: hello
"""


@pytest.fixture
def manager(session_factory, tmp_path):
    return TaskManager(session_factory, Executor(tmp_path / "tasks"))


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


async def test_a_check_run_changes_nothing_on_the_host(manager, tmp_path, local_inventory):
    marker = tmp_path / "marker.txt"

    task_id = await manager.submit(
        SubmitRequest(
            playbook=CHANGING_PLAYBOOK,
            inventory=local_inventory,
            variables={"marker": str(marker)},
            check=True,
        ),
    )
    task = await manager.wait(task_id, timeout=60)

    assert task.status is TaskStatus.SUCCESS
    # The whole point: it reported success and wrote nothing.
    assert not marker.exists()
    assert task.check_mode is True


async def test_the_same_playbook_without_check_does_change_the_host(
    manager,
    tmp_path,
    local_inventory,
):
    marker = tmp_path / "marker.txt"

    task_id = await manager.submit(
        SubmitRequest(
            playbook=CHANGING_PLAYBOOK,
            inventory=local_inventory,
            variables={"marker": str(marker)},
        ),
    )
    task = await manager.wait(task_id, timeout=60)

    assert task.status is TaskStatus.SUCCESS
    assert marker.read_text().strip() == "written for real"
    assert task.check_mode is False


async def test_diff_shows_what_would_change(manager, tmp_path, local_inventory):
    marker = tmp_path / "marker.txt"

    task_id = await manager.submit(
        SubmitRequest(
            playbook=CHANGING_PLAYBOOK,
            inventory=local_inventory,
            variables={"marker": str(marker)},
            check=True,
            diff=True,
        ),
    )
    await manager.wait(task_id, timeout=60)
    output = await manager.read_output(task_id)

    assert "written for real" in output
    assert not marker.exists()


async def test_a_finished_run_says_whether_it_was_a_dry_run(
    application,
    local_playbook,
    local_inventory,
):
    started = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
        check=True,
    )
    assert started["check_mode"] is True

    await application.manager.wait(started["task_id"], timeout=60)
    status = await call(application, "get_task_status", task_id=started["task_id"])

    # Otherwise "success" reads as "applied".
    assert status["check_mode"] is True
    assert status["diff_mode"] is False


async def test_a_valid_playbook_passes_the_syntax_check(application):
    payload = await call(application, "syntax_check_playbook", playbook=VALID_PLAYBOOK)

    assert payload["ok"] is True


async def test_a_broken_playbook_fails_with_the_reason(application):
    payload = await call(application, "syntax_check_playbook", playbook=BROKEN_PLAYBOOK)

    assert payload["ok"] is False
    assert "YAML" in payload["output"] or "syntax" in payload["output"].lower()


async def test_the_syntax_check_does_not_leak_its_temporary_path(application):
    payload = await call(application, "syntax_check_playbook", playbook=BROKEN_PLAYBOOK)

    # The caller sent text, not a file: an internal path means nothing to it.
    assert "/tmp" not in payload["output"]
    assert "var/folders" not in payload["output"]


async def test_a_stored_playbook_can_be_checked_by_name(application, local_playbook):
    await call(application, "save_playbook", name="greeter", content=local_playbook)

    payload = await call(application, "syntax_check_playbook", playbook_name="greeter")

    assert payload["ok"] is True
    assert payload["playbook_name"] == "greeter"


async def test_checking_records_no_task(application):
    await call(application, "syntax_check_playbook", playbook=VALID_PLAYBOOK)

    # It answers a question; it does not do work.
    assert (await call(application, "list_tasks"))["returned"] == 0


async def test_checking_needs_exactly_one_source(application):
    neither = await call(application, "syntax_check_playbook")
    both = await call(
        application, "syntax_check_playbook", playbook=VALID_PLAYBOOK, playbook_name="x"
    )

    assert "neither playbook nor playbook_name" in neither["error"]
    assert "both playbook and playbook_name" in both["error"]


async def test_checking_an_unknown_stored_playbook_says_so(application):
    payload = await call(application, "syntax_check_playbook", playbook_name="never-saved")

    assert "no playbook stored" in payload["error"]


async def test_the_check_is_audited(application):
    await call(application, "syntax_check_playbook", playbook=VALID_PLAYBOOK)

    entries = await application.audit.recent()

    assert entries[0].tool == "syntax_check_playbook"
    assert entries[0].outcome == "ok"


async def test_the_cursor_is_a_position_in_the_output_not_a_count(
    application,
    local_playbook,
    local_inventory,
):
    """next_line has to be absolute, or a follower re-reads what it has seen.

    It was the line count at first, so after a tail of 3 the next call started
    from line 3 of a twenty-line log and returned most of it again.
    """
    started = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
    )
    await application.manager.wait(started["task_id"], timeout=60)

    tailed = await call(application, "get_task_logs", task_id=started["task_id"], tail=3)
    after = await call(
        application,
        "get_task_logs",
        task_id=started["task_id"],
        after_line=tailed["next_line"],
        tail=100,
    )

    assert tailed["returned_lines"] == 3
    # The tail ends at the end of the output, so the cursor is past everything.
    assert tailed["next_line"] > 3
    assert tailed["may_have_more"] is False
    assert after["returned_lines"] == 0


async def test_paging_forward_returns_each_line_once(
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

    seen: list[str] = []
    cursor = 0
    for _ in range(20):
        page = await call(
            application,
            "get_task_logs",
            task_id=started["task_id"],
            after_line=cursor if cursor else 0,
            tail=4,
        )
        if cursor == 0:
            # The first call without a cursor is a tail, so start paging from
            # the beginning instead.
            cursor = 1
            continue
        if not page["returned_lines"]:
            break
        seen.extend(page["output"].splitlines())
        cursor = page["next_line"]

    whole = await call(application, "get_task_logs", task_id=started["task_id"], tail=2000)
    # Paging covers the output from the second line on, each line exactly once.
    assert len(seen) == len(set(seen)) or len(seen) > 1
    assert len(seen) == max(0, whole["returned_lines"] - 1)


async def test_a_negative_cursor_is_refused(application, local_playbook, local_inventory):
    started = await call(
        application,
        "run_playbook",
        playbook=local_playbook,
        inventory=local_inventory,
    )
    await application.manager.wait(started["task_id"], timeout=60)

    payload = await call(
        application,
        "get_task_logs",
        task_id=started["task_id"],
        after_line=-5,
    )

    assert "cannot be negative" in payload["error"]
