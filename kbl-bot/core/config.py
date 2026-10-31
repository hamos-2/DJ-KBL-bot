"""Application configuration using Pydantic Settings v2."""

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Database
    database_url: str = Field(...)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Security — both are REQUIRED
    master_encryption_key: str = Field(...)
    hmac_secret_key: str = Field(...)

    # Worker intervals (seconds)
    worker_live_interval_seconds: int = Field(default=5)
    worker_scheduled_interval_seconds: int = Field(default=60)
    worker_lookahead_days: int = Field(default=60)

    # Provider ("daum" or "mock")
    provider_mode: str = Field(default="daum")

    # Kakao
    kakao_skill_secret: str = Field(default="")

    @field_validator("master_encryption_key", "hmac_secret_key", mode="before")
    @classmethod
    def must_not_be_empty(cls, v: str, info: object) -> str:
        """Raise ValueError if a required secret is empty."""
        if not v or not v.strip():
            raise ValueError(
                f"{info.field_name} must not be empty. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
