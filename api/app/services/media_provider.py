"""图片/视频 Provider 适配层；密钥只从环境读取，禁止写入任务或日志。"""

from dataclasses import dataclass

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
        # 真实 OpenAI 图片调用在生产适配器中完成；未配置存储时不伪造可用素材。
        return ProviderResult(
            False, error_code="provider_unavailable", error_message="图片服务暂不可用"
        )
    if not settings.video_api_key.get_secret_value() or not settings.video_provider:
        return ProviderResult(
            False, error_code="provider_not_configured", error_message="视频服务未配置"
        )
    return ProviderResult(
        False, error_code="provider_unavailable", error_message="视频服务暂不可用"
    )
