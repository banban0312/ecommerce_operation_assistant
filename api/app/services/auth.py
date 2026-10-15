import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings, get_settings
from app.models import User


class AuthTokenError(ValueError):
    """访问令牌无效、过期或无法安全签名。"""


def create_access_token(user: User, settings: Settings | None = None) -> str:
    """签发带过期时间的 HMAC-SHA256 访问令牌。"""
    settings = settings or get_settings()
    secret = settings.auth_secret_key.get_secret_value()
    if len(secret) < 32:
        raise AuthTokenError("认证密钥未配置或长度不足")

    expiry = datetime.now(UTC) + timedelta(minutes=settings.auth_token_expire_minutes)
    payload = {"sub": str(user.id), "exp": int(expiry.timestamp())}
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def parse_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """校验令牌签名和过期时间，再返回最小身份载荷。"""
    settings = settings or get_settings()
    secret = settings.auth_secret_key.get_secret_value()
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if len(secret) < 32 or not hmac.compare_digest(signature, _encode(expected)):
            raise AuthTokenError("访问令牌签名无效")
        payload = json.loads(_decode(encoded))
        if int(payload["exp"]) <= int(datetime.now(UTC).timestamp()):
            raise AuthTokenError("访问令牌已过期")
        int(payload["sub"])
    except AuthTokenError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AuthTokenError("访问令牌格式无效") from exc
    return payload


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
