"""The task manager owns the lifecycle of a run."""

import asyncio
from datetime import UTC, datetime

import pytest

from ansible_mcp.core import Executor, SubmitRequest, TaskManager
from ansible_mcp.db import Task, TaskStatus

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


@pytest.fixture
def executor(tmp_path):
    return Executor(tmp_path / "tasks")


@pytest.fixture
def manager(session_factory, executor):
    return TaskManager(session_factory, executor)


@pytest.fixture
def request_of(local_playbook, local_inventory):
    def build(playbook: str | None = None, **kwargs) -> SubmitRequest:
        return SubmitRequest(
            playbook=playbook if playbook is not None else local_playbook,
            inventory=local_inventory,
            **kwargs,
        )

    return build


async def test_a_submitted_task_runs_and_is_recorded(manager, request_of):
    task_id = await manager.submit(request_of(playbook_name="hello"))

    task = await manager.wait(task_id, timeout=60)

    assert task.status is TaskStatus.SUCCESS
    assert task.exit_code == 0
    assert task.playbook_name == "hello"
    assert task.started_at is not None
    assert task.finished_at >= task.started_at
    assert task.artifacts_dir
    assert "executor reached testhost" in manager.read_output(task_id)


async def test_the_run_is_snapshotted_on_submission(manager, request_of, local_playbook):
    task_id = await manager.submit(request_of(variables={"greeting": "hi"}, tags=["one"]))

    task = await manager.wait(task_id, timeout=60)

    assert task.playbook_snapshot == local_playbook
    assert task.variables == {"greeting": "hi"}
    assert task.tags == ["one"]


async def test_a_failing_playbook_is_recorded_as_failed(manager, request_of):
    task_id = await manager.submit(request_of(FAILING_PLAYBOOK))

    task = await manager.wait(task_id, timeout=60)

    assert task.status is TaskStatus.FAILED
    assert task.exit_code != 0
    assert task.error_message


async def test_cancelling_a_running_task(manager, request_of):
    task_id = await manager.submit(request_of(SLOW_PLAYBOOK))
    await asyncio.sleep(2)

    assert await manager.cancel(task_id) is True
    task = await manager.wait(task_id, timeout=40)

    assert task.status is TaskStatus.CANCELLED


async def test_cancelling_a_queued_task_never_starts_it(session_factory, executor, request_of):
    manager = TaskManager(session_factory, executor, max_concurrent_tasks=1)
    first = await manager.submit(request_of(SLOW_PLAYBOOK))
    queued = await manager.submit(request_of())

    assert await manager.cancel(queued) is True
    await manager.cancel(first)
    await manager.wait(first, timeout=40)
    task = await manager.wait(queued, timeout=40)

    assert task.status is TaskStatus.CANCELLED
    assert task.started_at is None
    assert not executor.run_dir(queued).exists()


async def test_cancelling_an_unknown_task_reports_nothing_to_do(manager):
    assert await manager.cancel("no-such-task") is False


async def test_concurrency_is_bounded(session_factory, executor, request_of):
    manager = TaskManager(session_factory, executor, max_concurrent_tasks=1)

    first = await manager.submit(request_of(SLOW_PLAYBOOK))
    second = await manager.submit(request_of())
    await asyncio.sleep(2)

    queued = await manager.get(second)
    assert queued.status is TaskStatus.PENDING

    await manager.cancel(first)
    await manager.wait(first, timeout=40)
    finished = await manager.wait(second, timeout=60)
    assert finished.status is TaskStatus.SUCCESS


async def test_a_run_that_overruns_its_timeout_fails(session_factory, executor, request_of):
    manager = TaskManager(session_factory, executor, run_timeout_seconds=3)

    task_id = await manager.submit(request_of(SLOW_PLAYBOOK))
    task = await manager.wait(task_id, timeout=60)

    assert task.status is TaskStatus.FAILED
    assert "timed out" in task.error_message


async def test_interrupted_tasks_are_failed_on_startup(session_factory, manager):
    async with session_factory() as session:
        session.add_all(
            [
                Task(
                    playbook_snapshot="a",
                    inventory_snapshot="[all]",
                    status=TaskStatus.RUNNING,
                    started_at=datetime.now(UTC),
                ),
                Task(playbook_snapshot="b", inventory_snapshot="[all]", status=TaskStatus.PENDING),
                Task(
                    playbook_snapshot="c",
                    inventory_snapshot="[all]",
                    status=TaskStatus.SUCCESS,
                    finished_at=datetime.now(UTC),
                ),
            ],
        )
        await session.commit()

    recovered = await manager.recover_interrupted()

    assert recovered == 2
    failed = await manager.list(status=TaskStatus.FAILED)
    assert len(failed) == 2
    assert all("interrupted" in task.error_message for task in failed)
    assert len(await manager.list(status=TaskStatus.SUCCESS)) == 1


async def test_recovery_leaves_this_process_own_tasks_alone(manager, request_of):
    running = await manager.submit(request_of(SLOW_PLAYBOOK))
    await asyncio.sleep(2)

    recovered = await manager.recover_interrupted()

    assert recovered == 0
    assert (await manager.get(running)).status is TaskStatus.RUNNING
    await manager.shutdown()


async def test_an_unexpected_failure_still_reaches_a_terminal_status(
    session_factory,
    executor,
    request_of,
):
    async def explode(*_args, **_kwargs):
        message = "disk on fire"
        raise RuntimeError(message)

    executor.run = explode
    manager = TaskManager(session_factory, executor)

    task_id = await manager.submit(request_of())
    task = await manager.wait(task_id, timeout=30)

    assert task.status is TaskStatus.FAILED
    assert "disk on fire" in task.error_message


async def test_listing_returns_newest_first_and_respects_the_limit(manager, request_of):
    ids = [await manager.submit(request_of()) for _ in range(3)]
    for task_id in ids:
        await manager.wait(task_id, timeout=60)

    listed = await manager.list(limit=2)

    assert len(listed) == 2
    assert listed[0].created_at >= listed[1].created_at


async def test_getting_an_unknown_task_returns_nothing(manager):
    assert await manager.get("no-such-task") is None


async def test_shutdown_stops_running_tasks(manager, request_of):
    task_id = await manager.submit(request_of(SLOW_PLAYBOOK))
    await asyncio.sleep(2)

    await manager.shutdown()

    task = await manager.get(task_id)
    assert task.status is TaskStatus.CANCELLED
