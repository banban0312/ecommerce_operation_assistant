import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.routes import auth, catalog, content, health, settings
from app.core.config import get_settings
from app.db.session import get_engine
from app.observability import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # 应用启动时配置日志，正常关闭时释放数据库连接池。
    configure_logging(get_settings().log_level)
    logger.info("api_started")
    yield
    get_engine().dispose()
    logger.info("api_stopped")


app = FastAPI(title="电商运营助手 API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(content.router, prefix="/api/v1")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    # 统一错误响应结构，同时避免向客户端暴露内部异常信息。
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
    # 请求 ID 由服务端生成，避免客户端伪造日志关联标识。
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
    # 将框架 HTTP 异常转换为统一的对外错误格式。
    codes = {401: "AUTH_401", 403: "AUTH_403", 404: "BIZ_404", 409: "BIZ_409"}
    messages = {401: "请先登录", 403: "无操作权限", 404: "资源不存在", 409: "状态冲突"}
    # 业务校验和外部服务失败使用路由定义的安全提示，便于前端指导下一步；认证错误仍统一隐藏细节。
    safe_detail = (
        exc.detail if exc.status_code in {422, 502, 503} and isinstance(exc.detail, str) else None
    )
    return error_response(
        request,
        exc.status_code,
        codes.get(exc.status_code, "SYS_HTTP"),
        safe_detail or messages.get(exc.status_code, "请求未完成"),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # 不回显提交值或校验细节，避免响应包含用户输入的敏感内容。
    return error_response(request, 422, "VAL_422", "请求参数不合法")
