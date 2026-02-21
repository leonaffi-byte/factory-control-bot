"""Application configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    admin_telegram_id: int = Field(..., description="Admin's Telegram user ID for initial setup")

    # ── Database ──────────────────────────────────────────────
    database_url: str = Field(
        "postgresql+asyncpg://factory:factory@localhost:5432/factory_bot",
        description="PostgreSQL async connection string",
    )
    db_pool_size: int = Field(10, description="SQLAlchemy connection pool size")
    db_max_overflow: int = Field(5, description="SQLAlchemy max overflow connections")
    db_pool_recycle: int = Field(3600, description="Recycle connections after N seconds")

    # ── External API Keys ─────────────────────────────────────
    groq_api_key: str = Field("", description="Groq API key for Whisper transcription")
    openai_api_key: str = Field("", description="OpenAI API key for Whisper fallback + translation")
    openrouter_api_key: str = Field("", description="OpenRouter API key for free models")
    google_api_key: str = Field("", description="Google API key for Gemini engine")
    perplexity_api_key: str = Field("", description="Perplexity API key for research")
    github_token: str = Field("", description="GitHub token for repo management")

    # ── Factory ───────────────────────────────────────────────
    factory_root_dir: Path = Field(
        Path("/home/factory/projects"),
        description="Root directory for all factory projects",
    )
    templates_dir: Path = Field(
        Path("/app/templates"),
        description="Directory containing engine configs and prompt templates",
    )

    # ── Monitoring ────────────────────────────────────────────
    log_poll_interval: int = Field(3, description="Seconds between log file polls")
    max_concurrent_monitors: int = Field(10, description="Max concurrent monitored runs")
    health_check_interval: int = Field(300, description="Seconds between health checks (5 min)")
    idle_timeout_minutes: int = Field(10, description="Minutes before a run is considered stuck")

    # ── Defaults ──────────────────────────────────────────────
    default_engine: str = Field("claude", description="Default engine for new projects")
    quality_gate_threshold: int = Field(97, description="Default quality gate threshold")
    max_quality_retries: int = Field(3, description="Max retries per quality gate")
    max_fix_cycles: int = Field(5, description="Max fix cycles in Phase 6")
    cost_alert_threshold: float = Field(50.0, description="Alert if project cost exceeds this")

    # ── Translation / Transcription ───────────────────────────
    voice_provider: str = Field("auto", description="Transcription provider: groq, openai, or auto")
    translation_model: str = Field("gpt-4o-mini", description="Model for translation via OpenRouter")
    requirements_model: str = Field("gpt-4o-mini", description="Model for structuring requirements")

    # ── Deployment ────────────────────────────────────────────
    domain_name: str | None = Field(None, description="Registered domain for web deployments")
    ssl_email: str | None = Field(None, description="Email for certbot SSL")

    # ── OpenRouter Rate Limiting ──────────────────────────────
    openrouter_daily_limit: int = Field(200, description="Max daily OpenRouter requests")
    openrouter_warn_threshold: float = Field(0.8, description="Warn at this fraction of daily limit")
    openrouter_block_threshold: float = Field(0.95, description="Block new runs at this fraction")

    # ── Logging ───────────────────────────────────────────────
    log_level: str = Field("INFO", description="Application log level")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("database_url must start with 'postgresql'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL for Alembic."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    def mask_key(self, key: str) -> str:
        """Mask an API key for safe display."""
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def get_masked_keys(self) -> dict[str, str]:
        """Return all API keys in masked form for display."""
        return {
            "groq_api_key": self.mask_key(self.groq_api_key),
            "openai_api_key": self.mask_key(self.openai_api_key),
            "openrouter_api_key": self.mask_key(self.openrouter_api_key),
            "google_api_key": self.mask_key(self.google_api_key),
            "perplexity_api_key": self.mask_key(self.perplexity_api_key),
            "github_token": self.mask_key(self.github_token),
        }


def get_settings() -> Settings:
    """Create and return a Settings instance. Cached at module level on first call."""
    return Settings()  # type: ignore[call-arg]
