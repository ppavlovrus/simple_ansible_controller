"""Starting runs and following them, over HTTP.

A run is a resource: creating one is a POST that answers 202 with where to look,
and everything after that is a GET on what was created. Cancelling is a POST to
a sub-resource rather than a DELETE, because a cancelled run is not removed --
its history, logs and snapshots stay exactly where they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Response

from ansible_mcp.api.models import RunRequest
from ansible_mcp.operations import runs
from ansible_mcp.operations.limits import DEFAULT_LOG_LINES
from ansible_mcp.operations.recording import record

if TYPE_CHECKING:
    from ansible_mcp.operations import Services

ACCEPTED = 202


def router(services: Services, prefix: str) -> APIRouter:
    """Return the run routes, bound to the services they act on."""
    api = APIRouter(prefix=prefix, tags=["runs"])

    @api.post("/runs", status_code=ACCEPTED)
    async def start_run(body: RunRequest, response: Response) -> dict[str, Any]:
        """Start a playbook run and answer before it finishes.

        Say what to run with exactly one of playbook or playbook_name, and where
        with exactly one of inventory or provider. Passing both of a pair is
        refused rather than resolved silently.

        Answers 202 with task_id, status and check_mode, and a Location header
        pointing at the run. Follow it with GET on that location, and read what
        it printed from the logs below it.
        """
        async with record(services.audit, "run_playbook", body.model_dump(exclude_none=True)) as c:
            started = await runs.start(services, **body.model_dump())
            c.task_id = started["task_id"]
        response.headers["Location"] = f"{prefix}/runs/{started['task_id']}"
        return started

    @api.get("/runs")
    async def list_runs(status: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List recent runs, newest first.

        Filter with status (pending, running, success, failed or cancelled) and
        cap with limit, which may not exceed 100. Answers returned, has_more and
        the runs themselves.
        """
        async with record(services.audit, "list_tasks", {"status": status, "limit": limit}):
            return await runs.recent(services, status=status, limit=limit)

    @api.get("/runs/{task_id}")
    async def get_run(task_id: str) -> dict[str, Any]:
        """Report how a run is doing, or how it ended.

        Answers the status, the timestamps, the exit code and, for a failure,
        the error message. check_mode says whether anything was actually applied:
        a run that succeeded with check=true changed nothing.
        """
        async with record(services.audit, "get_task_status", {"task_id": task_id}):
            return await runs.status(services, task_id)

    @api.get("/runs/{task_id}/logs")
    async def get_run_logs(
        task_id: str,
        tail: int = DEFAULT_LOG_LINES,
        after_line: int = 0,
    ) -> dict[str, Any]:
        """Read what a run printed, most recent lines last.

        Only the last lines come back unless more are asked for, at most 2000 per
        call. When following a run still in progress, pass the next_line from the
        previous answer as after_line to get only what has appeared since.

        Secrets the run was given are removed from the output before it is
        returned, as they are everywhere else.
        """
        async with record(
            services.audit,
            "get_task_logs",
            {"task_id": task_id, "tail": tail, "after_line": after_line},
        ):
            return await runs.logs(services, task_id, tail=tail, after_line=after_line)

    @api.post("/runs/{task_id}/cancel")
    async def cancel_run(task_id: str) -> dict[str, Any]:
        """Stop one queued or running playbook.

        Cancelling mid-run leaves the hosts in whatever state the playbook
        reached: what it already applied is not rolled back. A run that had
        already finished answers cancelled=false with its final status.
        """
        async with record(services.audit, "cancel_task", {"task_id": task_id}):
            return await runs.cancel(services, task_id)

    return api
