from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.health import readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness():
    # 存活检查只确认 API 进程能响应，不检查数据库等外部依赖。
    return {"service": "api", "status": "ok"}


@router.get("/ready")
def ready():
    # 就绪检查包含外部依赖；任一必需服务不可用时返回 503。
    result = readiness()
    return JSONResponse(
        result,
        status_code=200 if result["status"] == "ok" else 503,
        headers={"Cache-Control": "no-store"},
    )
