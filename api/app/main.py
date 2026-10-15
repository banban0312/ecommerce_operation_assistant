import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.routes import health
from app.core.config import get_settings
from app.db.session import get_engine
from app.observability import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Configure process-wide logging once and release the database pool during graceful shutdown.
    configure_logging(get_settings().log_level)
    logger.info("api_started")
    yield
    get_engine().dispose()
    logger.info("api_stopped")


app = FastAPI(title="电商运营助手 API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    # Keep a stable client-facing error shape without exposing internal exception details.
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "request_id": request.state.request_id,
            "details": {},
        },
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    # Generate request IDs on the server so clients cannot choose or spoof log correlation IDs.
    request.state.request_id = uuid4().hex
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "request_failed",
            extra={"request_id": request.state.request_id, "exception_type": type(exc).__name__},
        )
        response = error_response(request, 500, "SYS_500", "服务暂时不可用")
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(
        "http_request",
        extra={
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    # Translate framework errors to the same public envelope used by other API failures.
    codes = {401: "AUTH_401", 403: "AUTH_403", 404: "BIZ_404", 409: "BIZ_409"}
    messages = {401: "请先登录", 403: "无操作权限", 404: "资源不存在", 409: "状态冲突"}
    return error_response(
        request,
        exc.status_code,
        codes.get(exc.status_code, "SYS_HTTP"),
        messages.get(exc.status_code, "请求未完成"),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo submitted values or validation internals, which may contain sensitive input.
    return error_response(request, 422, "VAL_422", "请求参数不合法")
