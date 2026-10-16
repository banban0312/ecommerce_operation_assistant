"""服务配置的生效值与只读连接探针。"""

from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import ServiceConfig
from app.schemas.settings import ConnectionCheckRead, ServiceConfigRead, Target

TARGETS: tuple[Target, ...] = ("text", "image", "video")


def read_services(
    db: Session, workspace_id: int, settings: Settings | None = None
) -> list[ServiceConfigRead]:
    """数据库参数覆盖环境默认值；密钥始终只从进程环境读取。"""
    settings = settings or get_settings()
    rows = db.scalars(select(ServiceConfig).where(ServiceConfig.workspace_id == workspace_id)).all()
    by_target = {row.target: row for row in rows}
    result: list[ServiceConfigRead] = []
    for target in TARGETS:
        row = by_target.get(target)
        provider = (
            row.provider
            if row
            else (settings.video_provider or "none" if target == "video" else "openai")
        )
        model = (
            row.model
            if row
            else (
                settings.openai_text_model
                if target == "text"
                else settings.openai_image_model
                if target == "image"
                else settings.video_model
            )
        )
        key = settings.video_api_key if target == "video" else settings.openai_api_key
        has_key = bool(key.get_secret_value().strip())
        result.append(
            ServiceConfigRead(
                target=target,
                provider=provider,
                model=model,
                has_api_key=has_key,
                configured=has_key and bool(model) and provider != "none",
            )
        )
    return result


def check_connection(
    service: ServiceConfigRead, settings: Settings | None = None
) -> ConnectionCheckRead:
    """只请求 OpenAI 模型元数据，不发生成请求，也不记录供应商响应正文。"""
    now = datetime.now(UTC)
    if not service.configured:
        return ConnectionCheckRead(
            target=service.target,
            ok=False,
            code="not_configured",
            message="请先配置模型名称和本机环境密钥，再重建服务。",
            checked_at=now,
        )
    if service.target == "video":
        return ConnectionCheckRead(
            target=service.target,
            ok=False,
            code="not_supported",
            message="视频供应商连接检查尚未接入；密钥存在不代表连接成功。",
            checked_at=now,
        )
    settings = settings or get_settings()
    request = Request(
        f"https://api.openai.com/v1/models/{quote(service.model, safe='')}",
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            if response.status == 200:
                return ConnectionCheckRead(
                    target=service.target,
                    ok=True,
                    code="model_visible",
                    message="已访问模型元数据；生成权限与额度需在后续业务调用中确认。",
                    checked_at=now,
                )
    except HTTPError as exc:
        if exc.code in (401, 403):
            code, message = "authorization_failed", "服务商拒绝认证或当前密钥无权访问该模型。"
        elif exc.code == 404:
            code, message = "model_not_found", "服务商未找到该模型，请核对模型名称和访问权限。"
        elif exc.code == 429:
            code, message = "rate_limited", "服务商暂时限制请求，请稍后重试。"
        else:
            code, message = "provider_error", "服务商连接检查失败，请稍后重试。"
        return ConnectionCheckRead(
            target=service.target, ok=False, code=code, message=message, checked_at=now
        )
    except (URLError, TimeoutError, OSError):
        return ConnectionCheckRead(
            target=service.target,
            ok=False,
            code="network_error",
            message="无法连接服务商，请检查网络后重试。",
            checked_at=now,
        )
    return ConnectionCheckRead(
        target=service.target,
        ok=False,
        code="provider_error",
        message="服务商返回异常状态，请稍后重试。",
        checked_at=now,
    )
