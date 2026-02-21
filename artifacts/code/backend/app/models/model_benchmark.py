"""ModelBenchmark model — capability and quality benchmarks for AI models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelBenchmark(TimestampMixin, Base):
    """Stores capability metadata and benchmark scores for individual AI models."""

    __tablename__ = "model_benchmarks"

    __table_args__ = (
        UniqueConstraint("model_name", "provider_name", name="uq_model_benchmarks_model_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    context_window: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    benchmark_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    capability_tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    scan_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scan_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_scanned: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ModelBenchmark model={self.model_name!r} provider={self.provider_name!r}"
            f" score={self.overall_score}>"
        )
