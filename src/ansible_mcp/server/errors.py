"""Turning failures into something an agent can act on.

A tool that raises leaks a traceback into the agent's context: long, mostly
irrelevant, and impossible to act on. Every tool is wrapped so a failure arrives
as one sentence saying what went wrong, flagged as an error by the protocol.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

log = logging.getLogger("ansible_mcp.tools")

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


class UsageError(ToolError):
    """The call itself was wrong: a missing task, a bad argument, a refused action.

    Raised deliberately by tools. The message is written for the agent, so it
    says what to do differently rather than what failed internally.
    """


def tool_errors(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Wrap a tool so any failure reaches the agent as a readable message.

    ``UsageError`` passes through as written. Anything else is unexpected: it is
    logged with its traceback for the operator and summarized in one line for the
    agent, because a stack trace is not something an agent can act on.
    """

    @functools.wraps(function)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await function(*args, **kwargs)
        except UsageError:
            raise
        except Exception as error:
            log.exception("tool %s failed", function.__name__)
            message = f"{function.__name__} failed: {type(error).__name__}: {error}"
            raise ToolError(message) from error

    return wrapper


def require(condition: bool, message: str) -> None:
    """Refuse the call with ``message`` unless ``condition`` holds."""
    if not condition:
        raise UsageError(message)


def found(value: T | None, message: str) -> T:
    """Return ``value``, refusing the call with ``message`` if it is missing.

    Checks and narrows in one step, so tools do not need an assert to convince
    the type checker that a lookup succeeded.
    """
    if value is None:
        raise UsageError(message)
    return value


def confirmed(confirm: bool, action: str) -> None:
    """Refuse a destructive action that was not explicitly confirmed.

    Destructive tools take ``confirm=false`` by default, so an agent acting on an
    ambiguous instruction has to state its intent a second time (ADR-0007).
    """
    if not confirm:
        message = (
            f"{action} is destructive and was not confirmed. "
            f"Re-issue the call with confirm=true if this is intended."
        )
        raise UsageError(message)
