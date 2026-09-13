"""What the controller can be asked to do, independent of who is asking.

Both surfaces sit on this layer. MCP adds tool descriptions, the shapes an agent
tends to send and a confirmation gate; REST adds methods, status codes and a
schema. Neither holds a rule of its own, because a rule held twice is a rule that
eventually differs between them (ADR-0002, ADR-0015).
"""

from __future__ import annotations

from ansible_mcp.operations.errors import (
    NotFoundError,
    UsageError,
    confirmed,
    found,
    require,
)
from ansible_mcp.operations.services import Services

__all__ = [
    "NotFoundError",
    "Services",
    "UsageError",
    "confirmed",
    "found",
    "require",
]
