"""Cấu hình ứng dụng, đọc từ biến môi trường (tiền tố OMNITEST_). Không có giá trị bí mật mặc định."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNITEST_", env_file=".env", extra="ignore")

    env: str = Field(default="development", description="development | test | production")
    database_url: str = "postgresql+asyncpg://omnitest:omnitest@127.0.0.1:5432/omnitest"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Khóa chủ 32 byte (base64 urlsafe) dùng mã hóa secret bằng AES-GCM. Bắt buộc, không mặc định.
    master_key: SecretStr

    session_cookie_name: str = "omnitest_session"
    session_ttl_hours: int = 12
    cookie_secure: bool = True

    login_max_failures: int = 5
    login_lock_minutes: int = 15

    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("env")
    @classmethod
    def _check_env(cls, v: str) -> str:
        if v not in {"development", "test", "production"}:
            raise ValueError("OMNITEST_ENV phải là development, test hoặc production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
