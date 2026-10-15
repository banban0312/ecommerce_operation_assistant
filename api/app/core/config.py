from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Application settings loaded from environment variables or the local .env file."""

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
        # Build the URL from separate fields so special characters in credentials are escaped safely.
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
    # Reuse one settings object per process instead of reparsing environment values per request.
    return Settings()
