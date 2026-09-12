"""Runtime configuration, read from the environment.

Every setting is prefixed with ``ANSIBLE_MCP_`` so the process can be configured
without a config file — the deployment story is a single container with a single
volume, and credentials for provider plugins are read from their own environment
variables, never from here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings.

    Attributes:
        data_dir: root of the state directory holding the database, playbooks,
            task artifacts and inventories.
        api_key: bearer token intended for HTTP callers. **Not enforced yet**:
            nothing checks it against incoming requests, which is why HTTP is
            restricted to loopback (ADR-0010).
        host: address the HTTP transport binds to.
        port: port the HTTP transport binds to.
        log_level: root log level.
        max_concurrent_tasks: how many playbooks may run at the same time.
        run_timeout_seconds: how long one run may take before it is cancelled
            and recorded as failed. ``None`` means no limit, which lets a hung
            playbook hold its slot indefinitely.
        transport: ``stdio`` for a locally launched client, ``streamable-http``
            to serve a remote endpoint.
    """

    model_config = SettingsConfigDict(env_prefix="ANSIBLE_MCP_", extra="ignore")

    data_dir: Path = Path("/data")
    api_key: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    max_concurrent_tasks: int = Field(default=4, ge=1)
    run_timeout_seconds: float | None = Field(default=None, gt=0)
    transport: Literal["stdio", "streamable-http"] = "stdio"

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
