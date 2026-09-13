"""How an operation refuses a call.

A refusal is part of the contract: the arguments were wrong, the thing does not
exist, or a destructive action was not confirmed. The message is written for the
caller, so it says what to do differently.

These are surface-independent on purpose. The MCP layer turns a refusal into a
tool error, the REST layer into a 4xx, and neither has to invent its own
vocabulary for "you asked for a task that is not here".
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class UsageError(Exception):
    """The call itself was wrong: a bad argument, or a refused action.

    Raised deliberately by an operation. The message is written for the caller,
    so it says what to do differently rather than what failed internally.
    """


class NotFoundError(UsageError):
    """The call named something that is not here: a task, a playbook, a provider.

    A subclass rather than a flag, because REST has to answer 404 where it would
    otherwise answer 400, and MCP does not care about the difference: to an agent
    both are the same refusal with the same message.
    """


def require(condition: bool, message: str) -> None:
    """Refuse the call with ``message`` unless ``condition`` holds."""
    if not condition:
        raise UsageError(message)


def found(value: T | None, message: str) -> T:
    """Return ``value``, refusing the call with ``message`` if it is missing.

    Checks and narrows in one step, so operations do not need an assert to
    convince the type checker that a lookup succeeded.
    """
    if value is None:
        raise NotFoundError(message)
    return value


def confirmed(confirm: bool, action: str) -> None:
    """Refuse a destructive action that was not explicitly confirmed.

    Destructive tools take ``confirm=false`` by default, so an agent acting on an
    ambiguous instruction has to state its intent a second time (ADR-0007). REST
    does not use this: there the method is the statement of intent (ADR-0015).
    """
    if not confirm:
        message = (
            f"{action} is destructive and was not confirmed. "
            f"Re-issue the call with confirm=true if this is intended."
        )
        raise UsageError(message)
