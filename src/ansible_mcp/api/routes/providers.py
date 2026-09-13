"""Configuring where inventories come from, over HTTP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from ansible_mcp.api.models import AddProviderRequest
from ansible_mcp.operations import providers
from ansible_mcp.operations.errors import NotFoundError
from ansible_mcp.operations.recording import record

if TYPE_CHECKING:
    from ansible_mcp.operations import Services


def router(services: Services, prefix: str) -> APIRouter:
    """Return the provider routes, bound to the services they act on."""
    api = APIRouter(prefix=prefix, tags=["providers"])

    @api.get("/providers")
    async def list_providers() -> dict[str, Any]:
        """List configured providers and the plugin types available here.

        Each configured provider says whether it currently works: one whose
        inventory file has moved is listed with the problem, rather than
        failing when a run finally needs it.
        """
        async with record(services.audit, "list_providers", {}):
            return await providers.configured(services)

    @api.put("/providers/{name}")
    async def add_provider(name: str, body: AddProviderRequest) -> dict[str, Any]:
        """Configure a source of inventories under this name, replacing any.

        The configuration is validated before it is stored, so a provider that
        cannot work is refused here rather than at the start of a run.

        Credentials do not belong in the configuration: name the environment
        variable they are read from instead, for example token_env=YC_TOKEN. A
        value that looks like a credential is refused.
        """
        arguments = {"name": name, **body.model_dump(exclude_none=True)}
        async with record(services.audit, "add_provider", arguments):
            return await providers.add(services, name, body.plugin_type, body.config)

    @api.get("/providers/{name}/inventory")
    async def get_inventory(name: str, full: bool = False) -> dict[str, Any]:
        """Ask a configured provider what hosts it currently resolves to.

        Answers what a run would actually be pointed at, without starting one.
        Only the opening lines come back unless full=true is asked for.
        """
        async with record(services.audit, "get_inventory", {"provider": name, "full": full}):
            return await providers.inventory(services, name, full=full)

    @api.delete("/providers/{name}")
    async def delete_provider(name: str) -> dict[str, Any]:
        """Remove a provider's configuration.

        Runs already made through it keep the inventory they used, so history is
        intact. Nothing on the hosts is touched.
        """
        async with record(services.audit, "delete_provider", {"name": name}):
            removed = await providers.delete(services, name)
            if not removed["deleted"]:
                message = f"no provider configured as {name!r}"
                raise NotFoundError(message)
            return removed

    return api
