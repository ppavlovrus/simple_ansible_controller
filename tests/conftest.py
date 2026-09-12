"""Shared fixtures."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ansible_mcp.db import create_engine, create_schema, create_session_factory

FIXTURES = Path(__file__).parent / "fixtures"


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """An engine over a throwaway database file with the schema created."""
    engine = create_engine(tmp_path / "state" / "ansible_mcp.db")
    await create_schema(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A session factory bound to the throwaway database."""
    return create_session_factory(engine)


@pytest.fixture
def local_playbook() -> str:
    """A playbook that runs against the control node itself.

    Keeps the executor tests honest (a real ansible-playbook process runs) while
    needing neither SSH nor a container.
    """
    return (FIXTURES / "local_ping.yml").read_text()


@pytest.fixture
def local_inventory() -> str:
    """An inventory holding only the implicit local host."""
    return (FIXTURES / "local_inventory").read_text()
