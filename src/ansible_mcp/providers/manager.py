"""Configured providers: what is set up, and what inventory each one yields.

Configuration is stored; credentials are not. A provider's configuration names
the environment variables its credentials come from, and the values stay in the
environment (ADR-0006), so a copy of the database carries no secrets.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select

from ansible_mcp.db import ProviderConfig
from ansible_mcp.providers.base import ProviderConfigError, ProviderRegistry

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SECRET_HINTS = ("password", "token", "secret", "key", "credential")


@dataclass(frozen=True)
class ConfiguredProvider:
    """A provider as it is set up on this instance."""

    name: str
    plugin_type: str
    config: dict[str, Any]
    usable: bool
    problem: str | None


@dataclass(frozen=True)
class PluginType:
    """A plugin type this installation can configure."""

    plugin_type: str
    description: str


def looks_like_a_secret(key: str, value: Any) -> bool:
    """Whether a configuration entry looks like a credential value.

    Names ending in ``_env`` are the intended way to reference a credential, so
    they are allowed: they hold the name of an environment variable, not its
    value.

    A nested value counts. Only looking at top-level strings meant
    ``{"auth": {"token": "..."}}`` was stored happily, which breaks the promise
    that a copy of the database carries no secrets (ADR-0006).
    """
    lowered = key.lower()
    if lowered.endswith("_env"):
        return False
    if any(hint in lowered for hint in SECRET_HINTS):
        return isinstance(value, str | int | float) or bool(value)
    return _nested_secret(value)


def _nested_secret(value: Any) -> bool:
    """Whether anything inside a container looks like a credential."""
    if isinstance(value, dict):
        return any(looks_like_a_secret(str(key), nested) for key, nested in value.items())
    if isinstance(value, list | tuple | set):
        return any(_nested_secret(item) for item in value)
    return False


class Providers:
    """Stores provider configuration and turns it into inventories."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: ProviderRegistry | None = None,
    ) -> None:
        """Create the service over the given sessions and plugin registry."""
        self._session_factory = session_factory
        self._registry = registry or ProviderRegistry()

    def plugin_types(self) -> list[PluginType]:
        """Return the plugin types available to configure."""
        return [
            PluginType(plugin_type=plugin.plugin_type, description=plugin.description)
            for plugin in self._registry.known_types()
        ]

    async def add(self, name: str, plugin_type: str, config: dict[str, Any]) -> ConfiguredProvider:
        """Configure a provider, replacing any earlier one of the same name.

        The configuration is validated before it is stored, so a provider that
        cannot work is refused at the point where the mistake was made.

        Args:
            name: how runs will refer to this provider.
            plugin_type: which plugin to use.
            config: the plugin's configuration.

        Returns:
            The stored provider.

        Raises:
            ProviderConfigError: if a value looks like a credential, or the
                plugin rejects the configuration.
        """
        leaked = [key for key, value in config.items() if looks_like_a_secret(key, value)]
        if leaked:
            message = (
                f"refusing to store {', '.join(sorted(leaked))}: credentials are read from the "
                f"environment. Name the variable instead, for example token_env='YC_TOKEN'."
            )
            raise ProviderConfigError(message)

        plugin = self._registry.build(plugin_type, config)
        plugin.validate()

        async with self._session_factory() as session:
            existing = await session.get(ProviderConfig, name)
            if existing is None:
                session.add(ProviderConfig(name=name, plugin_type=plugin_type, config=config))
            else:
                existing.plugin_type = plugin_type
                existing.config = config
            await session.commit()

        return ConfiguredProvider(
            name=name,
            plugin_type=plugin_type,
            config=config,
            usable=True,
            problem=None,
        )

    async def list(self) -> list[ConfiguredProvider]:
        """Return configured providers, saying which ones currently work."""
        async with self._session_factory() as session:
            rows = list(await session.scalars(select(ProviderConfig).order_by(ProviderConfig.name)))

        providers = []
        for row in rows:
            problem = await asyncio.to_thread(self._problem_with, row)
            providers.append(
                ConfiguredProvider(
                    name=row.name,
                    plugin_type=row.plugin_type,
                    config=dict(row.config),
                    usable=problem is None,
                    problem=problem,
                ),
            )
        return providers

    async def inventory(self, name: str) -> str:
        """Return the inventory a configured provider currently yields.

        Args:
            name: the configured provider to ask.

        Returns:
            An Ansible inventory.

        Raises:
            ProviderConfigError: if no provider is configured under that name.
            ProviderError: if the provider cannot produce an inventory.
        """
        async with self._session_factory() as session:
            row = await session.get(ProviderConfig, name)

        if row is None:
            message = f"no provider named {name!r} is configured"
            raise ProviderConfigError(message)

        plugin = self._registry.build(row.plugin_type, dict(row.config))
        # A cloud plugin's get_inventory does HTTP, and the Protocol is
        # deliberately synchronous, so this belongs off the event loop: otherwise
        # one run naming a cloud provider stalls every other call in the session.
        return await asyncio.to_thread(plugin.get_inventory)

    async def delete(self, name: str) -> bool:
        """Remove a provider's configuration.

        Returns:
            Whether anything was removed.
        """
        async with self._session_factory() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(ProviderConfig).where(ProviderConfig.name == name)),
            )
            await session.commit()
            return bool(result.rowcount)

    def _problem_with(self, row: ProviderConfig) -> str | None:
        """Return why a stored provider cannot be used, or ``None`` if it can."""
        try:
            plugin = self._registry.build(row.plugin_type, dict(row.config))
            plugin.validate()
        except Exception as error:
            return f"{type(error).__name__}: {error}"
        return None
