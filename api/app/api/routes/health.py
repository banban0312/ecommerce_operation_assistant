from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.health import readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness():
    # Liveness only answers whether this API process can serve requests; it avoids dependency checks.
    return {"service": "api", "status": "ok"}


@router.get("/ready")
def ready():
    # Readiness includes external dependencies and returns 503 while any required service is unavailable.
    result = readiness()
    return JSONResponse(
        result,
        status_code=200 if result["status"] == "ok" else 503,
        headers={"Cache-Control": "no-store"},
    )
