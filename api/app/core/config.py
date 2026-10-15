from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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
    redis_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    uploads_dir: Path = Path("uploads")
    log_level: str = "INFO"

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
