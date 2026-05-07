"""Exception handlers. Map domain `MFTError`s to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from my_family_tree.core.errors import MFTError
from my_family_tree.core.logging import get_logger

log = get_logger(__name__)


async def _mft_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, MFTError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


async def _generic_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("api.unhandled", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "internal server error"}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(MFTError, _mft_error_handler)
    app.add_exception_handler(Exception, _generic_handler)
