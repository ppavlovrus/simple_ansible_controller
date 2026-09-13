"""Entry point: configure logging, refuse unsafe exposure, serve."""

from __future__ import annotations

import logging
import sys

from ansible_mcp.config import get_settings
from ansible_mcp.server import (
    build_application,
    ensure_isolation_is_usable,
    ensure_safe_to_expose,
)
from ansible_mcp.server.http import serve_http

CONFIGURATION_ERROR = 2
MAX_MESSAGE_CHARS = 300


def main() -> int:
    """Start the server with the transport the environment asks for.

    Returns:
        A process exit code. A refused configuration exits 2 with one line,
        because an operator reading a traceback learns nothing they can act on.
    """
    # Reading the settings is itself a configuration step that can fail: a
    # non-numeric port, or a list given as bare text where pydantic wants JSON.
    # Both used to reach the operator as a traceback, which is what this
    # function's own docstring says not to do.
    try:
        settings = get_settings()
        logging.basicConfig(
            level=settings.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        ensure_safe_to_expose(settings)
        ensure_isolation_is_usable(settings)
    except (RuntimeError, ValueError) as error:
        print(f"ansible-mcp: {_one_line(error)}", file=sys.stderr)
        return CONFIGURATION_ERROR

    application = build_application(settings)
    if settings.transport == "stdio":
        application.server.run(transport="stdio")
    else:
        try:
            serve_http(application, settings)
        except RuntimeError as error:
            print(f"ansible-mcp: {error}", file=sys.stderr)
            return CONFIGURATION_ERROR
    return 0


def _one_line(error: Exception) -> str:
    """Collapse a validation error into something an operator can act on."""
    text = str(error).replace("\n", "; ")
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS] + "..."
    return text


if __name__ == "__main__":
    raise SystemExit(main())
