import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.responses import ErrorBody, ErrorEnvelope, FieldError

logger = logging.getLogger(__name__)

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"), headers=headers
    )


def _phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    if exc.status_code >= 500:
        logger.warning("app_error", extra={"code": exc.code, "status_code": exc.status_code})
    return error_response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Deliberately omit the submitted input: it may contain passwords or other secrets.
    details = [
        FieldError(field=".".join(str(part) for part in err["loc"]), message=str(err["msg"]))
        for err in exc.errors()
    ]
    return error_response(
        request, 422, "validation_error", "The request contains invalid data.", details=details
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    headers = dict(exc.headers) if exc.headers else None
    return error_response(request, exc.status_code, code, _phrase(exc.status_code), headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    # Unhandled exceptions are caught in RequestContextMiddleware so that
    # request-id and security headers are still applied to the 500 response.
