"""A record of what was asked of this service.

Task history says what ran. It does not say who asked for it, what was refused,
or which calls failed before a task existed at all. After an incident those are
the questions, and "the agent did something" is not an answer anyone accepts.

Entries are append-only and live in the same database as everything else. What
is written is the call, not its payload: a playbook's text is already stored with
its task, and copying it into every audit row would make the log unreadable and
the database large for no gain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from ansible_mcp.core.redaction import is_secret_name, redact
from ansible_mcp.db.models import Base, UtcDateTime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = logging.getLogger("ansible_mcp.audit")

MAX_VALUE_CHARS = 120
MAX_ENTRIES_PER_QUERY = 200


class Outcome(StrEnum):
    """How a call ended."""

    OK = "ok"
    REFUSED = "refused"
    FAILED = "failed"


class AuditEntry(Base):
    """One call, recorded after it finished."""

    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime, default=lambda: datetime.now(UTC), index=True)
    tool: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    arguments: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # The task this call created or acted on, when there is one. Without it the
    # log says a playbook was started but not which run that became, which is
    # the first thing anyone asks afterwards.
    task_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)


@dataclass(frozen=True)
class RecordedCall:
    """An audit entry as it is read back."""

    at: str
    tool: str
    outcome: str
    arguments: str
    detail: str | None
    duration_ms: int | None
    task_id: str | None


def describe_arguments(arguments: dict[str, Any]) -> str:
    """Summarize call arguments into one short, secret-free line.

    Long values are reduced to their size: the interesting part of an audit entry
    is that `run_playbook` was called with a 240-line playbook, not the playbook.

    Every value is measured, whatever its type. An earlier version capped only
    strings and mappings, so a playbook sent as the parsed list of plays -- which
    is the normal path, since that is what coercion exists to accept -- was
    written into the row whole, secrets and all.
    """
    parts = []
    for name, value in sorted(arguments.items()):
        if value is None:
            continue
        if is_secret_name(name):
            parts.append(f"{name}=[redacted]")
        else:
            parts.append(f"{name}={_describe_value(value)}")
    return redact(", ".join(parts))


def _describe_value(value: Any) -> str:
    """Render one argument value, by size once it stops being small."""
    if isinstance(value, dict):
        # Keys are useful for reading the log; values are not worth the risk.
        return f"{{{', '.join(sorted(map(str, value)))}}}" if value else "{}"
    if isinstance(value, str):
        rendered = repr(value)
    elif isinstance(value, list | tuple | set):
        rendered = f"<{type(value).__name__} of {len(value)} items>"
        if len(rendered) <= MAX_VALUE_CHARS:
            return rendered
    else:
        rendered = repr(value)

    if len(rendered) > MAX_VALUE_CHARS:
        lines = value.splitlines() if isinstance(value, str) else []
        measured = f"{len(value)} chars" if isinstance(value, str) else f"{len(rendered)} chars"
        suffix = f", {len(lines)} lines" if lines else ""
        return f"<{measured}{suffix}>"
    return rendered


class AuditLog:
    """Writes and reads the record of calls."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Create the log over the given sessions."""
        self._session_factory = session_factory

    async def record(
        self,
        tool: str,
        arguments: dict[str, Any],
        outcome: Outcome,
        detail: str | None = None,
        duration_ms: int | None = None,
        task_id: str | None = None,
    ) -> None:
        """Write one entry.

        Failing to write an audit entry must not fail the call that was already
        performed, so a storage error is logged and swallowed. Losing the record
        is bad; pretending a completed run failed is worse.
        """
        try:
            async with self._session_factory() as session:
                session.add(
                    AuditEntry(
                        tool=tool,
                        outcome=outcome.value,
                        arguments=describe_arguments(arguments),
                        detail=redact(detail) if detail else None,
                        duration_ms=duration_ms,
                        task_id=task_id,
                    ),
                )
                await session.commit()
        except Exception:
            log.exception("could not write an audit entry for %s", tool)

    async def recent(self, limit: int = 50) -> list[RecordedCall]:
        """Return the most recent calls, newest first."""
        limit = min(limit, MAX_ENTRIES_PER_QUERY)
        async with self._session_factory() as session:
            entries = await session.scalars(
                select(AuditEntry)
                .order_by(AuditEntry.at.desc(), AuditEntry.id.desc())
                .limit(limit),
            )
            return [
                RecordedCall(
                    at=entry.at.isoformat(),
                    tool=entry.tool,
                    outcome=entry.outcome,
                    arguments=entry.arguments,
                    detail=entry.detail,
                    duration_ms=entry.duration_ms,
                    task_id=entry.task_id,
                )
                for entry in entries
            ]
