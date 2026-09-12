"""Engine and session handling for the SQLite store.

SQLite is the only backend (ADR-0003). It is opened in WAL mode so a reader is
never blocked by the single writer, which is what makes one process serving
concurrent tool calls workable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .models import Base

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


def _apply_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Put every new connection into WAL mode with sane durability settings."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        # NORMAL is the documented companion of WAL: it keeps commits cheap and
        # only risks the last transactions on an OS-level crash, not corruption.
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Wait instead of failing immediately when the single writer is busy.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_engine(database_path: Path) -> AsyncEngine:
    """Create the async engine for a SQLite file, creating its directory.

    Args:
        database_path: file the database lives in. Its parent directory is
            created if missing.

    Returns:
        An engine with the WAL pragmas applied to every new connection.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    event.listen(engine.sync_engine, "connect", _apply_pragmas)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine: AsyncEngine) -> None:
    """Create any missing tables.

    The schema is small and young enough that migrations would cost more than
    they are worth; this is revisited before the first release that other people
    upgrade.
    """
    # Importing registers the audit table on the shared metadata; without it
    # create_all would quietly produce a database missing one table.
    from ansible_mcp.core import audit as _audit  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
