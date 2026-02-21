"""Deployment model — tracks deployed instances of projects."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Deployment(TimestampMixin, Base):
    """Tracks a deployed instance of a factory-built project."""

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    deploy_type: Mapped[str] = mapped_column(String(30), nullable=False)
    deploy_target: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Status: pending, deploying, healthy, unhealthy, stopped
    url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    container_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    # Relationships
    project = relationship("Project", back_populates="deployments", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Deployment project={self.project_id} status={self.status}>"
