"""读取工作空间服务配置；密钥仅在服务进程内解密，不进入响应和审计。"""

from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ServiceConfig
from app.schemas.settings import ConnectionCheckRead, ServiceConfigRead, Target
from app.services.secret_storage import decrypt_secret

TARGETS: tuple[Target, ...] = ("text", "image", "video")
DEFAULT_ENDPOINT = "https://api.openai.com/v1"


def runtime_service(db: Session, workspace_id: int, target: Target) -> tuple[str, str, str, str]:
    """返回供应商、模型、服务地址和 API Key，数据库密钥优先于环境默认值。"""
    settings = get_settings()
    row = db.scalar(
        select(ServiceConfig).where(
            ServiceConfig.workspace_id == workspace_id, ServiceConfig.target == target
        )
    )
    if target == "video":
        provider = row.provider if row else settings.video_provider or "none"
        model = row.model if row and row.model else settings.video_model
        endpoint = row.endpoint_url if row and row.endpoint_url else settings.video_api_url
        env_key = settings.video_api_key.get_secret_value()
    else:
        provider = row.provider if row else "openai"
        model = row.model if row and row.model else (
            settings.openai_text_model if target == "text" else settings.openai_image_model
        )
        endpoint = row.endpoint_url if row and row.endpoint_url else DEFAULT_ENDPOINT
        env_key = settings.openai_api_key.get_secret_value()
    key = decrypt_secret(row.api_key_encrypted) if row and row.api_key_encrypted else env_key
    return provider, model, endpoint.rstrip("/"), key.strip()


def read_services(db: Session, workspace_id: int) -> list[ServiceConfigRead]:
    """返回可编辑参数及密钥状态，绝不返回密钥本身。"""
    rows = db.scalars(select(ServiceConfig).where(ServiceConfig.workspace_id == workspace_id)).all()
    by_target = {row.target: row for row in rows}
    result = []
    for target in TARGETS:
        provider, model, endpoint, key = runtime_service(db, workspace_id, target)
        row = by_target.get(target)
        key_source = "workspace" if row and row.api_key_encrypted else "environment"
        if target == "video" and not endpoint:
            endpoint = ""
        configured = bool(key and model and provider != "none" and endpoint)
        result.append(
            ServiceConfigRead(
                target=target,
                provider=provider,
                model=model,
                endpoint_url=endpoint,
                has_api_key=bool(key),
                configured=configured,
                key_source=key_source,
            )
        )
    return result


def check_connection(
    service: ServiceConfigRead, *, api_key: str
) -> ConnectionCheckRead:
    """只请求模型元数据，不发生成请求，也不记录供应商响应正文。"""
    now = datetime.now(UTC)
    if not service.configured or not api_key:
        return ConnectionCheckRead(
            target=service.target, ok=False, code="not_configured",
            message="请先填写服务地址、模型名称和 API Key。", checked_at=now,
        )
    if service.target == "video":
        return ConnectionCheckRead(
            target=service.target, ok=False, code="not_supported",
            message="该视频供应商暂不支持通用模型元数据检查。", checked_at=now,
        )
    request = Request(
        f"{service.endpoint_url.rstrip('/')}/models/{quote(service.model, safe='')}",
        headers={"Authorization": f"Bearer {api_key}"}, method="GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            if response.status == 200:
                return ConnectionCheckRead(
                    target=service.target, ok=True, code="model_visible",
                    message="已访问模型元数据；生成权限与额度需在业务调用中确认。", checked_at=now,
                )
    except HTTPError as exc:
        if exc.code in (401, 403):
            code, message = "authorization_failed", "服务商拒绝认证或当前密钥无权访问该模型。"
        elif exc.code == 404:
            code, message = "model_not_found", "服务商未找到该模型，请核对模型名称和权限。"
        elif exc.code == 429:
            code, message = "rate_limited", "服务商暂时限制请求，请稍后重试。"
        else:
            code, message = "provider_error", "服务商连接检查失败，请稍后重试。"
        return ConnectionCheckRead(
            target=service.target, ok=False, code=code, message=message, checked_at=now
        )
    except (URLError, TimeoutError, OSError):
        return ConnectionCheckRead(
            target=service.target, ok=False, code="network_error",
            message="无法连接服务商，请检查服务地址和网络。", checked_at=now,
        )
    return ConnectionCheckRead(
        target=service.target, ok=False, code="provider_error",
        message="服务商返回异常状态，请稍后重试。", checked_at=now,
    )
