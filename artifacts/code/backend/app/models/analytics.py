"""Analytics model — cost and metric tracking."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Analytics(TimestampMixin, Base):
    """Records individual cost/metric entries for analytics aggregation."""

    __tablename__ = "analytics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factory_runs.id", ondelete="SET NULL"),
        default=None, index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Metric names: cost, quality_score, test_passed, test_failed, test_skipped,
    #               duration_minutes, phase_duration
    metric_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    phase: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    engine: Mapped[Optional[str]] = mapped_column(String(20), default=None)

    def __repr__(self) -> str:
        return (
            f"<Analytics metric={self.metric_name} value={self.metric_value} "
            f"provider={self.provider}>"
        )
