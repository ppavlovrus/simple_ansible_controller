"""The REST surface: the same controller, for a person with curl.

MCP is the product (ADR-0002); this is the second door onto the same
operations, shaped the way a human or a script expects rather than the way an
agent does (ADR-0015).
"""

from __future__ import annotations

from ansible_mcp.api.app import API_PREFIX, build_api

__all__ = ["API_PREFIX", "build_api"]
