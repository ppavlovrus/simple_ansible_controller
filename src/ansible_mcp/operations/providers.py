"""Configuring where inventories come from."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ansible_mcp.operations.coercion import as_mapping
from ansible_mcp.operations.errors import UsageError, require
from ansible_mcp.operations.limits import INVENTORY_PREVIEW_LINES
from ansible_mcp.providers import ProviderError

if TYPE_CHECKING:
    from ansible_mcp.operations.services import Services


async def add(
    services: Services,
    name: str,
    plugin_type: str,
    config: Any = None,
) -> dict[str, Any]:
    """Configure a source of inventories that runs can name.

    The configuration is validated before it is stored, so a provider that
    cannot work is refused here rather than failing at the start of a run.
    Configuring the same name again replaces it.

    Args:
        services: where to store the configuration.
        name: how runs will refer to this provider.
        plugin_type: which plugin to use; an unknown one is refused.
        config: the plugin's configuration.

    Returns:
        The stored provider and whether it currently works.

    Raises:
        UsageError: if the name is empty, the plugin type is unknown, or the
            configuration is not one the plugin can work with.
    """
    require(bool(name.strip()), "name is empty")
    try:
        provider = await services.providers.add(name, plugin_type, as_mapping(config, "config"))
    except ProviderError as error:
        raise UsageError(str(error)) from error

    return {
        "name": provider.name,
        "plugin_type": provider.plugin_type,
        "usable": provider.usable,
    }


async def configured(services: Services) -> dict[str, Any]:
    """List configured providers and the plugin types available to configure.

    Each configured provider says whether it currently works: one whose
    inventory file has moved is listed with the problem, rather than silently
    failing when a run needs it.

    Args:
        services: what to list.

    Returns:
        The configured providers and the installed plugin types.
    """
    existing = await services.providers.list()
    return {
        "configured": [
            {
                "name": provider.name,
                "plugin_type": provider.plugin_type,
                "config": provider.config,
                "usable": provider.usable,
                "problem": provider.problem,
            }
            for provider in existing
        ],
        "available_plugin_types": [
            {"plugin_type": plugin.plugin_type, "description": plugin.description}
            for plugin in services.providers.plugin_types()
        ],
    }


async def inventory(services: Services, name: str, *, full: bool = False) -> dict[str, Any]:
    """Ask a configured provider what hosts it currently resolves to.

    Args:
        services: where the provider is configured.
        name: name of a configured provider.
        full: return the whole inventory instead of its opening lines.

    Returns:
        The inventory text and whether it was cut short.

    Raises:
        UsageError: if the provider is not configured or cannot resolve.
    """
    try:
        resolved = await services.providers.inventory(name)
    except ProviderError as error:
        raise UsageError(str(error)) from error

    lines = resolved.splitlines(keepends=True)
    truncated = not full and len(lines) > INVENTORY_PREVIEW_LINES
    content = "".join(lines[:INVENTORY_PREVIEW_LINES]) if truncated else resolved

    return {
        "provider": name,
        "total_lines": len(lines),
        "truncated": truncated,
        "inventory": content,
    }


async def delete(services: Services, name: str) -> dict[str, Any]:
    """Remove a provider's configuration. Nothing on the hosts is touched.

    Args:
        services: where the provider is configured.
        name: the configured provider to remove.

    Returns:
        Whether anything was removed.
    """
    deleted = await services.providers.delete(name)
    return {
        "name": name,
        "deleted": deleted,
        "note": None if deleted else "no provider was configured under that name",
    }
