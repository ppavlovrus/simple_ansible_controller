"""The lifecycle of a run: accept it, execute it, record how it ended.

A submitted task is persisted immediately and executed in the background, so the
caller gets an identifier straight away and polls for the outcome (ADR-0007).

Concurrency is bounded by a semaphore rather than by a worker pool: this is one
process on one node (ADR-0003), and a task waiting for a slot simply stays
``PENDING``.

Two guarantees need explicit work. A run that outlives the timeout is cancelled
rather than left hanging, because ansible-runner has no timeout of its own. And
a task left ``RUNNING`` by a crashed process is failed on the next startup, since
nothing is left to resume it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, update

from ansible_mcp.core.executor import Cancellation, RunRequest
from ansible_mcp.core.redaction import redact, secret_values
from ansible_mcp.db import Task, TaskStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ansible_mcp.core.executor import Executor, RunResult, SyntaxCheckResult

log = logging.getLogger("ansible_mcp.task_manager")


@dataclass(frozen=True)
class SubmitRequest:
    """A request to run a playbook.

    The playbook and the inventory arrive as text and are stored with the task,
    so the run stays reproducible afterwards (ADR-0005).
    """

    playbook: str
    inventory: str
    playbook_name: str | None = None
    provider_name: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    check: bool = False
    diff: bool = False


class TaskManager:
    """Owns running tasks and the record of finished ones."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        executor: Executor,
        *,
        max_concurrent_tasks: int = 4,
        run_timeout_seconds: float | None = None,
        keep_artifacts_days: int | None = None,
    ) -> None:
        """Create a manager.

        Args:
            session_factory: opens sessions against the store.
            executor: runs the playbooks.
            max_concurrent_tasks: how many runs may execute at once.
            run_timeout_seconds: how long a single run may take before it is
                cancelled. ``None`` means no limit.
            keep_artifacts_days: how long a finished run's artifacts are kept.
                ``None`` keeps them forever.
        """
        self._session_factory = session_factory
        self._executor = executor
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._run_timeout = run_timeout_seconds
        self._keep_artifacts_days = keep_artifacts_days
        self._running: dict[str, _InFlight] = {}

    async def recover_interrupted(self) -> int:
        """Fail tasks left active by a process that died.

        Nothing resumes a run across a restart: the ansible-playbook process is
        gone with its parent. Leaving the rows as ``RUNNING`` would make the
        service lie about what it is doing.

        Tasks this process is currently running are excluded. Calling this while
        the service is live would otherwise mark healthy runs as failed and leave
        the database contradicting reality.

        Returns:
            How many tasks were failed.
        """
        async with self._session_factory() as session:
            # execute() is typed as returning a plain Result; an UPDATE always
            # gives back a CursorResult, which is the one that counts rows.
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(Task)
                    .where(Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]))
                    .where(Task.id.not_in(list(self._running)))
                    .values(
                        status=TaskStatus.FAILED,
                        finished_at=datetime.now(UTC),
                        error_message=(
                            "interrupted: the service restarted while this task was active"
                        ),
                    ),
                ),
            )
            await session.commit()
            recovered = int(result.rowcount or 0)

        if recovered:
            log.warning("failed %d task(s) interrupted by a restart", recovered)
        return recovered

    async def prune_artifacts(self) -> int:
        """Delete the artifacts of runs older than the retention window.

        The task rows are left alone: they are the history, they are small, and
        they hold the snapshots that make a run reproducible. What goes is the
        bulk on disk, which for a successful run is mostly per-event files and
        is of no interest once nobody is looking at it any more.

        Returns:
            How many runs had their artifacts deleted.
        """
        if self._keep_artifacts_days is None:
            return 0

        cutoff = datetime.now(UTC) - timedelta(days=self._keep_artifacts_days)
        async with self._session_factory() as session:
            stale = list(
                await session.scalars(
                    select(Task)
                    .where(Task.finished_at.is_not(None))
                    .where(Task.finished_at < cutoff)
                    .where(Task.artifacts_dir.is_not(None)),
                ),
            )
            for task in stale:
                await asyncio.to_thread(self._executor.cleanup, task.id)
                # Cleared so the row stops promising artifacts that are gone.
                task.artifacts_dir = None
            await session.commit()

        if stale:
            log.info(
                "deleted the artifacts of %d run(s) finished before %s",
                len(stale),
                cutoff.date(),
            )
        return len(stale)

    async def submit(self, request: SubmitRequest) -> str:
        """Accept a run, persist it and start it in the background.

        Args:
            request: what to run.

        Returns:
            The identifier of the created task.
        """
        async with self._session_factory() as session:
            task = Task(
                playbook_name=request.playbook_name,
                playbook_snapshot=request.playbook,
                inventory_snapshot=request.inventory,
                provider_name=request.provider_name,
                variables=dict(request.variables),
                tags=list(request.tags),
                check_mode=request.check,
                diff_mode=request.diff,
            )
            session.add(task)
            await session.commit()
            task_id = task.id

        cancellation = Cancellation()
        background = asyncio.create_task(self._execute(task_id, request, cancellation))
        self._running[task_id] = _InFlight(background=background, cancellation=cancellation)
        background.add_done_callback(lambda _: self._running.pop(task_id, None))
        return task_id

    async def get(self, task_id: str) -> Task | None:
        """Return one task, or ``None`` if there is no such task."""
        async with self._session_factory() as session:
            return await session.get(Task, task_id)

    async def list(self, *, status: TaskStatus | None = None, limit: int = 20) -> list[Task]:
        """Return the most recent tasks, newest first.

        Args:
            status: keep only tasks in this status.
            limit: how many to return.
        """
        query = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if status is not None:
            query = query.where(Task.status == status)
        async with self._session_factory() as session:
            return list(await session.scalars(query))

    async def count_output_lines(self, task_id: str) -> int:
        """Return how many lines of output the run has produced so far."""
        return await asyncio.to_thread(self._executor.count_lines, task_id)

    async def syntax_check(self, playbook: str) -> SyntaxCheckResult:
        """Parse a playbook without running or recording anything."""
        return await asyncio.to_thread(self._executor.syntax_check, playbook)

    async def read_output(self, task_id: str, tail: int | None = None) -> str:
        """Return what the run has written so far, with secrets removed.

        The read happens on a worker thread: Ansible output reaches tens of
        megabytes, and reading that on the event loop would stall every other
        call while one agent fetches logs.

        Redaction uses the run's own variables, so a password this run was given
        is removed from the output even when the playbook echoed it without
        ``no_log``.
        """
        task = await self.get(task_id)
        secrets = secret_values(dict(task.variables)) if task else ()
        output = await asyncio.to_thread(self._executor.read_output, task_id, tail)
        return redact(output, secrets)

    async def cancel(self, task_id: str) -> bool:
        """Ask a task to stop.

        A task that has not started yet is cancelled outright; a running one is
        asked to stop and reaches ``CANCELLED`` once the current Ansible task
        finishes.

        Args:
            task_id: task to stop.

        Returns:
            Whether a task was actually asked to stop. ``False`` means it had
            already finished or never existed.
        """
        in_flight = self._running.get(task_id)
        if in_flight is None:
            return False

        in_flight.cancellation.cancel()
        if not in_flight.started:
            # Cancelling the coroutine is not enough to record the outcome: if
            # the cancel lands before the coroutine's first step, it never
            # enters its own try block, so the status is written here instead of
            # relying on a handler that may not run.
            in_flight.background.cancel()
            await self._finish(
                task_id,
                TaskStatus.CANCELLED,
                None,
                "cancelled while waiting for a slot",
            )
        return True

    async def wait(self, task_id: str, timeout: float | None = None) -> Task | None:
        """Wait for a task to finish and return it.

        A timeout is not an error here: waiting is how a caller polls, and the
        task as it stands is a useful answer. The run continues.

        Args:
            task_id: task to wait for.
            timeout: how long to wait. ``None`` waits indefinitely.

        Returns:
            The task: finished if it finished within the timeout, as it stands
            otherwise, or ``None`` if there is no such task.
        """
        in_flight = self._running.get(task_id)
        if in_flight is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(in_flight.background), timeout)
        return await self.get(task_id)

    async def shutdown(self) -> None:
        """Ask every running task to stop and wait for them to wind down."""
        in_flight = list(self._running.values())
        for entry in in_flight:
            entry.cancellation.cancel()
        for entry in in_flight:
            with contextlib.suppress(asyncio.CancelledError):
                await entry.background

    async def _execute(
        self,
        task_id: str,
        request: SubmitRequest,
        cancellation: Cancellation,
    ) -> None:
        """Run one task from waiting for a slot to writing down the outcome.

        Every path out of here writes a terminal status. An exception escaping
        this coroutine would leave the row saying ``RUNNING`` forever, and a
        polling agent would keep waiting for a run that is no longer happening.
        """
        try:
            async with self._semaphore:
                # A slot can free up long after the cancel arrived.
                if cancellation.is_cancelled:
                    await self._finish(
                        task_id, TaskStatus.CANCELLED, None, "cancelled before it started"
                    )
                    return

                in_flight = self._running.get(task_id)
                if in_flight is not None:
                    in_flight.started = True

                await self._mark_running(task_id)
                result = await self._run(task_id, request, cancellation)

            await self._finish(
                task_id,
                result.status,
                result.exit_code,
                result.error_message,
                artifacts_dir=str(result.run_dir),
                secrets=secret_values(dict(request.variables)),
            )
        except asyncio.CancelledError:
            # Reached on shutdown, or when a queued task is cancelled after it
            # has started running. cancel() has already recorded the queued
            # case, and writing the same terminal status twice is harmless.
            await self._finish(task_id, TaskStatus.CANCELLED, None, "the service stopped this task")
            raise
        except Exception as error:
            log.exception("task %s failed unexpectedly", task_id)
            await self._finish(
                task_id,
                TaskStatus.FAILED,
                None,
                f"internal error: {type(error).__name__}: {error}",
                secrets=secret_values(dict(request.variables)),
            )

    async def _run(
        self,
        task_id: str,
        request: SubmitRequest,
        cancellation: Cancellation,
    ) -> RunResult:
        """Execute the playbook, enforcing the timeout if one is configured."""
        run_request = RunRequest(
            task_id=task_id,
            playbook=request.playbook,
            inventory=request.inventory,
            variables=request.variables,
            tags=request.tags,
            check=request.check,
            diff=request.diff,
        )
        run = asyncio.create_task(self._executor.run(run_request, cancellation))

        if self._run_timeout is None:
            return await run

        try:
            # Shielded: the timeout must not abandon the thread running Ansible.
            return await asyncio.wait_for(asyncio.shield(run), self._run_timeout)
        except TimeoutError:
            log.warning("task %s exceeded %.0fs, cancelling it", task_id, self._run_timeout)
            cancellation.cancel()
            result = await run
            return _as_timed_out(result, self._run_timeout)

    async def _mark_running(self, task_id: str) -> None:
        """Move a task into ``RUNNING`` and stamp when it started."""
        async with self._session_factory() as session:
            await session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(status=TaskStatus.RUNNING, started_at=datetime.now(UTC)),
            )
            await session.commit()

    async def _finish(
        self,
        task_id: str,
        status: TaskStatus,
        exit_code: int | None,
        error_message: str | None,
        artifacts_dir: str | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """Write down how a task ended.

        The message is redacted with the run's own secret values as well as the
        generic patterns. In practice the message is a one-line summary from
        ansible-runner, but the path that reports an exception can carry anything
        the library put in it, and a value with no secret-looking name beside it
        is exactly what the patterns cannot catch.
        """
        values: dict[str, Any] = {
            "status": status,
            "finished_at": datetime.now(UTC),
            "exit_code": exit_code,
            # A failure message can quote the command that failed, password and all.
            "error_message": redact(error_message, secrets) if error_message else None,
        }
        if artifacts_dir is not None:
            values["artifacts_dir"] = artifacts_dir

        async with self._session_factory() as session:
            await session.execute(update(Task).where(Task.id == task_id).values(**values))
            await session.commit()


@dataclass
class _InFlight:
    """A task currently owned by this process."""

    background: asyncio.Task[None]
    cancellation: Cancellation
    # False while the task is still waiting for a slot. A queued task is parked
    # inside the semaphore, where no flag can reach it, so cancelling one means
    # cancelling the coroutine; a running one is asked to stop cooperatively,
    # because killing it would abandon a live ansible-playbook process.
    started: bool = False


def _as_timed_out(result: RunResult, timeout: float) -> RunResult:
    """Relabel a cancelled-by-timeout run as a failure, since it did not finish."""
    return replace(
        result,
        status=TaskStatus.FAILED,
        error_message=f"timed out after {timeout:.0f}s and was cancelled",
    )
