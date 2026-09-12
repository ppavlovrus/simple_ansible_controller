"""Providers: the static plugin, the registry, and what may be stored."""

import pytest

from ansible_mcp.providers import (
    ENTRY_POINT_GROUP,
    ProviderConfigError,
    ProviderError,
    ProviderRegistry,
    Providers,
    StaticProvider,
)
from ansible_mcp.providers.manager import looks_like_a_secret

INVENTORY = "[web]\nweb1.example.com\nweb2.example.com\n"


@pytest.fixture
def providers(session_factory, tmp_path):
    registry = ProviderRegistry((tmp_path,), load_entry_points=False)
    return Providers(session_factory, registry)


def test_the_static_plugin_serves_an_inline_inventory():
    plugin = StaticProvider({"inventory": INVENTORY})

    plugin.validate()

    assert plugin.get_inventory() == INVENTORY


def test_the_static_plugin_reads_a_file_at_run_time(tmp_path):
    path = tmp_path / "hosts"
    path.write_text(INVENTORY)
    plugin = StaticProvider({"inventory_file": str(path)}, [tmp_path])
    plugin.validate()

    path.write_text("[web]\nweb3.example.com\n")

    # Resolved when asked, not when configured: that is the point of a file.
    assert "web3" in plugin.get_inventory()


@pytest.mark.parametrize(
    ("config", "complaint"),
    [
        ({}, "configure 'inventory'"),
        ({"inventory": "", "inventory_file": ""}, "configure 'inventory'"),
        ({"inventory": INVENTORY, "inventory_file": "/tmp/x"}, "not both"),
    ],
)
def test_a_misconfigured_static_plugin_says_what_is_wrong(config, complaint):
    with pytest.raises(ProviderConfigError, match=complaint):
        StaticProvider(config, ["/tmp"]).validate()


def test_a_missing_file_inside_an_allowed_directory_is_reported(tmp_path):
    plugin = StaticProvider({"inventory_file": str(tmp_path / "absent")}, [tmp_path])

    with pytest.raises(ProviderConfigError, match="does not exist"):
        plugin.validate()


def test_a_file_outside_the_allowed_directories_is_refused(tmp_path):
    # Without this, configuring a "provider" would be a way to read any file on
    # the host and have its contents handed back by get_inventory.
    plugin = StaticProvider({"inventory_file": "/etc/passwd"}, [tmp_path])

    with pytest.raises(ProviderConfigError, match="outside the directories"):
        plugin.validate()


def test_escaping_an_allowed_directory_with_dot_dot_is_refused(tmp_path):
    allowed = tmp_path / "inventories"
    allowed.mkdir()
    outside = tmp_path / "secret"
    outside.write_text("not an inventory")
    plugin = StaticProvider({"inventory_file": str(allowed / ".." / "secret")}, [allowed])

    with pytest.raises(ProviderConfigError, match="outside the directories"):
        plugin.validate()


def test_a_file_source_is_unusable_when_no_directory_is_allowed(tmp_path):
    path = tmp_path / "hosts"
    path.write_text(INVENTORY)
    plugin = StaticProvider({"inventory_file": str(path)})

    with pytest.raises(ProviderConfigError, match="allows no inventory directories"):
        plugin.validate()


def test_a_file_that_disappears_after_validation_is_reported(tmp_path):
    path = tmp_path / "hosts"
    path.write_text(INVENTORY)
    plugin = StaticProvider({"inventory_file": str(path)}, [tmp_path])
    plugin.validate()

    path.unlink()

    with pytest.raises(ProviderError):
        plugin.get_inventory()


def test_the_registry_knows_the_built_in_plugin():
    registry = ProviderRegistry(load_entry_points=False)

    assert [plugin.plugin_type for plugin in registry.known_types()] == ["static"]


def test_the_registry_refuses_an_unknown_type():
    registry = ProviderRegistry(load_entry_points=False)

    with pytest.raises(ProviderConfigError, match="unknown provider type"):
        registry.build("yandex_cloud", {})


def test_a_broken_installed_plugin_does_not_break_the_registry(monkeypatch):
    class Exploding:
        name = "exploding"

        def load(self):
            message = "this plugin is broken"
            raise ImportError(message)

    monkeypatch.setattr(
        "ansible_mcp.providers.base.entry_points",
        lambda group: [Exploding()] if group == ENTRY_POINT_GROUP else [],
    )

    registry = ProviderRegistry()

    assert [plugin.plugin_type for plugin in registry.known_types()] == ["static"]


async def test_adding_then_resolving_a_provider(providers):
    await providers.add("lab", "static", {"inventory": INVENTORY})

    assert await providers.inventory("lab") == INVENTORY

    listed = await providers.list()
    assert len(listed) == 1
    assert listed[0].name == "lab"
    assert listed[0].usable is True
    assert listed[0].problem is None


async def test_a_provider_that_cannot_work_is_refused_when_added(providers, tmp_path):
    with pytest.raises(ProviderConfigError, match="does not exist"):
        await providers.add("lab", "static", {"inventory_file": str(tmp_path / "absent")})

    assert await providers.list() == []


async def test_a_provider_that_breaks_later_is_listed_with_its_problem(providers, tmp_path):
    path = tmp_path / "hosts"
    path.write_text(INVENTORY)
    await providers.add("lab", "static", {"inventory_file": str(path)})

    path.unlink()

    listed = await providers.list()
    assert listed[0].usable is False
    assert "does not exist" in listed[0].problem


async def test_asking_an_unconfigured_provider(providers):
    with pytest.raises(ProviderConfigError, match="no provider named"):
        await providers.inventory("nope")


async def test_configuring_the_same_name_replaces_it(providers):
    await providers.add("lab", "static", {"inventory": INVENTORY})
    await providers.add("lab", "static", {"inventory": "[db]\ndb1\n"})

    assert "db1" in await providers.inventory("lab")
    assert len(await providers.list()) == 1


async def test_deleting_a_provider(providers):
    await providers.add("lab", "static", {"inventory": INVENTORY})

    assert await providers.delete("lab") is True
    assert await providers.delete("lab") is False


async def test_credentials_are_refused_in_the_configuration(providers):
    with pytest.raises(ProviderConfigError, match="credentials are read from the environment"):
        await providers.add("cloud", "static", {"inventory": INVENTORY, "token": "s3cret"})

    assert await providers.list() == []


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("token", "abc", True),
        ("password", "abc", True),
        ("api_key", "abc", True),
        ("secret_value", "abc", True),
        ("credential", "abc", True),
        # Naming the variable is the intended way to reference a credential.
        ("token_env", "YC_TOKEN", False),
        ("password_env", "DB_PASSWORD", False),
        ("folder_id", "b1gxxx", False),
        ("inventory", INVENTORY, False),
        ("port", 22, False),
    ],
)
def test_which_configuration_entries_look_like_secrets(key, value, expected):
    assert looks_like_a_secret(key, value) is expected


def test_the_plugin_types_are_listed_with_descriptions(providers):
    types = providers.plugin_types()

    assert [plugin.plugin_type for plugin in types] == ["static"]
    assert "inventory" in types[0].description


async def test_a_provider_cannot_be_pointed_at_an_arbitrary_host_file(providers):
    with pytest.raises(ProviderConfigError, match="outside the directories"):
        await providers.add("sneaky", "static", {"inventory_file": "/etc/passwd"})

    assert await providers.list() == []


# Found by review: a dict passed every truthiness check and then str()'d into a
# Python repr, which ansible cannot parse and get_inventory showed as if it were
# the inventory.
@pytest.mark.parametrize("value", [{"all": {"hosts": {"web1": None}}}, ["web1", "web2"], 42])
def test_a_non_text_inventory_is_refused(value):
    with pytest.raises(ProviderConfigError, match="must be the inventory text"):
        StaticProvider({"inventory": value}).validate()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("auth", {"token": "real-secret"}),
        ("tokens", ["real-secret"]),
        ("nested", {"cfg": {"password": "real-secret"}}),
    ],
)
async def test_a_nested_credential_is_refused(providers, key, value):
    # ADR-0006 promises a copy of the database carries no secrets, and the guard
    # used to look only at top-level strings.
    with pytest.raises(ProviderConfigError, match="credentials are read from the environment"):
        await providers.add("cloud", "static", {"inventory": INVENTORY, key: value})

    assert await providers.list() == []


async def test_naming_an_environment_variable_is_still_allowed(providers):
    # The intended way to reference a credential must survive the stricter guard.
    await providers.add(
        "lab",
        "static",
        {"inventory": INVENTORY, "token_env": "YC_TOKEN", "folder_id": "b1gxxx"},
    )

    assert (await providers.list())[0].config["token_env"] == "YC_TOKEN"
