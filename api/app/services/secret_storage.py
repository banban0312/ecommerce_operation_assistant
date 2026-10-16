"""对服务凭据进行认证加密，避免将明文 API Key 写入数据库。"""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    auth_key = get_settings().auth_secret_key.get_secret_value().encode("utf-8")
    # 域分离派生独立加密密钥，避免额外的密钥配置；轮换 AUTH_SECRET_KEY 前需先迁移凭据。
    derived = hmac.new(auth_key, b"ecommerce-operation-service-keys-v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("服务密钥无法解密，请检查认证密钥是否已轮换") from exc
