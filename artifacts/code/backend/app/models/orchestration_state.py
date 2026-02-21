"""OrchestrationState model — tracks per-run orchestration phase and barrier state."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrchestrationState(TimestampMixin, Base):
    """Tracks orchestration state for a single factory run, including phase, tier, and barriers."""

    __tablename__ = "factory_orchestration_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factory_runs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    current_phase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phase_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_scores: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model_assignments: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    barrier_manifest: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_gate_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    interface_source: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)

    # Relationships
    run = relationship("FactoryRun", back_populates="orchestration_state")

    def __repr__(self) -> str:
        return (
            f"<OrchestrationState run_id={self.run_id} phase={self.current_phase}"
            f" status={self.phase_status} tier={self.tier}>"
        )
