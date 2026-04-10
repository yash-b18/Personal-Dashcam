"""
Application configuration loaded from environment variables.

All settings are validated at startup via Pydantic. Copy .env.example
to .env and fill in values before running the application.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    secret_key: str = Field(..., description="Secret key for signing tokens")
    allowed_origins: str = "http://localhost:3000"

    # ── Database ───────────────────────────────────────────────────
    database_url: str = Field(..., description="PostgreSQL connection string")

    # ── Redis / Celery ─────────────────────────────────────────────
    redis_url: str = Field(..., description="Redis connection string")

    # ── Cloudflare R2 ──────────────────────────────────────────────
    r2_account_id: str = Field(..., description="Cloudflare account ID")
    r2_access_key_id: str = Field(..., description="R2 access key ID")
    r2_secret_access_key: str = Field(..., description="R2 secret access key")
    r2_bucket_name: str = Field(..., description="R2 bucket name")
    r2_public_url: str = Field(..., description="Public R2 bucket URL")

    # ── Claude API ─────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # ── ML ─────────────────────────────────────────────────────────
    yolo_model_path: str = "models/yolov8m.pt"
    feature_dim: int = 128
    lstm_hidden_size: int = 256
    lstm_num_layers: int = 2

    @property
    def cors_origins(self) -> list[str]:
        """Parse allowed origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Return True if running in production environment."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Use as a FastAPI dependency."""
    return Settings()
