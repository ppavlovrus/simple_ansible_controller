"""How a tool refuses a call.

A refusal is part of a tool's contract: the arguments were wrong, the thing does
not exist, or a destructive action was not confirmed. The message is written for
the agent, so it says what to do differently.

Turning an unexpected failure into something readable is the job of
:mod:`ansible_mcp.server.instrumentation`, which wraps every tool.
"""

from __future__ import annotations

from typing import TypeVar

from mcp.server.mcpserver.exceptions import ToolError

T = TypeVar("T")


class UsageError(ToolError):
    """The call itself was wrong: a missing task, a bad argument, a refused action.

    Raised deliberately by tools. The message is written for the agent, so it
    says what to do differently rather than what failed internally.
    """


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
