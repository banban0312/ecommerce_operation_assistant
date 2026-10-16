from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """集中管理应用配置；环境变量会覆盖默认值和本地 .env 文件中的值。"""

    model_config = SettingsConfigDict(extra="ignore")

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "ecommerce"
    mysql_user: str = "ecommerce"
    mysql_password: SecretStr = SecretStr("")
    # 认证密钥必须通过本地环境配置；空值会阻止签发访问令牌。
    auth_secret_key: SecretStr = SecretStr("")
    auth_token_expire_minutes: int = Field(default=60, ge=1, le=10080)
    redis_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    uploads_dir: Path = Path("uploads")
    log_level: str = "INFO"
    # 模型密钥只在进程环境中读取；数据库与响应仅保存非敏感参数和状态。
    openai_api_key: SecretStr = SecretStr("")
    openai_text_model: str = ""
    openai_image_model: str = ""
    video_provider: str = ""
    video_api_key: SecretStr = SecretStr("")
    video_model: str = ""
    video_api_url: str = ""
    media_request_timeout_seconds: int = Field(default=60, ge=5, le=600)

    @property
    def database_url(self) -> URL:
        # 分字段构造连接地址，SQLAlchemy 会正确处理密码中的特殊字符。
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    # 每个进程复用同一个配置对象，避免在每次请求时重新读取配置。
    return Settings()
