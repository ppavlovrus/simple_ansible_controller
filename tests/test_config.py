"""Settings are read from the environment under the ANSIBLE_MCP_ prefix."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ansible_mcp.config import Settings, get_settings


def test_defaults_do_not_require_any_environment():
    settings = Settings()

    assert settings.data_dir == Path("/data")
    assert settings.api_key is None
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.max_concurrent_tasks == 4


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("ANSIBLE_MCP_DATA_DIR", "/srv/state")
    monkeypatch.setenv("ANSIBLE_MCP_API_KEY", "secret")
    monkeypatch.setenv("ANSIBLE_MCP_PORT", "9000")

    settings = Settings()

    assert settings.data_dir == Path("/srv/state")
    assert settings.api_key == "secret"
    assert settings.port == 9000


def test_derived_paths_follow_the_data_dir():
    settings = Settings(data_dir=Path("/srv/state"))

    assert settings.database_path == Path("/srv/state/ansible_mcp.db")
    assert settings.playbooks_dir == Path("/srv/state/playbooks")
    assert settings.tasks_dir == Path("/srv/state/tasks")


def test_concurrency_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(max_concurrent_tasks=0)


def test_settings_are_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ANSIBLE_MCP_PORT", "9100")

    first = get_settings()
    monkeypatch.setenv("ANSIBLE_MCP_PORT", "9200")
    second = get_settings()

    assert first is second
    assert second.port == 9100
    get_settings.cache_clear()
