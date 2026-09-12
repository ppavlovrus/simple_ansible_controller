"""Running a playbook and collecting what came out of it.

``ansible-runner`` does the actual work. It is a blocking library that shells out
to ``ansible-playbook``, so every call is pushed onto a worker thread and the
event loop stays free (ADR-0003).

Each run gets its own directory under the data dir, holding the playbook and the
inventory it ran with and the artifacts it produced. That directory is the whole
record of the run on disk; the database keeps the metadata.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import ansible_runner

from ansible_mcp.db import TaskStatus

if TYPE_CHECKING:
    from pathlib import Path

# ansible-runner reports its own vocabulary; map it onto ours. Anything absent
# from this table is treated as a failure, which is the safe direction.
_RUNNER_STATUS_TO_TASK_STATUS = {
    "successful": TaskStatus.SUCCESS,
    "failed": TaskStatus.FAILED,
    "timeout": TaskStatus.FAILED,
    "canceled": TaskStatus.CANCELLED,
}

_PLAYBOOK_FILENAME = "playbook.yml"
_INVENTORY_FILENAME = "hosts"


class Cancellation:
    """A cooperative cancel signal for a run that is already in flight.

    ``ansible-runner`` polls a callback while the playbook runs and stops when it
    returns true, so cancelling is a request rather than a kill: the current task
    finishes first.
    """

    def __init__(self) -> None:
        """Create a signal that has not been raised yet."""
        self._event = threading.Event()

    def cancel(self) -> None:
        """Ask the run to stop at the next opportunity."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._event.is_set()


@dataclass(frozen=True)
class RunRequest:
    """Everything needed to execute one playbook.

    The playbook and the inventory are passed as text, not as paths: by the time
    a run starts they are already snapshotted (ADR-0005), and the executor writes
    them into the run directory itself.
    """

    task_id: str
    playbook: str
    inventory: str
    variables: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunResult:
    """What a finished run produced.

    Attributes:
        status: terminal status of the run.
        exit_code: exit code of ``ansible-playbook``, when it got as far as
            running.
        error_message: why the run failed, for failures with no exit code.
        run_dir: directory holding the inputs and the artifacts of this run.
    """

    status: TaskStatus
    exit_code: int | None
    error_message: str | None
    run_dir: Path


class Executor:
    """Runs playbooks, one directory per run."""

    def __init__(self, tasks_dir: Path) -> None:
        """Create an executor storing run directories under ``tasks_dir``."""
        self._tasks_dir = tasks_dir

    def run_dir(self, task_id: str) -> Path:
        """Return the directory holding one run's inputs and artifacts."""
        return self._tasks_dir / task_id

    def stdout_path(self, task_id: str) -> Path:
        """Return the file ``ansible-playbook`` wrote its output to."""
        return self.run_dir(task_id) / "artifacts" / task_id / "stdout"

    def read_output(self, task_id: str, tail: int | None = None) -> str:
        """Return the run's output, optionally only its last lines.

        A playbook over a large inventory writes tens of megabytes, so the tail
        is read backwards from the end of the file rather than by loading the
        whole thing and slicing it.

        Args:
            task_id: run to read.
            tail: how many trailing lines to return. ``None`` returns everything.

        Returns:
            The output collected so far, or an empty string if the run has not
            produced any yet.
        """
        path = self.stdout_path(task_id)
        if not path.exists():
            return ""
        if tail is None:
            return path.read_text(errors="replace")
        return _read_last_lines(path, tail)

    def prepare(self, request: RunRequest) -> Path:
        """Lay out the run directory that ``ansible-runner`` expects.

        Args:
            request: the run to prepare.

        Returns:
            The private data directory for this run.
        """
        run_dir = self.run_dir(request.task_id)
        project = run_dir / "project"
        inventory = run_dir / "inventory"
        project.mkdir(parents=True, exist_ok=True)
        inventory.mkdir(parents=True, exist_ok=True)

        (project / _PLAYBOOK_FILENAME).write_text(request.playbook)
        (inventory / _INVENTORY_FILENAME).write_text(request.inventory)
        return run_dir

    async def run(
        self,
        request: RunRequest,
        cancellation: Cancellation | None = None,
    ) -> RunResult:
        """Execute a playbook and wait for it to reach a terminal state.

        The blocking runner call happens on a worker thread, so this coroutine
        yields for the whole duration of the playbook.

        Args:
            request: what to run.
            cancellation: signal that asks the run to stop early.

        Returns:
            The terminal status, the exit code and where the artifacts landed.
        """
        run_dir = self.prepare(request)
        return await asyncio.to_thread(self._run_blocking, request, run_dir, cancellation)

    def cleanup(self, task_id: str) -> None:
        """Delete a run's directory, artifacts included."""
        shutil.rmtree(self.run_dir(task_id), ignore_errors=True)

    @staticmethod
    def _drop_run_inputs(run_dir: Path) -> None:
        """Remove what the run was fed, keeping what it produced.

        Three files carry secrets and none of them need to survive the run. The
        variables file ansible-runner writes (``env/extravars``) holds them in
        the clear; the inventory can carry ``ansible_password``; and both the
        playbook and the inventory are already stored with the task (ADR-0005),
        so the copies here are duplicates that outlive their usefulness.

        The artifacts stay: stdout is the only record of what actually happened.
        """
        (run_dir / "env" / "extravars").unlink(missing_ok=True)
        shutil.rmtree(run_dir / "project", ignore_errors=True)
        shutil.rmtree(run_dir / "inventory", ignore_errors=True)

    def _run_blocking(
        self,
        request: RunRequest,
        run_dir: Path,
        cancellation: Cancellation | None,
    ) -> RunResult:
        """Call ansible-runner on the current thread and translate its result."""
        should_cancel = (lambda: cancellation.is_cancelled) if cancellation else None

        try:
            runner = ansible_runner.run(
                private_data_dir=str(run_dir),
                playbook=_PLAYBOOK_FILENAME,
                inventory=str(run_dir / "inventory" / _INVENTORY_FILENAME),
                extravars=dict(request.variables),
                tags=",".join(request.tags) if request.tags else None,
                ident=request.task_id,
                cancel_callback=should_cancel,
                quiet=True,
                # Halves what a successful run leaves on disk and keeps the
                # structured event data for the runs where it is worth reading.
                # stdout, which is what get_task_logs returns, is unaffected.
                only_failed_event_data=True,
            )
        # A broken playbook, an unreadable inventory or a missing binary all
        # surface here. The caller gets a readable message, never a traceback.
        except Exception as error:
            return RunResult(
                status=TaskStatus.FAILED,
                exit_code=None,
                error_message=f"{type(error).__name__}: {error}",
                run_dir=run_dir,
            )

        finally:
            self._drop_run_inputs(run_dir)

        status = _RUNNER_STATUS_TO_TASK_STATUS.get(runner.status, TaskStatus.FAILED)
        return RunResult(
            status=status,
            exit_code=runner.rc,
            error_message=None if status is TaskStatus.SUCCESS else _describe(runner),
            run_dir=run_dir,
        )


def _describe(runner: Any) -> str:
    """Summarize a non-successful run in one line."""
    return f"ansible-runner reported status={runner.status} rc={runner.rc}"


def _read_last_lines(path: Path, lines: int, block_size: int = 8192) -> str:
    """Read the last ``lines`` lines of a file without loading all of it."""
    if lines <= 0:
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        chunks: list[bytes] = []
        newlines = 0
        while position > 0 and newlines <= lines:
            step = min(block_size, position)
            position -= step
            handle.seek(position)
            chunk = handle.read(step)
            newlines += chunk.count(b"\n")
            chunks.insert(0, chunk)
    data = b"".join(chunks)
    return b"".join(data.splitlines(keepends=True)[-lines:]).decode(errors="replace")
