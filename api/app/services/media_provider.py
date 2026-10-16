"""图片/视频 Provider 适配层；密钥只从环境读取，禁止写入任务或日志。"""

import base64
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.service_settings import runtime_service


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    storage_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def generate_media(
    media_type: str, job_id: int, prompt: dict, db: Session, workspace_id: int
) -> ProviderResult:
    settings = get_settings()
    if media_type == "image":
        _, model, endpoint, key = runtime_service(db, workspace_id, "image")
        if not key:
            return ProviderResult(
                False, error_code="provider_not_configured", error_message="图片服务未配置"
            )
        try:
            response = httpx.post(
                f"{endpoint}/images/generations",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model or "gpt-image-1",
                    "prompt": str(prompt),
                    "size": "1024x1024",
                },
                timeout=settings.media_request_timeout_seconds,
            )
            response.raise_for_status()
            item = response.json().get("data", [{}])[0]
            encoded = item.get("b64_json")
            if not encoded:
                return ProviderResult(
                    False,
                    error_code="provider_invalid_response",
                    error_message="图片服务返回格式异常",
                )
            output = Path(settings.uploads_dir) / "generated" / f"image-{job_id}.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(base64.b64decode(encoded))
            return ProviderResult(True, storage_path=str(output))
        except (httpx.HTTPError, ValueError, OSError):
            return ProviderResult(
                False, error_code="provider_unavailable", error_message="图片服务暂不可用"
            )
    provider, model, endpoint, key = runtime_service(db, workspace_id, "video")
    if not key or provider == "none":
        return ProviderResult(
            False, error_code="provider_not_configured", error_message="视频服务未配置"
        )
    if not endpoint:
        return ProviderResult(
            False, error_code="provider_not_configured", error_message="视频服务接口地址未配置"
        )
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "prompt": prompt},
            timeout=settings.media_request_timeout_seconds,
        )
        response.raise_for_status()
        storage_path = response.json().get("storage_path")
        if not storage_path:
            return ProviderResult(
                False, error_code="provider_invalid_response", error_message="视频服务返回格式异常"
            )
        return ProviderResult(True, storage_path=storage_path)
    except (httpx.HTTPError, ValueError):
        return ProviderResult(
            False, error_code="provider_unavailable", error_message="视频服务暂不可用"
        )
