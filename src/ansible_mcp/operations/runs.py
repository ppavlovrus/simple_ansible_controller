"""Starting playbook runs, and following them.

Two rules shape every answer. It carries the fields a caller decides on, not a
dump of the row; and anything unbounded -- run lists, log output -- is capped
(ADR-0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ansible_mcp.core import InvalidPlaybookError, SubmitRequest, validate_playbook
from ansible_mcp.db import TaskStatus
from ansible_mcp.operations.coercion import as_list, as_mapping, as_text
from ansible_mcp.operations.errors import UsageError, found, require
from ansible_mcp.operations.limits import (
    DEFAULT_LOG_LINES,
    MAX_LOG_LINES_PER_CALL,
    MAX_TASKS_PER_CALL,
)
from ansible_mcp.operations.playbooks import resolve
from ansible_mcp.providers import ProviderError

if TYPE_CHECKING:
    from ansible_mcp.db import Task
    from ansible_mcp.operations.services import Services


def summarize(task: Task) -> dict[str, Any]:
    """Return the fields of a run a caller actually decides on."""
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


async def start(
    services: Services,
    *,
    playbook: Any = None,
    playbook_name: str | None = None,
    inventory: Any = None,
    provider: str | None = None,
    variables: Any = None,
    tags: Any = None,
    check: bool = False,
    diff: bool = False,
) -> dict[str, Any]:
    """Start a run in the background and return its identifier.

    Exactly one of ``playbook``/``playbook_name`` says what to run, and exactly
    one of ``inventory``/``provider`` says where.

    Args:
        services: what to run it with.
        playbook: the playbook, as YAML text or as the parsed list of plays.
        playbook_name: name of a stored playbook to run instead.
        inventory: the inventory, as INI or YAML text.
        provider: name of a configured provider to resolve the inventory from.
        variables: extra variables for the run.
        tags: Ansible tags to limit the run to.
        check: run with ``--check``, changing nothing on the hosts.
        diff: run with ``--diff``, reporting what each change would alter.

    Returns:
        The identifier of the created run and its initial status.

    Raises:
        UsageError: if the sources are ambiguous or missing, the playbook is
            empty or malformed, or the provider cannot resolve an inventory.
        NotFoundError: if a named playbook is not stored here.
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

    content = await resolve(services, playbook, playbook_name)
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
    return {
        "task_id": task_id,
        "status": TaskStatus.PENDING.value,
        "check_mode": check,
    }


async def status(services: Services, task_id: str) -> dict[str, Any]:
    """Report how a run is doing, or how it ended.

    Args:
        services: where to look the run up.
        task_id: identifier returned when the run was started.

    Returns:
        The run's status, timestamps, exit code and error message.

    Raises:
        NotFoundError: if there is no such run.
    """
    task = found(await services.manager.get(task_id), f"no task with id {task_id!r}")
    return summarize(task)


async def logs(
    services: Services,
    task_id: str,
    *,
    tail: int = DEFAULT_LOG_LINES,
    after_line: int = 0,
) -> dict[str, Any]:
    """Read what a run printed, most recent lines last.

    Args:
        services: where to read the output from.
        task_id: identifier returned when the run was started.
        tail: how many trailing lines to return (at most 2000).
        after_line: return only the lines after this position in the output, as
            reported by a previous call's ``next_line``. 0 returns the tail.

    Returns:
        The lines, how many were returned, and the position to continue from.

    Raises:
        UsageError: if the window asked for is empty or larger than a call may
            return.
        NotFoundError: if there is no such run.
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

    return {
        "task_id": task_id,
        "returned_lines": len(selected),
        "next_line": consumed,
        "may_have_more": total > consumed,
        "output": output,
    }


async def cancel(services: Services, task_id: str) -> dict[str, Any]:
    """Ask one queued or running playbook to stop.

    Cancelling mid-run leaves the hosts in whatever state the playbook reached:
    the tasks already applied are not rolled back.

    Args:
        services: where the run lives.
        task_id: identifier returned when the run was started.

    Returns:
        Whether the run was asked to stop, and the status it was in.

    Raises:
        NotFoundError: if there is no such run.
    """
    task = found(await services.manager.get(task_id), f"no task with id {task_id!r}")
    cancelled = await services.manager.cancel(task_id)
    return {
        "task_id": task_id,
        "cancelled": cancelled,
        "status": task.status.value,
        "note": None if cancelled else "the task had already reached a final status",
    }


async def recent(
    services: Services,
    *,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent runs, newest first.

    Args:
        services: what to list.
        status: keep only runs in this status.
        limit: how many runs to return (at most 100).

    Returns:
        The runs and whether the limit cut the answer short.

    Raises:
        UsageError: if the status is not one a run can be in, or the limit is
            outside what a single call may return.
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
    return {
        "returned": len(tasks),
        "has_more": len(tasks) == limit,
        "tasks": [summarize(task) for task in tasks],
    }
