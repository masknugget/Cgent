"""Translate domain and framework failures into the stable REST error shape."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from cgent.errors import HarnessError
from cgent.telemetry.request_id import current_request_id, new_id

logger = logging.getLogger(__name__)


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = current_request_id() or getattr(request.state, "request_id", None) or new_id("req")
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message},
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HarnessError)
    async def domain_error(request: Request, exc: HarnessError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "validation_error", "The request is invalid")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        message = exc.detail if isinstance(exc.detail, str) else "The HTTP request failed"
        return error_response(
            request,
            exc.status_code,
            codes.get(exc.status_code, "http_error"),
            message,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error")
        return error_response(request, 500, "internal_error", "An internal error occurred")
