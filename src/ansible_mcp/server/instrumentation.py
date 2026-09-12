"""One wrapper around every tool: readable failures, and a record that it happened.

Both concerns belong at the same seam. A tool that raises must reach the agent as
a sentence rather than a traceback, and the call must be recorded whether it
succeeded, was refused or blew up. Keeping them in one decorator means a new tool
cannot pick up half of the contract.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

from ansible_mcp.core.audit import Outcome
from ansible_mcp.server.errors import UsageError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ansible_mcp.core.audit import AuditLog

log = logging.getLogger("ansible_mcp.tools")

P = ParamSpec("P")
R = TypeVar("R")


def instrumented(
    audit: AuditLog,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Return a decorator that audits a tool and tidies its failures.

    ``UsageError`` is a refusal: the call was wrong, the message already explains
    what to do differently, and it passes through as written. Anything else is
    unexpected, so the traceback goes to the operator's log and the agent gets a
    single line, because a stack trace is not something an agent can act on.
    """

    def decorator(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        tool_name = function.__name__

        @functools.wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.monotonic()
            arguments: dict[str, Any] = dict(kwargs)

            def elapsed() -> int:
                return int((time.monotonic() - started) * 1000)

            try:
                result = await function(*args, **kwargs)
            except UsageError as refusal:
                await audit.record(tool_name, arguments, Outcome.REFUSED, str(refusal), elapsed())
                raise
            except Exception as error:
                log.exception("tool %s failed", tool_name)
                message = f"{tool_name} failed: {type(error).__name__}: {error}"
                await audit.record(tool_name, arguments, Outcome.FAILED, message, elapsed())
                raise ToolError(message) from error

            await audit.record(
                tool_name,
                arguments,
                Outcome.OK,
                None,
                elapsed(),
                _task_id_of(result, arguments),
            )
            return result

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
