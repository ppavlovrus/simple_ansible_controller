"""Database schema.

Three tables carry the whole state of the service: what was run (``Task``), what
can be run (``Playbook``) and where it can be run (``ProviderConfig``).

A task stores the playbook and the inventory as text rather than referencing
them, so a finished run stays reproducible after either has changed. See
ADR-0005.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that stays timezone-aware across a round trip.

    SQLite has no timestamp type, so plain ``DateTime(timezone=True)`` silently
    returns naive values on the way back. Anything that then compares them against
    ``datetime.now(UTC)`` raises ``TypeError``, which is a runtime failure in the
    one place it hurts: measuring how long a run took.

    Values are stored in UTC and handed back with ``tzinfo`` set. Naive input is
    rejected rather than guessed at.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Normalize an aware timestamp to UTC before storing it."""
        if value is None:
            return None
        if value.tzinfo is None:
            message = "naive datetime cannot be stored: attach a timezone"
            raise ValueError(message)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Re-attach UTC to a timestamp coming back from the database."""
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def _utcnow() -> datetime:
    """Return the current time as an aware UTC timestamp."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Return an identifier for a new task."""
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Declarative base for every table in the service."""


class TaskStatus(StrEnum):
    """Lifecycle of a single playbook run.

    ``PENDING`` and ``RUNNING`` are transient; the remaining three are terminal
    and never change afterwards.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether no further transition is possible from this status."""
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES = frozenset(
    {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED},
)


class Task(Base):
    """One playbook run, from request to terminal status.

    Attributes:
        id: opaque identifier handed back to the caller.
        playbook_name: name in the playbook store, or ``None`` for inline content.
        playbook_snapshot: the playbook text as it was at launch time.
        inventory_snapshot: the resolved inventory as it was at launch time.
        provider_name: provider that produced the inventory, if any.
        variables: extra variables passed to the run.
        tags: Ansible tags the run was limited to.
        execution_environment: container image the run happens in, when isolation
            is enabled (ADR-0008). ``None`` means the run uses the host.
        status: current lifecycle status.
        exit_code: process exit code once the run has finished.
        error_message: why the run failed, for failures that have no exit code.
        artifacts_dir: directory holding stdout, stderr and runner artifacts.
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)

    playbook_name: Mapped[str | None] = mapped_column(String(255), default=None)
    playbook_snapshot: Mapped[str] = mapped_column(Text)
    inventory_snapshot: Mapped[str] = mapped_column(Text)
    provider_name: Mapped[str | None] = mapped_column(String(255), default=None)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    execution_environment: Mapped[str | None] = mapped_column(String(512), default=None)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=TaskStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    artifacts_dir: Mapped[str | None] = mapped_column(String(1024), default=None)


class Playbook(Base):
    """A playbook held in the store, addressable by a human-readable name."""

    __tablename__ = "playbooks"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=_utcnow,
        onupdate=_utcnow,
    )


class ProviderConfig(Base):
    """Non-sensitive configuration of a provider plugin.

    Credentials are never stored here: ``config`` holds the names of environment
    variables to read them from, not their values (ADR-0006).
    """

    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    plugin_type: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
