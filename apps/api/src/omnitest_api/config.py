"""Cấu hình ứng dụng, đọc từ biến môi trường (tiền tố OMNITEST_). Không có giá trị bí mật mặc định."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # Nơi lưu bằng chứng (ảnh, trace). Giai đoạn sau có thể chuyển sang S3/MinIO.
    artifacts_dir: Path = Path("./artifacts/runs")
    max_upload_bytes: int = 2 * 1024 * 1024
    max_artifact_bytes: int = 50 * 1024 * 1024
    # "redis": gửi job qua Dramatiq; "none": chỉ tạo run (dùng cho test, worker được gọi trực tiếp).
    queue_backend: str = "redis"
    # Run đang chạy mà không có heartbeat quá số phút này sẽ bị đánh dấu lỗi khi worker khởi động.
    stale_run_minutes: int = 15
    # Múi giờ dùng để gom số liệu theo ngày trên dashboard.
    display_timezone: str = "Asia/Ho_Chi_Minh"

    # AI (tùy chọn, tắt mặc định). "none" | "anthropic" | "openai_compatible".
    # Khóa chỉ đặt qua biến môi trường/secret của máy chủ, không bao giờ trả về client hay ghi log.
    ai_provider: Literal["none", "anthropic", "openai_compatible"] = "none"
    ai_api_key: SecretStr | None = None
    ai_model: str = "claude-sonnet-5-5"
    ai_base_url: str | None = None
    ai_timeout_seconds: float = 60
    ai_max_output_tokens: int = 4096

    # Sandbox chạy script code (pytest/Playwright) trong container Docker, tắt mặc định.
    # Worker cần Docker CLI và quyền gọi Docker daemon (nên dùng máy chạy riêng, xem docs/sandbox.md).
    sandbox_enabled: bool = False
    sandbox_image: str = "omnitest-sandbox:latest"
    sandbox_docker_bin: str = "docker"
    sandbox_cpus: float = Field(default=1.0, gt=0, le=16)
    sandbox_memory_mb: int = Field(default=1024, ge=128, le=16384)
    sandbox_pids_limit: int = Field(default=256, ge=32, le=4096)
    sandbox_tmpfs_mb: int = Field(default=512, ge=64, le=8192)
    sandbox_max_output_bytes: int = 50 * 1024 * 1024
    sandbox_proxy_network: str = "bridge"

    def sandbox_settings(self) -> dict[str, object]:
        return {
            "enabled": self.sandbox_enabled,
            "image": self.sandbox_image,
            "docker_bin": self.sandbox_docker_bin,
            "cpus": self.sandbox_cpus,
            "memory_mb": self.sandbox_memory_mb,
            "pids_limit": self.sandbox_pids_limit,
            "tmpfs_mb": self.sandbox_tmpfs_mb,
            "max_output_bytes": self.sandbox_max_output_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
            "proxy_network": self.sandbox_proxy_network,
        }

    @field_validator("env")
    @classmethod
    def _check_env(cls, v: str) -> str:
        if v not in {"development", "test", "production"}:
            raise ValueError("OMNITEST_ENV phải là development, test hoặc production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
