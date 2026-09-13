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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings.

    Attributes:
        data_dir: root of the state directory holding the database, playbooks,
            task artifacts and inventories.
        api_key: bearer token every HTTP request is checked against. Required to
            serve beyond loopback; the health probe is exempt (ADR-0012).
        host: address the HTTP transport binds to.
        port: port the HTTP transport binds to.
        log_level: root log level.
        max_concurrent_tasks: how many playbooks may run at the same time.
        run_timeout_seconds: how long one run may take before it is cancelled
            and recorded as failed. ``None`` means no limit, which lets a hung
            playbook hold its slot indefinitely.
        transport: ``stdio`` for a locally launched client, ``streamable-http``
            to serve a remote endpoint.
        keep_artifacts_days: how long a finished run's artifacts are kept.
            ``None`` keeps them forever, which is the current behaviour and
            makes the data directory grow without bound. The task itself, with
            its snapshots, is never deleted: only the artifacts are.
        extra_inventory_dirs: directories, besides the data dir's own
            ``inventories``, that a static provider may read inventory files
            from. Anything outside these is refused, so a provider cannot be
            pointed at an arbitrary file on the host.
    """

    model_config = SettingsConfigDict(env_prefix="ANSIBLE_MCP_", extra="ignore")

    data_dir: Path = Path("/data")
    api_key: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    max_concurrent_tasks: int = Field(default=4, ge=1)
    run_timeout_seconds: float | None = Field(default=None, gt=0)
    keep_artifacts_days: int | None = Field(default=None, gt=0)
    transport: Literal["stdio", "streamable-http"] = "stdio"
    extra_inventory_dirs: list[Path] = Field(default_factory=list)

    @field_validator("api_key", mode="after")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        """Treat an empty or blank key as no key at all.

        The safety gate asks whether a key is set, and an empty string is set.
        A container started with ``ANSIBLE_MCP_API_KEY=`` -- which is what an
        unset variable passed through compose looks like -- therefore sailed past
        the refusal and served an endpoint beyond loopback that nothing could
        authenticate to: every request 401, for the operator too. A configuration
        that looks protected while being broken is the failure ADR-0010 named,
        and the honest reading of a blank value is that no key was given.
        """
        if value is None:
            return None
        return value if value.strip() else None

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

    @property
    def inventories_dir(self) -> Path:
        """Directory inventory files are expected in."""
        return self.data_dir / "inventories"

    @property
    def allowed_inventory_dirs(self) -> tuple[Path, ...]:
        """Every directory a provider may read an inventory file from."""
        return (self.inventories_dir, *self.extra_inventory_dirs)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, reading the environment once."""
    return Settings()
