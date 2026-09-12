"""The store keeps tasks, playbooks and provider configuration."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from ansible_mcp.db import Playbook, ProviderConfig, Task, TaskStatus


async def test_sqlite_runs_in_wal_mode(engine):
    async with engine.connect() as connection:
        mode = await connection.scalar(text("PRAGMA journal_mode"))

    assert mode == "wal"


async def test_task_defaults_are_filled_in(session_factory):
    async with session_factory() as session:
        task = Task(playbook_snapshot="- hosts: all", inventory_snapshot="[all]")
        session.add(task)
        await session.commit()

        assert len(task.id) == 32
        assert task.status is TaskStatus.PENDING
        assert task.variables == {}
        assert task.tags == []
        assert task.execution_environment is None
        assert task.created_at.tzinfo is not None
        assert task.started_at is None


async def test_snapshots_survive_a_later_edit_of_the_playbook(session_factory):
    async with session_factory() as session:
        session.add(Playbook(name="deploy", content="- hosts: all  # v1"))
        await session.commit()

        task = Task(
            playbook_name="deploy",
            playbook_snapshot="- hosts: all  # v1",
            inventory_snapshot="[all]\nweb1",
        )
        session.add(task)
        await session.commit()

        stored = await session.get(Playbook, "deploy")
        stored.content = "- hosts: all  # v2"
        await session.commit()
        await session.refresh(task)

        assert task.playbook_snapshot == "- hosts: all  # v1"


async def test_json_columns_round_trip(session_factory):
    async with session_factory() as session:
        task = Task(
            playbook_snapshot="- hosts: all",
            inventory_snapshot="[all]",
            variables={"env": "staging", "replicas": 3},
            tags=["deploy", "smoke"],
        )
        session.add(task)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(Task, task.id)

        assert stored.variables == {"env": "staging", "replicas": 3}
        assert stored.tags == ["deploy", "smoke"]


async def test_tasks_can_be_filtered_by_status(session_factory):
    async with session_factory() as session:
        session.add_all(
            [
                Task(
                    playbook_snapshot="a",
                    inventory_snapshot="[all]",
                    status=TaskStatus.RUNNING,
                ),
                Task(
                    playbook_snapshot="b",
                    inventory_snapshot="[all]",
                    status=TaskStatus.SUCCESS,
                    finished_at=datetime.now(UTC),
                ),
            ],
        )
        await session.commit()

        running = (
            await session.scalars(select(Task).where(Task.status == TaskStatus.RUNNING))
        ).all()

        assert len(running) == 1
        assert running[0].playbook_snapshot == "a"


async def test_playbook_name_is_unique(session_factory):
    async with session_factory() as session:
        session.add(Playbook(name="deploy", content="one"))
        await session.commit()

    async with session_factory() as session:
        session.add(Playbook(name="deploy", content="another"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_provider_config_holds_variable_names_not_secrets(session_factory):
    async with session_factory() as session:
        session.add(
            ProviderConfig(
                name="yc-prod",
                plugin_type="yandex_cloud",
                config={"token_env": "YC_TOKEN", "folder_id": "b1gxxx"},
            ),
        )
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(ProviderConfig, "yc-prod")

        assert stored.config["token_env"] == "YC_TOKEN"
        assert "token" not in stored.config


async def test_timestamps_come_back_timezone_aware(session_factory):
    async with session_factory() as session:
        task = Task(playbook_snapshot="a", inventory_snapshot="[all]")
        session.add(task)
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(Task, task.id)

        assert stored.created_at.tzinfo is not None
        # The failure this guards against is a TypeError here, not a wrong value.
        assert datetime.now(UTC) - stored.created_at >= timedelta(0)


async def test_naive_timestamps_are_refused(session_factory):
    async with session_factory() as session:
        session.add(
            Task(
                playbook_snapshot="a",
                inventory_snapshot="[all]",
                started_at=datetime(2026, 9, 12, 12, 0),
            ),
        )
        # SQLAlchemy wraps the ValueError raised while binding the parameter.
        with pytest.raises(StatementError, match="naive datetime"):
            await session.commit()


async def test_status_is_stored_as_its_value(session_factory):
    async with session_factory() as session:
        session.add(
            Task(
                playbook_snapshot="a",
                inventory_snapshot="[all]",
                status=TaskStatus.RUNNING,
            ),
        )
        await session.commit()

        # Hand-written SQL during an incident should match what the API returns.
        stored = await session.scalar(text("SELECT status FROM tasks"))

        assert stored == "running"


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (TaskStatus.PENDING, False),
        (TaskStatus.RUNNING, False),
        (TaskStatus.SUCCESS, True),
        (TaskStatus.FAILED, True),
        (TaskStatus.CANCELLED, True),
    ],
)
def test_terminal_statuses(status, terminal):
    assert status.is_terminal is terminal
