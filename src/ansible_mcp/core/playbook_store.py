"""Keeping playbooks so a run can name one instead of carrying its text.

Content lives in the database next to its metadata rather than in files beside
it. The store is already a single SQLite file (ADR-0003), so putting the text in
a row keeps a save atomic and removes the question of what to do when the file
and the row disagree.

Storing a playbook does not affect runs already created from it: a task keeps its
own snapshot (ADR-0005).
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import yaml
from sqlalchemy import delete, select

from ansible_mcp.db import Playbook

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class InvalidPlaybookError(ValueError):
    """The text offered as a playbook is not one."""


@dataclass(frozen=True)
class StoredPlaybook:
    """A playbook as the store hands it back."""

    name: str
    content: str
    description: str | None
    tags: list[str]
    updated_at: str


def normalize(content: str) -> str:
    """Strip a common indent from a playbook without changing its meaning.

    A playbook copied out of a quoted block, or assembled by an agent from a
    prompt, often arrives with every line shifted right by the same amount. That
    is not a YAML error worth refusing: removing the shared prefix leaves an
    identical document.
    """
    return textwrap.dedent(content).strip("\n") + "\n"


def validate_playbook(content: str) -> None:
    """Check that text is at least shaped like a playbook.

    This is a structural check, not a safety one: a playbook is a YAML list of
    plays. Whether the playbook is a good idea is the caller's judgement to make
    (ADR-0004).

    Args:
        content: the playbook text.

    Raises:
        InvalidPlaybookError: if the text is not YAML, or not a list of mappings.
    """
    if not content.strip():
        message = "the playbook is empty"
        raise InvalidPlaybookError(message)

    content = normalize(content)
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise InvalidPlaybookError(_explain(error, content)) from error

    if not isinstance(parsed, list):
        message = f"a playbook must be a list of plays, got {type(parsed).__name__}"
        raise InvalidPlaybookError(message)
    if not parsed:
        message = "the playbook contains no plays"
        raise InvalidPlaybookError(message)
    for index, play in enumerate(parsed):
        if not isinstance(play, dict):
            message = f"play {index + 1} is not a mapping but {type(play).__name__}"
            raise InvalidPlaybookError(message)


class PlaybookStore:
    """Named playbooks, saved and looked up by name."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Create a store over the given sessions."""
        self._session_factory = session_factory

    async def save(
        self,
        name: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> StoredPlaybook:
        """Store a playbook, replacing any earlier version of the same name.

        Args:
            name: how the playbook is addressed later.
            content: the playbook text.
            description: what it does, for whoever lists the store next.
            tags: labels to group playbooks by.

        Returns:
            The stored playbook.

        Raises:
            InvalidPlaybookError: if the content is not a playbook.
        """
        validate_playbook(content)
        content = normalize(content)

        async with self._session_factory() as session:
            existing = await session.get(Playbook, name)
            if existing is None:
                session.add(
                    Playbook(
                        name=name,
                        content=content,
                        description=description,
                        tags=tags or [],
                    ),
                )
            else:
                existing.content = content
                existing.description = description
                existing.tags = tags or []
            await session.commit()
            stored = await session.get(Playbook, name)
            return _to_stored(stored) if stored else _missing(name)

    async def get(self, name: str) -> StoredPlaybook | None:
        """Return one playbook, or ``None`` if nothing is stored under that name."""
        async with self._session_factory() as session:
            playbook = await session.get(Playbook, name)
            return _to_stored(playbook) if playbook else None

    async def list(self, limit: int = 50) -> list[StoredPlaybook]:
        """Return stored playbooks in alphabetical order."""
        async with self._session_factory() as session:
            playbooks = await session.scalars(
                select(Playbook).order_by(Playbook.name).limit(limit),
            )
            return [_to_stored(playbook) for playbook in playbooks]

    async def delete(self, name: str) -> bool:
        """Remove a playbook.

        Returns:
            Whether anything was removed.
        """
        async with self._session_factory() as session:
            # An UPDATE/DELETE always yields a CursorResult; execute() is typed wider.
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(Playbook).where(Playbook.name == name)),
            )
            await session.commit()
            return bool(result.rowcount)


def _explain(error: yaml.YAMLError, content: str) -> str:
    """Turn a parser error into something the caller can act on.

    A raw PyYAML message points at a line number in a document the caller cannot
    see, which is why an agent handed one tends to retry the identical call.
    Quoting the offending line, and naming the usual cause, gives it something to
    change.
    """
    mark = getattr(error, "problem_mark", None)
    detail = getattr(error, "problem", None) or "could not be parsed"
    if mark is None:
        return f"the playbook is not valid YAML: {detail}"

    lines = content.splitlines()
    quoted = lines[mark.line].rstrip() if 0 <= mark.line < len(lines) else ""
    return (
        f"the playbook is not valid YAML: {detail} on line {mark.line + 1}: {quoted!r}. "
        f"A playbook is a list of plays, so the first line should start with '- ' and every "
        f"line below it must be indented consistently relative to it."
    )


def _to_stored(playbook: Playbook) -> StoredPlaybook:
    """Convert a row into the store's own shape."""
    return StoredPlaybook(
        name=playbook.name,
        content=playbook.content,
        description=playbook.description,
        tags=list(playbook.tags),
        updated_at=playbook.updated_at.isoformat(),
    )


def _missing(name: str) -> StoredPlaybook:
    """Fail loudly: a playbook that was just written must be readable."""
    message = f"playbook {name!r} disappeared immediately after being stored"
    raise RuntimeError(message)
