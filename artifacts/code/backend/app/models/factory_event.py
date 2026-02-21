"""FactoryEvent model — granular events during a factory run."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class FactoryEvent(TimestampMixin, Base):
    """Represents a single event during a factory run (phase start/end, cost, error, etc.)."""

    __tablename__ = "factory_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factory_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # Event types: phase_start, phase_end, clarify, error, cost, complete
    phase: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    cost_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), default=None)
    cost_provider: Mapped[Optional[str]] = mapped_column(String(50), default=None)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    run = relationship("FactoryRun", back_populates="events", lazy="selectin")

    def __repr__(self) -> str:
        return f"<FactoryEvent type={self.event_type} phase={self.phase}>"
