"""ModelProvider model — registry of external AI model providers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelProvider(TimestampMixin, Base):
    """Represents an external AI provider with routing and health metadata."""

    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_key_env_var: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    openai_compatible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(50), default="litellm", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ModelProvider name={self.name!r} enabled={self.is_enabled}"
            f" healthy={self.is_healthy}>"
        )
