from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.health import readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness():
    return {"service": "api", "status": "ok"}


@router.get("/ready")
def ready():
    result = readiness()
    return JSONResponse(
        result,
        status_code=200 if result["status"] == "ok" else 503,
        headers={"Cache-Control": "no-store"},
    )
