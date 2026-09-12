"""Entry point: configure logging, refuse unsafe exposure, serve."""

from __future__ import annotations

import logging
import sys

from ansible_mcp.config import get_settings
from ansible_mcp.server import build_application, ensure_safe_to_expose
from ansible_mcp.server.http import serve_http

CONFIGURATION_ERROR = 2


def main() -> int:
    """Start the server with the transport the environment asks for.

    Returns:
        A process exit code. A refused configuration exits 2 with one line,
        because an operator reading a traceback learns nothing they can act on.
    """
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        ensure_safe_to_expose(settings)
    except RuntimeError as error:
        print(f"ansible-mcp: {error}", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
