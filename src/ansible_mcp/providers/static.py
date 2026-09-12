"""The static provider: hosts someone wrote down.

The simplest provider and the one that needs no external API. Either the
inventory is held in the provider's configuration, or it is read from a file,
which is what makes a provider useful for an inventory another tool keeps up to
date.

A file is only read from a directory this installation allows. The configuration
arrives from whoever called add_provider, possibly an agent, and without that
confinement a "provider" would be a way to read any file on the host and have its
contents returned (ADR-0011).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ansible_mcp.providers.base import ProviderConfigError, ProviderError

if TYPE_CHECKING:
    from collections.abc import Sequence


class StaticProvider:
    """An inventory taken verbatim from configuration or from an allowed file."""

    plugin_type: ClassVar[str] = "static"
    description: ClassVar[str] = (
        "A fixed inventory, either written into the provider's configuration "
        "('inventory') or read from a file at run time ('inventory_file', which "
        "must live in one of the directories this server allows). No credentials."
    )

    def __init__(
        self,
        config: dict[str, Any],
        allowed_paths: Sequence[Path] = (),
    ) -> None:
        """Keep the configuration and the read policy; both are checked in validate()."""
        self._inline = config.get("inventory")
        self._path = config.get("inventory_file")
        self._allowed_paths = tuple(allowed_paths)

    def validate(self) -> None:
        """Check that exactly one source is configured and that it may be read.

        Raises:
            ProviderConfigError: if the configuration is unusable, or the file is
                outside every allowed directory.
        """
        if self._inline and self._path:
            message = "configure either 'inventory' or 'inventory_file', not both"
            raise ProviderConfigError(message)
        if not self._inline and not self._path:
            message = (
                "configure 'inventory' with the inventory text or 'inventory_file' with a path"
            )
            raise ProviderConfigError(message)

        if self._inline is not None and not str(self._inline).strip():
            message = "'inventory' is empty"
            raise ProviderConfigError(message)

        if self._path is not None:
            path = self._resolved_path()
            if not path.is_file():
                message = f"inventory_file {str(path)!r} does not exist or is not a file"
                raise ProviderConfigError(message)

    def get_inventory(self) -> str:
        """Return the configured inventory.

        Raises:
            ProviderError: if the configured file cannot be read now, even though
                it validated earlier: files move.
        """
        self.validate()
        if self._inline is not None:
            return str(self._inline)

        path = self._resolved_path()
        try:
            return path.read_text()
        except OSError as error:
            message = f"cannot read inventory_file {str(path)!r}: {error}"
            raise ProviderError(message) from error

    def _resolved_path(self) -> Path:
        """Resolve the configured path, refusing anything outside the allowed dirs.

        Resolution happens before the check so that ``..`` and symlinks cannot
        step out of an allowed directory.

        Raises:
            ProviderConfigError: if the path is not inside an allowed directory.
        """
        path = Path(str(self._path)).expanduser().resolve()

        if not self._allowed_paths:
            message = (
                "this server allows no inventory directories, so 'inventory_file' cannot be "
                "used: pass the inventory inline with 'inventory' instead"
            )
            raise ProviderConfigError(message)

        for allowed in self._allowed_paths:
            if path.is_relative_to(Path(allowed).expanduser().resolve()):
                return path

        permitted = ", ".join(str(allowed) for allowed in self._allowed_paths)
        message = (
            f"inventory_file {str(path)!r} is outside the directories this server reads "
            f"inventories from ({permitted})"
        )
        raise ProviderConfigError(message)
