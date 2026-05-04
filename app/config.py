"""
Application configuration loaded from environment variables.
All settings have documented defaults and validation via Pydantic Settings.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object.  Reads from environment variables (case-insensitive)
    and, when APP_ENV != 'production', also from a .env file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = Field(default="development", description="development | production")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # ── OpenRouter ────────────────────────────────────────────────────────────
    openrouter_api_key: str = Field(..., description="OpenRouter API key (required)")
    llm_model: str = Field(default="meta-llama/llama-3.1-70b-instruct")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, ge=64, le=8192)

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = Field(..., description="Supabase project URL (required)")
    supabase_service_role_key: str = Field(..., description="Supabase service-role key (required)")

    # ── Agent ─────────────────────────────────────────────────────────────────
    agent_config_path: str = Field(default="config/agent_config.yaml")
    max_conversation_turns: int = Field(default=50, ge=1, le=500)

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = Field(default="*")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "production", "test"}
        lower = v.lower()
        if lower not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return lower

    @property
    def cors_origins(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.  Call this everywhere you need config."""
    return Settings()
