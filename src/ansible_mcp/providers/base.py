"""What a provider plugin is, and how one is found.

A provider answers one question: what hosts should this playbook run against.
It produces an Ansible inventory and validates its own configuration, and that
is the whole contract (ADR-0006). It does not implement Ansible modules and it
does not run anything.

Built-in plugins are registered here. Third-party plugins register themselves
through the ``ansible_mcp.providers`` entry point group, so a new provider needs
no change in this repository.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

log = logging.getLogger("ansible_mcp.providers")

ENTRY_POINT_GROUP = "ansible_mcp.providers"


class ProviderError(Exception):
    """A provider could not do what was asked of it."""


class ProviderConfigError(ProviderError):
    """A provider was configured in a way it cannot work with."""


@runtime_checkable
class ProviderPlugin(Protocol):
    """A source of inventories.

    Implementations are constructed with their configuration and must tolerate a
    configuration that turns out to be wrong: report it from ``validate`` rather
    than raising from ``__init__``, so a bad provider can be listed and fixed
    instead of breaking startup.
    """

    plugin_type: ClassVar[str]
    description: ClassVar[str]

    def __init__(
        self,
        config: dict[str, Any],
        allowed_paths: tuple[Path, ...] = (),
    ) -> None:
        """Build the plugin from its configuration and the host's read policy.

        ``allowed_paths`` are the directories this installation permits a
        provider to read from. The configuration comes from whoever called
        add_provider, which may be an agent, so a plugin that touches the
        filesystem must confine itself to these directories rather than trusting
        a path it was handed.
        """
        ...

    def validate(self) -> None:
        """Check the configuration and any credentials.

        Raises:
            ProviderError: if the provider cannot be used as configured.
        """
        ...

    def get_inventory(self) -> str:
        """Return an Ansible inventory, in INI or YAML format.

        Raises:
            ProviderError: if the inventory cannot be produced.
        """
        ...


class ProviderRegistry:
    """The plugin types this installation knows about."""

    def __init__(
        self,
        allowed_inventory_dirs: tuple[Path, ...] = (),
        *,
        load_entry_points: bool = True,
    ) -> None:
        """Register the built-in plugins and, unless asked not to, installed ones.

        Args:
            allowed_inventory_dirs: directories plugins may read files from.
            load_entry_points: whether to pick up plugins from other packages.
        """
        from ansible_mcp.providers.static import StaticProvider

        self._allowed_paths = allowed_inventory_dirs
        self._types: dict[str, type[ProviderPlugin]] = {
            StaticProvider.plugin_type: StaticProvider,
        }
        if load_entry_points:
            self._load_installed()

    def _load_installed(self) -> None:
        """Add plugins published by other packages.

        A plugin that fails to import is logged and skipped: a broken third-party
        package must not stop the service from serving the providers that work.
        """
        for entry_point in entry_points(group=ENTRY_POINT_GROUP):
            try:
                plugin = entry_point.load()
            except Exception:
                log.exception("provider plugin %r failed to load", entry_point.name)
                continue
            if not isinstance(plugin, type) or not hasattr(plugin, "plugin_type"):
                log.error("provider plugin %r is not a plugin class", entry_point.name)
                continue
            self._types[plugin.plugin_type] = plugin
            log.info("registered provider plugin %r", plugin.plugin_type)

    def known_types(self) -> Iterable[type[ProviderPlugin]]:
        """Return the registered plugin classes, ordered by type name."""
        return [self._types[name] for name in sorted(self._types)]

    def build(self, plugin_type: str, config: dict[str, Any]) -> ProviderPlugin:
        """Instantiate a plugin of the given type.

        Args:
            plugin_type: which plugin to build.
            config: its stored configuration.

        Returns:
            The plugin, not yet validated.

        Raises:
            ProviderConfigError: if no such plugin type is registered.
        """
        plugin = self._types.get(plugin_type)
        if plugin is None:
            known = ", ".join(sorted(self._types))
            message = f"unknown provider type {plugin_type!r}: installed types are {known}"
            raise ProviderConfigError(message)
        return plugin(config, self._allowed_paths)
