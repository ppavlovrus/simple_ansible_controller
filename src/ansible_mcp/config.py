"""Runtime configuration, read from the environment.

Every setting is prefixed with ``ANSIBLE_MCP_`` so the process can be configured
without a config file — the deployment story is a single container with a single
volume, and credentials for provider plugins are read from their own environment
variables, never from here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings.

    Attributes:
        data_dir: root of the state directory holding the database, playbooks,
            task artifacts and inventories.
        api_key: bearer token required from HTTP callers. ``None`` leaves the
            endpoint unauthenticated, which is only acceptable on a loopback bind.
        host: address the HTTP transport binds to.
        port: port the HTTP transport binds to.
        log_level: root log level.
        max_concurrent_tasks: how many playbooks may run at the same time.
    """

    model_config = SettingsConfigDict(env_prefix="ANSIBLE_MCP_", extra="ignore")

    data_dir: Path = Path("/data")
    api_key: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    max_concurrent_tasks: int = Field(default=4, ge=1)

    @property
    def database_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.data_dir / "ansible_mcp.db"

    @property
    def playbooks_dir(self) -> Path:
        """Directory holding stored playbooks."""
        return self.data_dir / "playbooks"

    @property
    def tasks_dir(self) -> Path:
        """Directory holding per-task private data and artifacts."""
        return self.data_dir / "tasks"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, reading the environment once."""
    return Settings()
