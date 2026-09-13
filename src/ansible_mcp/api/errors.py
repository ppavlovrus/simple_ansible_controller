"""Turning a refusal into a status code.

The body is always ``{"error": "<one sentence>"}``, the same shape the token
check answers with, so a script has one thing to read whatever went wrong.

The mapping is deliberately small. 400 means the request was wrong, 404 that
what it named is not here, 500 that this service broke; anything finer would be
inventing distinctions the operations do not make.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from ansible_mcp.operations.errors import NotFoundError, UsageError
from ansible_mcp.operations.recording import failure_message

if TYPE_CHECKING:
    from starlette.requests import Request

BAD_REQUEST = 400
NOT_FOUND = 404
SERVER_ERROR = 500


def install_error_handlers(app: FastAPI) -> None:
    """Answer every failure with a status code and one sentence."""

    async def not_found(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=NOT_FOUND)

    async def refused(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=BAD_REQUEST)

    async def malformed(_request: Request, error: Exception) -> JSONResponse:
        """Report a body pydantic rejected, as a sentence rather than a tree.

        A validation error is the caller getting the request wrong, which is
        what 400 means here; FastAPI's own 422 would be a second way of saying
        the same thing, in a shape nothing else on this surface uses.
        """
        return JSONResponse({"error": _summarize(error)}, status_code=BAD_REQUEST)

    async def broke(_request: Request, error: Exception) -> JSONResponse:
        """Answer a bug in this service without handing over its traceback.

        Nothing is logged here on purpose: a recorded call has already written
        the traceback to the operator's log, and Starlette re-raises after this
        so the server logs it as well. A third copy of the same stack helps
        nobody read the second one.
        """
        return JSONResponse(
            {"error": failure_message("the request", error)},
            status_code=SERVER_ERROR,
        )

    app.add_exception_handler(NotFoundError, not_found)
    app.add_exception_handler(UsageError, refused)
    app.add_exception_handler(RequestValidationError, malformed)
    app.add_exception_handler(Exception, broke)


def _summarize(error: Exception) -> str:
    """Collapse pydantic's error list into one line naming the fields."""
    if not isinstance(error, RequestValidationError):
        return str(error)
    parts = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"] if part != "body") or "body"
        parts.append(f"{where}: {problem['msg']}")
    return "; ".join(parts) or "the request body could not be read"
