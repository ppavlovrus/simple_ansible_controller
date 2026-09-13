"""Tools for running playbooks and following the runs.

Each tool is the agent-facing half of an operation in
:mod:`ansible_mcp.operations.runs`: the description it chooses by, the argument
shapes it tends to send, the confirmation gate on anything destructive, and the
hint about what to call next. The rules themselves live below, where REST reads
them too.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.operations import runs
from ansible_mcp.operations.errors import confirmed
from ansible_mcp.operations.limits import DEFAULT_LOG_LINES
from ansible_mcp.server.instrumentation import instrumented
from ansible_mcp.server.tools._shared import EXECUTE, READ, STOP

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from ansible_mcp.operations import Services


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
        execution_environment: str | None = None,
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
            execution_environment: container image to run the playbook inside.
                Accepted only where this installation isolates runs, which
                get_task_status reports; omitting it uses the image configured
                there. It cannot turn isolation on or off, so leave it out
                unless a specific image was asked for.

        Returns:
            A JSON object with task_id and the initial status. The run is not
            finished when this returns.
        """
        started = await runs.start(
            services,
            playbook=playbook,
            playbook_name=playbook_name,
            inventory=inventory,
            provider=provider,
            variables=variables,
            tags=tags,
            check=check,
            diff=diff,
            execution_environment=execution_environment,
        )
        return json.dumps(
            {**started, "hint": "poll get_task_status; read output with get_task_logs"},
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
        return json.dumps(await runs.status(services, task_id))

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
        return json.dumps(await runs.logs(services, task_id, tail=tail, after_line=after_line))

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
        return json.dumps(await runs.cancel(services, task_id))

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
        return json.dumps(await runs.recent(services, status=status, limit=limit))
