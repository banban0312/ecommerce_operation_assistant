"""图片/视频 Provider 适配层；密钥只从环境读取，禁止写入任务或日志。"""

import base64
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    storage_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def generate_media(media_type: str, job_id: int, prompt: dict) -> ProviderResult:
    settings = get_settings()
    if media_type == "image":
        if not settings.openai_api_key.get_secret_value():
            return ProviderResult(
                False, error_code="provider_not_configured", error_message="图片服务未配置"
            )
        try:
            response = httpx.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
                json={
                    "model": settings.openai_image_model or "gpt-image-1",
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
    if not settings.video_api_key.get_secret_value() or not settings.video_provider:
        return ProviderResult(
            False, error_code="provider_not_configured", error_message="视频服务未配置"
        )
    if not settings.video_api_url:
        return ProviderResult(
            False, error_code="provider_not_configured", error_message="视频服务接口地址未配置"
        )
    try:
        response = httpx.post(
            settings.video_api_url,
            headers={"Authorization": f"Bearer {settings.video_api_key.get_secret_value()}"},
            json={"model": settings.video_model, "prompt": prompt},
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
