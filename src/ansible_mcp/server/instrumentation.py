"""One wrapper around every tool: readable failures, and a record that it happened.

Both concerns belong at the same seam. A tool that raises must reach the agent as
a sentence rather than a traceback, and the call must be recorded whether it
succeeded, was refused or blew up. Keeping them in one decorator means a new tool
cannot pick up half of the contract.

The recording itself is shared with the REST surface
(:mod:`ansible_mcp.operations.recording`); what is specific here is turning a
refusal into the SDK's ToolError, which is how a refusal reaches an agent.
"""

from __future__ import annotations

import contextlib
import functools
import json
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

from ansible_mcp.operations.errors import UsageError
from ansible_mcp.operations.recording import failure_message, record

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ansible_mcp.core.audit import AuditLog

P = ParamSpec("P")
R = TypeVar("R")


def instrumented(
    audit: AuditLog,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Return a decorator that audits a tool and tidies its failures.

    ``UsageError`` is a refusal: the call was wrong, the message already explains
    what to do differently, and it reaches the agent as written. Anything else is
    unexpected, so the traceback goes to the operator's log and the agent gets a
    single line, because a stack trace is not something an agent can act on.
    """

    def decorator(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        tool_name = function.__name__

        @functools.wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # The translation happens outside the recording, so the log keeps the
            # distinction between a refusal and a failure that this hides from
            # the agent: over the wire both are a tool error.
            try:
                async with record(audit, tool_name, dict(kwargs)) as call:
                    result = await function(*args, **kwargs)
                    call.task_id = _task_id_of(result, kwargs)
                    return result
            except UsageError as refusal:
                raise ToolError(str(refusal)) from refusal
            except ToolError:
                raise
            except Exception as error:
                raise ToolError(failure_message(tool_name, error)) from error

        return wrapper

    return decorator


def _task_id_of(result: object, arguments: dict[str, Any]) -> str | None:
    """Find the task a call created or acted on.

    Tools answer with a JSON object, so the id of a run they started is right
    there. Reading it here keeps the link in one place instead of asking every
    tool to report it, and a tool that acted on an existing task passed its id in
    as an argument.
    """
    task_id = arguments.get("task_id")
    if isinstance(task_id, str):
        return task_id
    if isinstance(result, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            payload = json.loads(result)
            if isinstance(payload, dict) and isinstance(payload.get("task_id"), str):
                return str(payload["task_id"])
    return None
