"""Entry point: configure logging, refuse unsafe exposure, serve."""

from __future__ import annotations

import logging

from ansible_mcp.config import get_settings
from ansible_mcp.server import build_application, ensure_safe_to_expose
from ansible_mcp.server.http import serve_http


def main() -> None:
    """Start the server with the transport the environment asks for."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ensure_safe_to_expose(settings)

    application = build_application(settings)
    if settings.transport == "stdio":
        application.server.run(transport="stdio")
    else:
        serve_http(application, settings)


if __name__ == "__main__":
    main()
