import logging
import tempfile
from pathlib import Path

from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def check_database() -> None:
    # 只执行轻量查询来验证连接，不读取或修改业务数据。
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def check_redis() -> None:
    # 设置较短的网络超时，避免 Redis 故障时健康检查长时间挂起。
    with Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1
    ) as client:
        client.ping()


def check_storage() -> None:
    directory = get_settings().uploads_dir
    # Do not silently create a missing volume: an incorrectly mounted path must be unhealthy.
    with tempfile.NamedTemporaryFile(dir=Path(directory), prefix=".health-"):
        pass


def readiness() -> dict:
    # 各依赖独立检查，一次响应中汇总所有不可用项。
    checks = {}
    for name, check in (
        ("database", check_database),
        ("redis", check_redis),
        ("storage", check_storage),
    ):
        try:
            check()
            checks[name] = {"status": "ok"}
        except Exception as exc:
            # Never include a driver/provider exception message; it can contain connection secrets.
            logger.warning("dependency_unavailable", extra={"exception_type": type(exc).__name__})
            checks[name] = {"status": "unavailable"}
    return {
        "service": "api",
        "status": "ok" if all(c["status"] == "ok" for c in checks.values()) else "degraded",
        "checks": checks,
    }
