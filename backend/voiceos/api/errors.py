"""Error envelope from plan/docs/06: {error:{code,message,field_errors,retryable},trace_id}."""

import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_DEFAULT_CODES = {
    400: "INVALID_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "BUSINESS_VALIDATION",
    428: "PRECONDITION_REQUIRED",
    429: "THROTTLED",
    503: "UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, field_errors=None, retryable=False):
        self.status, self.code, self.message = status, code, message
        self.field_errors = field_errors or {}
        self.retryable = retryable


def _body(status: int, code: str, message: str, field_errors=None, retryable=False) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "field_errors": field_errors or {},
                "retryable": retryable,
            },
            "trace_id": trace_id_var.get(),
        },
    )


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        token = trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            trace_id_var.reset(token)
        response.headers["x-trace-id"] = trace_id
        return response

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _body(exc.status, exc.code, exc.message, exc.field_errors, exc.retryable)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return _body(exc.status_code, _DEFAULT_CODES.get(exc.status_code, "ERROR"), str(exc.detail))

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError):
        # e.g. two concurrent requests with the same Idempotency-Key; the client retries and gets the replay
        return _body(409, "CONFLICT", "Yêu cầu trùng đang được xử lý, thử lại", retryable=True)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path", "header"))
            fields.setdefault(loc or "_", []).append(err["msg"])
        return _body(400, "INVALID_REQUEST", "Dữ liệu không hợp lệ", fields)
