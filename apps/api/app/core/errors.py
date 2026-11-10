"""App-wide error shape `{"error": "code", "detail": "..."}` (docs/CONTRACTS.md section 2).

Covers core's `ApiError`, any `HTTPException` (including routing 404/405) and request validation
errors, for every route under /core and /agent. Agreed with Shivansh in docs/STATUS.md.
An `HTTPException` whose `detail` is already `{"error", "detail"}` is passed through as-is.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    503: "unavailable",
}


class ApiError(Exception):
    def __init__(self, status_code: int, error: str, detail: str) -> None:
        self.status_code, self.error, self.detail = status_code, error, detail


def error_body(status_code: int, detail: Any) -> dict[str, str]:
    if isinstance(detail, dict) and {"error", "detail"} <= detail.keys():
        return {"error": str(detail["error"]), "detail": str(detail["detail"])}
    code = STATUS_CODES.get(status_code, "internal_error" if status_code >= 500 else "error")
    return {"error": code, "detail": str(detail)}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": exc.error, "detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            error_body(exc.status_code, exc.detail),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
            for e in exc.errors()
        )
        return JSONResponse({"error": "validation_error", "detail": detail}, status_code=422)
