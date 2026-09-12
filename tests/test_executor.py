"""The executor runs real playbooks.

These tests start an actual ansible-playbook process against the control node
itself, so they need neither SSH nor a container, but they do prove the wiring
end to end.
"""

import asyncio

import pytest

from ansible_mcp.core import Cancellation, Executor, RunRequest
from ansible_mcp.db import TaskStatus

FAILING_PLAYBOOK = """---
- name: Fail on purpose
  hosts: all
  gather_facts: false
  tasks:
    - name: Stop with an error
      ansible.builtin.fail:
        msg: "this run is meant to fail"
"""

SLOW_PLAYBOOK = """---
- name: Take a while
  hosts: all
  gather_facts: false
  tasks:
    - name: Sleep
      ansible.builtin.command: sleep 30
      changed_when: false
"""

TAGGED_PLAYBOOK = """---
- name: Tagged tasks
  hosts: all
  gather_facts: false
  tasks:
    - name: Wanted
      ansible.builtin.debug:
        msg: "ran the wanted task"
      tags: [wanted]
    - name: Unwanted
      ansible.builtin.debug:
        msg: "ran the unwanted task"
      tags: [unwanted]
"""


@pytest.fixture
def executor(tmp_path):
    return Executor(tmp_path / "tasks")


async def test_successful_run(executor, local_playbook, local_inventory):
    result = await executor.run(
        RunRequest(task_id="t1", playbook=local_playbook, inventory=local_inventory),
    )

    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    assert result.error_message is None
    assert "executor reached testhost" in executor.read_output("t1")


async def test_run_directory_holds_the_inputs_it_ran_with(
    executor,
    local_playbook,
    local_inventory,
):
    await executor.run(
        RunRequest(task_id="t2", playbook=local_playbook, inventory=local_inventory),
    )

    run_dir = executor.run_dir("t2")
    assert (run_dir / "project" / "playbook.yml").read_text() == local_playbook
    assert (run_dir / "inventory" / "hosts").read_text() == local_inventory
    assert executor.stdout_path("t2").exists()


async def test_variables_reach_the_playbook(executor, local_playbook, local_inventory):
    await executor.run(
        RunRequest(
            task_id="t3",
            playbook=local_playbook,
            inventory=local_inventory,
            variables={"greeting": "hello-from-the-test"},
        ),
    )

    assert "greeting=hello-from-the-test" in executor.read_output("t3")


async def test_tags_limit_what_runs(executor, local_inventory):
    await executor.run(
        RunRequest(
            task_id="t4",
            playbook=TAGGED_PLAYBOOK,
            inventory=local_inventory,
            tags=["wanted"],
        ),
    )

    output = executor.read_output("t4")
    assert "ran the wanted task" in output
    assert "ran the unwanted task" not in output


async def test_failing_playbook_is_reported_as_failed(executor, local_inventory):
    result = await executor.run(
        RunRequest(task_id="t5", playbook=FAILING_PLAYBOOK, inventory=local_inventory),
    )

    assert result.status is TaskStatus.FAILED
    assert result.exit_code != 0
    assert "status=failed" in result.error_message


async def test_broken_playbook_is_reported_as_failed(executor, local_inventory):
    result = await executor.run(
        RunRequest(
            task_id="t6",
            playbook="this: is: not: a playbook",
            inventory=local_inventory,
        ),
    )

    assert result.status is TaskStatus.FAILED
    assert result.error_message


async def test_cancellation_stops_a_running_playbook(executor, local_inventory):
    cancellation = Cancellation()
    run = asyncio.create_task(
        executor.run(
            RunRequest(task_id="t7", playbook=SLOW_PLAYBOOK, inventory=local_inventory),
            cancellation,
        ),
    )

    await asyncio.sleep(2)
    cancellation.cancel()
    result = await asyncio.wait_for(run, timeout=25)

    assert result.status is TaskStatus.CANCELLED


async def test_variables_do_not_stay_on_disk(executor, local_playbook, local_inventory):
    await executor.run(
        RunRequest(
            task_id="t10",
            playbook=local_playbook,
            inventory=local_inventory,
            variables={"db_password": "hunter2"},
        ),
    )

    leaked = [
        str(path.relative_to(executor.run_dir("t10")))
        for path in executor.run_dir("t10").rglob("*")
        if path.is_file() and "hunter2" in path.read_text(errors="ignore")
    ]

    assert leaked == []


async def test_reading_output_of_an_unknown_run_is_empty(executor):
    assert executor.read_output("never-ran") == ""


async def test_output_can_be_tailed(executor, local_playbook, local_inventory):
    await executor.run(
        RunRequest(task_id="t8", playbook=local_playbook, inventory=local_inventory),
    )

    tail = executor.read_output("t8", tail=3)

    assert tail
    assert len(tail.splitlines()) <= 3
    assert len(tail) < len(executor.read_output("t8"))


async def test_cleanup_removes_the_run_directory(executor, local_playbook, local_inventory):
    await executor.run(
        RunRequest(task_id="t9", playbook=local_playbook, inventory=local_inventory),
    )
    assert executor.run_dir("t9").exists()

    executor.cleanup("t9")

    assert not executor.run_dir("t9").exists()
