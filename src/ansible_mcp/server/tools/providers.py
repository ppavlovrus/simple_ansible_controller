"""Tools for configuring where inventories come from."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ansible_mcp.operations import providers
from ansible_mcp.operations.errors import confirmed
from ansible_mcp.server.instrumentation import instrumented
from ansible_mcp.server.tools._shared import DELETE, READ, WRITE

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from ansible_mcp.operations import Services


def register(server: MCPServer, services: Services) -> None:
    """Register the provider tools."""
    audited = instrumented(services.audit)

    @server.tool(annotations=WRITE)
    @audited
    async def add_provider(name: str, plugin_type: str, config: Any = None) -> str:
        """Configure a source of inventories that runs can name.

        A provider means a run does not have to carry an inventory: it names the
        provider, and the inventory is resolved when the run starts.

        The configuration is validated before it is stored, so a provider that
        cannot work is refused here rather than failing at the start of a run.
        Configuring the same name again replaces it.

        Credentials do not belong in the configuration: name the environment
        variable they are read from instead, for example token_env='YC_TOKEN'.
        A value that looks like a credential is refused.

        Args:
            name: how runs will refer to this provider.
            plugin_type: which plugin to use. "static" is built in and covers a
                fixed inventory, whether written inline or read from a file;
                list_providers reports any others this installation has. Do not
                invent a type: an unknown one is refused.
            config: the plugin's configuration. For "static", either
                {"inventory": "<inventory text>"} or
                {"inventory_file": "/path/to/hosts"}.

        Returns:
            A JSON object describing the stored provider.
        """
        return json.dumps(await providers.add(services, name, plugin_type, config))

    @server.tool(annotations=READ)
    @audited
    async def list_providers() -> str:
        """List configured providers and the plugin types available to configure.

        Each configured provider says whether it currently works: a provider whose
        inventory file has moved or whose credentials are missing is listed with
        the problem, rather than silently failing when a run needs it.

        Returns:
            A JSON object with the configured providers and the installed plugin
            types.
        """
        return json.dumps(await providers.configured(services))

    @server.tool(annotations=READ)
    @audited
    async def get_inventory(provider: str, full: bool = False) -> str:
        """Ask a configured provider what hosts it currently resolves to.

        Useful before running anything: it answers "what would this actually run
        against" without starting a run. For a cloud provider the answer can
        change between calls, which is the point.

        Args:
            provider: name of a configured provider.
            full: return the whole inventory instead of its opening lines.

        Returns:
            A JSON object with the inventory text and whether it was cut short.
        """
        return json.dumps(await providers.inventory(services, provider, full=full))

    @server.tool(annotations=DELETE)
    @audited
    async def delete_provider(name: str, confirm: bool = False) -> str:
        """Remove a provider's configuration.

        Runs already made through it keep the inventory they used, so history is
        intact. Nothing on the hosts is touched.

        Args:
            name: the configured provider to remove.
            confirm: must be true for the deletion to happen.

        Returns:
            A JSON object saying whether anything was removed.
        """
        confirmed(confirm, f"deleting provider {name!r}")
        return json.dumps(await providers.delete(services, name))
