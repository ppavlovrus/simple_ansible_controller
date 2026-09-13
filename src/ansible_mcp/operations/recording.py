"""Writing down that a call happened, whichever surface made it.

Both surfaces record the same thing under the same name, because the audit log
answers "what was done here", and the answer must not depend on whether the
caller was an agent over MCP or a person with curl. What it cannot answer is
which of the two it was: one token guards the whole instance (ADR-0012), so
there is nobody to attribute a call to either way.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ansible_mcp.core.audit import Outcome
from ansible_mcp.operations.errors import UsageError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ansible_mcp.core.audit import AuditLog

log = logging.getLogger("ansible_mcp.calls")


@dataclass
class Call:
    """A call in progress, and the run it turns out to be about.

    The link to a task is the first thing anyone wants when reading the log
    afterwards ("it started a playbook, which run was that?"), and for a call
    that creates one it is only known once the work is done.
    """

    task_id: str | None = None


def failure_message(name: str, error: Exception) -> str:
    """Return the one line a caller gets when a call fails unexpectedly.

    A stack trace is not something a caller can act on, so the traceback goes to
    the operator's log and this goes back over the wire.
    """
    return f"{name} failed: {type(error).__name__}: {error}"


@asynccontextmanager
async def record(audit: AuditLog, name: str, arguments: dict[str, Any]) -> AsyncIterator[Call]:
    """Record one call under ``name``, whatever becomes of it.

    A ``UsageError`` is a refusal: the call was wrong and the message already
    says what to do differently. Anything else is unexpected, and is logged with
    its traceback for the operator before it leaves this process.

    Args:
        audit: log to write to.
        name: canonical name of the operation, shared by both surfaces.
        arguments: what it was called with; secrets are removed as it is written.

    Yields:
        The call, so a handler can name the task it created.
    """
    started = time.monotonic()
    initial = arguments.get("task_id")
    call = Call(task_id=initial if isinstance(initial, str) else None)

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        yield call
    except UsageError as refusal:
        await audit.record(name, arguments, Outcome.REFUSED, str(refusal), elapsed())
        raise
    except Exception as error:
        log.exception("%s failed", name)
        await audit.record(
            name,
            arguments,
            Outcome.FAILED,
            failure_message(name, error),
            elapsed(),
        )
        raise

    await audit.record(name, arguments, Outcome.OK, None, elapsed(), call.task_id)
