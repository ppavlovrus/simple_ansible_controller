"""Tools for running playbooks and following the runs.

Two rules shape every response. It is JSON with the fields an agent needs to
decide what to do next, not a dump of the row; and anything unbounded (task
lists, log output) is capped, because filling the agent's context is a failure
mode of its own (ADR-0002).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.core import InvalidPlaybookError, SubmitRequest, validate_playbook
from ansible_mcp.db import Task, TaskStatus
from ansible_mcp.providers import ProviderError
from ansible_mcp.server.coercion import as_list, as_mapping, as_text
from ansible_mcp.server.errors import UsageError, confirmed, found, require
from ansible_mcp.server.instrumentation import instrumented
from ansible_mcp.server.tools._shared import (
    DEFAULT_LOG_LINES,
    EXECUTE,
    MAX_LOG_LINES_PER_CALL,
    MAX_TASKS_PER_CALL,
    READ,
    STOP,
    Services,
    resolve_playbook,
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
        # A finished run has to say whether it was a dry run: otherwise "it
        # succeeded" reads as "it was applied".
        "check_mode": task.check_mode,
        "diff_mode": task.diff_mode,
    }


def register(server: MCPServer, services: Services) -> None:
    """Register the task tools."""
    audited = instrumented(services.audit)

    @server.tool(annotations=EXECUTE)
    @audited
    async def run_playbook(
        playbook: Any = None,
        playbook_name: str | None = None,
        inventory: Any = None,
        provider: str | None = None,
        variables: Any = None,
        tags: Any = None,
        check: bool = False,
        diff: bool = False,
    ) -> str:
        """Run an Ansible playbook against an inventory and return immediately.

        Say what to run with exactly one of `playbook` or `playbook_name`, and
        where to run it with exactly one of `inventory` or `provider`. Passing
        both of a pair is refused rather than resolved silently, so if a provider
        was configured for these hosts, name the provider and leave `inventory`
        out even when the inventory text is also at hand.

        The run happens in the background: this returns a task id, and the run is
        followed with get_task_status and get_task_logs. Both the playbook and the
        resolved inventory are stored with the task exactly as used, so the run
        can be examined later even if either changes.

        Pass check=true when the user asks what a playbook *would* do, and before
        the first real run against hosts nobody has touched yet: nothing is
        changed, but the hosts are still connected to and the output reports what
        would change. Add diff=true to see the content of those changes. A
        check run is not a substitute for reading the playbook, and a task that
        succeeded in check mode has applied nothing.

        Args:
            playbook: the playbook, as YAML text or as the parsed list of plays.
            playbook_name: name of a stored playbook to run instead.
            inventory: the inventory to run against, in INI or YAML format.
            provider: name of a configured provider to take the inventory from.
            variables: extra variables, the equivalent of --extra-vars.
            tags: run only tasks carrying these tags. Omit for all of them.
            check: run without changing anything (Ansible's --check). The hosts
                are still contacted and the output says what would change.
            diff: show the differences a change would make (Ansible's --diff).
                Most useful together with check.

        Returns:
            A JSON object with task_id and the initial status. The run is not
            finished when this returns.
        """
        # Both sources present is refused rather than resolved by precedence: a
        # run that quietly used the other source than the caller believed is a
        # worse outcome than a refusal that says which argument to drop.
        require(
            bool(inventory) != bool(provider),
            "both inventory and provider were given; drop one. Pass provider alone to take the "
            "inventory from that configured source, or inventory alone with the text."
            if inventory and provider
            else "neither inventory nor provider was given; pass exactly one. Use inventory with "
            "the INI or YAML text, or provider with the name of a configured source.",
        )

        # An agent often sends the parsed document where text is declared, or an
        # empty string where a list is; those mean the same thing and are taken.
        inventory = as_text(inventory, "inventory") if inventory else None
        variable_values = as_mapping(variables, "variables")
        tag_values = as_list(tags, "tags")

        content = await resolve_playbook(services, playbook, playbook_name)
        require(bool(content.strip()), "playbook is empty: pass the playbook YAML as text")
        # The same check save_playbook makes. Without it a malformed playbook
        # became a persisted task, a run directory and an opaque complaint from
        # ansible, where the storing path answers immediately.
        try:
            validate_playbook(content)
        except InvalidPlaybookError as error:
            raise UsageError(str(error)) from error

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
                variables=variable_values,
                tags=tag_values,
                check=check,
                diff=diff,
            ),
        )
        return json.dumps(
            {
                "task_id": task_id,
                "status": TaskStatus.PENDING.value,
                "check_mode": check,
                "hint": "poll get_task_status; read output with get_task_logs",
            },
        )

    @server.tool(annotations=READ)
    @audited
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
    @audited
    async def get_task_logs(
        task_id: str,
        tail: int = DEFAULT_LOG_LINES,
        after_line: int = 0,
    ) -> str:
        """Read what a run printed, most recent lines last.

        Ansible output is long: only the last lines are returned unless more are
        asked for. Read the tail first and widen it if the reason for a failure is
        not visible.

        When following a run that is still going, pass the next_line from the
        previous answer as after_line: that returns only what has appeared since,
        instead of the same lines again.

        Args:
            task_id: identifier returned by run_playbook.
            tail: how many trailing lines to return (at most 2000).
            after_line: return only the lines after this position in the output,
                as reported by a previous call's next_line. 0, the default,
                returns the tail as usual.

        Returns:
            A JSON object with the lines, how many were returned, and next_line
            to pass back on the following call.
        """
        require(tail > 0, "tail must be at least 1")
        require(
            tail <= MAX_LOG_LINES_PER_CALL,
            f"tail is capped at {MAX_LOG_LINES_PER_CALL} lines per call",
        )
        require(after_line >= 0, "after_line cannot be negative")
        found(await services.manager.get(task_id), f"no task with id {task_id!r}")

        # next_line is an absolute position in the output, so a follower can pass
        # it straight back. Counting is a newline scan, not a read into memory.
        total = await services.manager.count_output_lines(task_id)

        if after_line:
            everything = (await services.manager.read_output(task_id)).splitlines()
            selected = everything[after_line : after_line + tail]
            consumed = after_line + len(selected)
            output = "\n".join(selected)
        else:
            output = await services.manager.read_output(task_id, tail)
            selected = output.splitlines()
            consumed = total

        return json.dumps(
            {
                "task_id": task_id,
                "returned_lines": len(selected),
                "next_line": consumed,
                "may_have_more": total > consumed,
                "output": output,
            },
        )

    @server.tool(annotations=STOP)
    @audited
    async def cancel_task(task_id: str, confirm: bool = False) -> str:
        """Stop one queued or running playbook, by id.

        This is not a restart and not a retry: there is no way to resume a run.
        Starting the same work again means calling run_playbook, which creates a
        new run. Stopping several runs means finding their ids with list_tasks
        and calling this once per id; there is no "cancel everything".

        Cancelling mid-run leaves the hosts in whatever state the playbook reached:
        the tasks already applied are not rolled back. That is why this needs
        explicit confirmation.

        Args:
            task_id: identifier returned by run_playbook. Required: this acts on
                exactly one run.
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
    @audited
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
