"""Settings are read from the environment under the ANSIBLE_MCP_ prefix."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ansible_mcp.config import Settings, get_settings
from ansible_mcp.server import ensure_safe_to_expose


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


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_api_key_is_no_api_key(monkeypatch, blank):
    # Found by running compose without a key: the variable reaches the process as
    # an empty string, which "is set" as far as the gate was concerned. The
    # server then bound to 0.0.0.0 and answered 401 to everyone, including
    # whoever started it.
    monkeypatch.setenv("ANSIBLE_MCP_API_KEY", blank)

    assert Settings().api_key is None


def test_a_blank_key_does_not_buy_a_public_bind(monkeypatch):
    monkeypatch.setenv("ANSIBLE_MCP_API_KEY", "")
    monkeypatch.setenv("ANSIBLE_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("ANSIBLE_MCP_TRANSPORT", "streamable-http")

    with pytest.raises(RuntimeError, match="requires ANSIBLE_MCP_API_KEY"):
        ensure_safe_to_expose(Settings())
