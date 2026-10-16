"""文本模型适配层：只负责请求、解析和脱敏，不直接写业务数据库。"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.core.config import Settings, get_settings


def _safe_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="模型返回的结构无法解析，请稍后重试") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=502, detail="模型返回格式不正确，请稍后重试")
    return value


def request_structured(
    prompt: str, *, model: str | None = None, api_key: str | None = None,
    endpoint_url: str | None = None, settings: Settings | None = None
) -> dict:
    """调用文本模型 JSON 输出；任何供应商原文都不会返回给浏览器或写入日志。"""
    settings = settings or get_settings()
    key = (api_key if api_key is not None else settings.openai_api_key.get_secret_value()).strip()
    model = (model or settings.openai_text_model).strip()
    endpoint = (endpoint_url or "https://api.openai.com/v1").rstrip("/")
    if not key or not model:
        raise HTTPException(
            status_code=503, detail="文本服务尚未配置，请在本机环境配置密钥和模型后重建服务"
        )
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "你是电商运营助手，只输出符合要求的 JSON，不要输出 Markdown。",
                },
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()
    request = Request(
            f"{endpoint}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return _safe_json(content)
    except HTTPError as exc:
        if exc.code in (401, 403):
            message = "文本服务认证失败，请检查本机环境密钥和模型权限"
        elif exc.code == 429:
            message = "文本服务暂时限流，请稍后重试"
        else:
            message = "文本服务调用失败，请稍后重试"
        raise HTTPException(status_code=502, detail=message) from exc
    except (
        URLError,
        TimeoutError,
        OSError,
        KeyError,
        IndexError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=502, detail="文本服务暂时不可用，请稍后重试") from exc


def build_prompt(product: dict, skus: list[dict], competitors: list[dict], output: str) -> str:
    """把商品上下文压缩为模型输入，明确禁止编造未提供的事实。"""
    context = json.dumps(
        {"product": product, "skus": skus, "competitors": competitors},
        ensure_ascii=False,
    )
    if output == "diagnosis":
        shape = {
            "target_audience": "...",
            "price_band": "...",
            "selling_point_matrix": [{"point": "...", "evidence": "..."}],
            "conversion_blockers": ["..."],
            "optimization_directions": ["..."],
        }
    elif output == "image_ideas":
        shape = {
            "items": [
                {
                    "title": "...",
                    "layout": "...",
                    "copy": "...",
                    "selling_point": "...",
                    "visual_guidance": "...",
                }
            ]
            * 3
        }
    else:
        shape = {
            "items": [
                {
                    "title": "...",
                    "hook_3s": "...",
                    "shots": [{"scene": "...", "voiceover": "..."}],
                    "call_to_action": "...",
                }
            ]
            * 3
        }
    shape_text = json.dumps(shape, ensure_ascii=False)
    return (
        f"商品上下文：{context}\n只根据已给信息生成，不要编造价格或功效。"
        f"输出 {output}，严格满足 JSON 形状：{shape_text}"
    )
