"""ApiUsageLog model — per-call log of API usage, cost, and latency."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApiUsageLog(TimestampMixin, Base):
    """Records every external AI API call for cost tracking and auditing."""

    __tablename__ = "api_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_estimated: Mapped[float] = mapped_column(Numeric(10, 6), default=0.0, nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    factory_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factory_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    phase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ApiUsageLog provider={self.provider_name!r} model={self.model_name!r}"
            f" success={self.success} cost={self.cost_estimated}>"
        )
