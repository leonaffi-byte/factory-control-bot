"""Node model — for future multi-node support."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Node(TimestampMixin, Base):
    """Represents a compute node (VPS) in the factory cluster. Future multi-node."""

    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Status: active, inactive, maintenance
    cpu_cores: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    memory_gb: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), default=None)
    disk_gb: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), default=None)
    capabilities: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # e.g., {"docker": true, "gpu": false, "engines": ["claude", "gemini"]}
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(default=None)

    def __repr__(self) -> str:
        return f"<Node name={self.name} status={self.status}>"
