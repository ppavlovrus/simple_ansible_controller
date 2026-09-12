"""Tools for running playbooks and following the runs.

Two rules shape every response. It is JSON with the fields an agent needs to
decide what to do next, not a dump of the row; and anything unbounded (task
lists, log output) is capped, because filling the agent's context is a failure
mode of its own (ADR-0002).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.core import SubmitRequest
from ansible_mcp.db import Task, TaskStatus
from ansible_mcp.providers import ProviderError
from ansible_mcp.server.errors import UsageError, confirmed, found, require, tool_errors
from ansible_mcp.server.tools._shared import (
    DEFAULT_LOG_LINES,
    EXECUTE,
    MAX_LOG_LINES_PER_CALL,
    MAX_TASKS_PER_CALL,
    READ,
    STOP,
    Services,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def _summarize(task: Task) -> dict[str, Any]:
    """Return the fields of a task an agent actually decides on."""
    return {
        "task_id": task.id,
        "status": task.status.value,
        "playbook_name": task.playbook_name,
        "provider_name": task.provider_name,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "exit_code": task.exit_code,
        "error_message": task.error_message,
    }


def register(server: MCPServer, services: Services) -> None:
    """Register the task tools."""

    @server.tool(annotations=EXECUTE)
    @tool_errors
    async def run_playbook(
        playbook: str | None = None,
        playbook_name: str | None = None,
        inventory: str | None = None,
        provider: str | None = None,
        variables: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Run an Ansible playbook against an inventory and return immediately.

        Say what to run, either inline with `playbook` or by naming one already
        stored with `playbook_name`. Say where to run it, either inline with
        `inventory` or by naming a configured provider with `provider`, which
        resolves the inventory when the run starts.

        The run happens in the background: this returns a task id, and the run is
        followed with get_task_status and get_task_logs. Both the playbook and the
        resolved inventory are stored with the task exactly as used, so the run
        can be examined later even if either changes.

        Args:
            playbook: the playbook itself, as YAML text.
            playbook_name: name of a stored playbook to run instead.
            inventory: the inventory to run against, in INI or YAML format.
            provider: name of a configured provider to take the inventory from.
            variables: extra variables, the equivalent of --extra-vars.
            tags: run only tasks carrying these tags.

        Returns:
            A JSON object with task_id and the initial status. The run is not
            finished when this returns.
        """
        require(
            bool(playbook) != bool(playbook_name),
            "pass exactly one of playbook (the YAML) or playbook_name (a stored playbook)",
        )
        require(
            bool(inventory) != bool(provider),
            "pass exactly one of inventory (the text) or provider (a configured provider)",
        )

        if playbook_name:
            stored = found(
                await services.playbooks.get(playbook_name),
                f"no playbook stored as {playbook_name!r}; list_playbooks shows what there is",
            )
            content = stored.content
        else:
            content = playbook or ""
            require(bool(content.strip()), "playbook is empty: pass the playbook YAML as text")

        if provider:
            try:
                resolved = await services.providers.inventory(provider)
            except ProviderError as error:
                raise UsageError(str(error)) from error
        else:
            resolved = inventory or ""
            require(bool(resolved.strip()), "inventory is empty: pass an INI or YAML inventory")

        task_id = await services.manager.submit(
            SubmitRequest(
                playbook=content,
                inventory=resolved,
                playbook_name=playbook_name,
                provider_name=provider,
                variables=variables or {},
                tags=tags or [],
            ),
        )
        return json.dumps(
            {
                "task_id": task_id,
                "status": TaskStatus.PENDING.value,
                "hint": "poll get_task_status; read output with get_task_logs",
            },
        )

    @server.tool(annotations=READ)
    @tool_errors
    async def get_task_status(task_id: str) -> str:
        """Report how a run is doing, or how it ended.

        Status is one of pending, running, success, failed or cancelled. The first
        two mean the run is still in progress and worth polling again; the other
        three are final.

        Args:
            task_id: identifier returned by run_playbook.

        Returns:
            A JSON object with the status, timestamps, exit code and, for
            failures, the error message.
        """
        task = found(await services.manager.get(task_id), f"no task with id {task_id!r}")
        return json.dumps(_summarize(task))

    @server.tool(annotations=READ)
    @tool_errors
    async def get_task_logs(task_id: str, tail: int = DEFAULT_LOG_LINES) -> str:
        """Read what a run printed, most recent lines last.

        Ansible output is long: only the last lines are returned unless more are
        asked for. Read the tail first and widen it if the reason for a failure is
        not visible.

        Args:
            task_id: identifier returned by run_playbook.
            tail: how many trailing lines to return (at most 2000).

        Returns:
            A JSON object with the requested lines and how many were returned.
        """
        require(tail > 0, "tail must be at least 1")
        require(
            tail <= MAX_LOG_LINES_PER_CALL,
            f"tail is capped at {MAX_LOG_LINES_PER_CALL} lines per call",
        )
        found(await services.manager.get(task_id), f"no task with id {task_id!r}")

        output = await services.manager.read_output(task_id, tail)
        lines = output.splitlines()
        return json.dumps(
            {
                "task_id": task_id,
                "returned_lines": len(lines),
                "may_have_more": len(lines) >= tail,
                "output": output,
            },
        )

    @server.tool(annotations=STOP)
    @tool_errors
    async def cancel_task(task_id: str, confirm: bool = False) -> str:
        """Stop a run that is queued or in progress.

        Cancelling mid-run leaves the hosts in whatever state the playbook reached:
        the tasks already applied are not rolled back. That is why this needs
        explicit confirmation.

        Args:
            task_id: identifier returned by run_playbook.
            confirm: must be true for the cancellation to happen.

        Returns:
            A JSON object saying whether the run was asked to stop. A run that had
            already finished reports cancelled=false with its final status.
        """
        confirmed(confirm, f"cancelling task {task_id}")

        task = found(await services.manager.get(task_id), f"no task with id {task_id!r}")
        cancelled = await services.manager.cancel(task_id)
        return json.dumps(
            {
                "task_id": task_id,
                "cancelled": cancelled,
                "status": task.status.value,
                "note": None if cancelled else "the task had already reached a final status",
            },
        )

    @server.tool(annotations=READ)
    @tool_errors
    async def list_tasks(status: str | None = None, limit: int = 20) -> str:
        """List recent runs, newest first.

        Use this to find a task id that was not kept, or to see what has been
        running lately. Filter by status to answer questions like "is anything
        still running".

        Args:
            status: keep only runs in this status (pending, running, success,
                failed or cancelled).
            limit: how many runs to return (at most 100).

        Returns:
            A JSON object with the runs and how many were returned.
        """
        require(limit > 0, "limit must be at least 1")
        require(limit <= MAX_TASKS_PER_CALL, f"limit is capped at {MAX_TASKS_PER_CALL}")

        wanted: TaskStatus | None = None
        if status is not None:
            try:
                wanted = TaskStatus(status)
            except ValueError:
                known = ", ".join(member.value for member in TaskStatus)
                message = f"unknown status {status!r}: expected one of {known}"
                raise UsageError(message) from None

        tasks = await services.manager.list(status=wanted, limit=limit)
        return json.dumps(
            {
                "returned": len(tasks),
                "has_more": len(tasks) == limit,
                "tasks": [_summarize(task) for task in tasks],
            },
        )
