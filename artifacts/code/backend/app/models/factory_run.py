"""FactoryRun model — represents a single engine run for a project."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class FactoryRun(TimestampMixin, Base):
    """Represents a single factory engine run for a project."""

    __tablename__ = "factory_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=RunStatus.QUEUED.value, index=True,
    )
    current_phase: Mapped[int] = mapped_column(Integer, default=0)
    quality_scores: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    test_results: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    total_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    cost_by_provider: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    duration_minutes: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), default=None)
    started_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    completed_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    tmux_session: Mapped[Optional[str]] = mapped_column(String(100), default=None)
    project_dir: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    last_log_offset: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)

    # Relationships
    project = relationship("Project", back_populates="runs", lazy="selectin")
    events = relationship(
        "FactoryEvent", back_populates="run", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<FactoryRun {self.engine} status={self.status} phase={self.current_phase}>"

    @property
    def project_name(self) -> str:
        """Get project name from relationship or directory."""
        if self.project:
            return self.project.name
        if self.project_dir:
            return self.project_dir.split("/")[-1]
        return str(self.project_id)[:8]

    @property
    def log_file_path(self) -> str | None:
        """Path to the factory run log file."""
        if self.project_dir:
            return f"{self.project_dir}/artifacts/reports/factory-run.log"
        return None
