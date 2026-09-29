"""Domain error envelope (docs/specs/04-wardrobe-api.md, API-REQ-001/002).

Intentional 4xx/5xx errors raised by application code use
`{"error": {"code", "message", "details"}}`. FastAPI's default 422 request
validation format is kept unchanged (API-REQ-002).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

GARMENT_NOT_FOUND = "GARMENT_NOT_FOUND"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
INVALID_IMAGE = "INVALID_IMAGE"
IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
JOB_NOT_FAILED = "JOB_NOT_FAILED"
GARMENT_HAS_HISTORY = "GARMENT_HAS_HISTORY"
INVALID_WEIGHTS = "INVALID_WEIGHTS"
GARMENT_PROCESSING = "GARMENT_PROCESSING"  # added: delete while the worker runs the job


class AppError(Exception):
    """A domain error rendered as the API-REQ-001 envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """OpenAPI model of the error envelope (API-REQ-001, API-REQ-017)."""

    error: ErrorBody


async def _handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    body = ErrorResponse(error=ErrorBody(code=exc.code, message=exc.message, details=exc.details))
    return JSONResponse(status_code=exc.status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
