"""What a request body may contain.

Validation here is about shape, not about rules: whether a playbook and a
provider may be named together, or how large a limit may be, is decided by the
operation, so that both surfaces refuse the same things with the same words.

``extra="forbid"`` is the one thing this layer is strict about. A misspelled
field that is silently ignored turns into a run that quietly did something
other than what was asked, which is the failure ADR-0013 refuses to accept from
either direction.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# A playbook is the same document whether it arrives as YAML text or as the
# parsed list of plays, and JSON callers naturally have the latter.
PlaybookSource = str | list[Any] | dict[str, Any]


class Strict(BaseModel):
    """A body that refuses fields it does not know."""

    model_config = ConfigDict(extra="forbid")


class RunRequest(Strict):
    """What to run, and where.

    Exactly one of ``playbook``/``playbook_name`` and exactly one of
    ``inventory``/``provider`` is expected; the run is refused otherwise.
    """

    playbook: PlaybookSource | None = None
    playbook_name: str | None = None
    inventory: str | None = None
    provider: str | None = None
    variables: dict[str, Any] | None = None
    tags: list[str] | None = None
    check: bool = False
    diff: bool = False


class SavePlaybookRequest(Strict):
    """A playbook to store under the name in the path."""

    content: PlaybookSource
    description: str | None = None
    tags: list[str] | None = None


class SyntaxCheckRequest(Strict):
    """A playbook to parse, as text or by the name it is stored under."""

    playbook: PlaybookSource | None = None
    playbook_name: str | None = None


class AddProviderRequest(Strict):
    """A source of inventories, to configure under the name in the path."""

    plugin_type: str
    config: dict[str, Any] | None = None
