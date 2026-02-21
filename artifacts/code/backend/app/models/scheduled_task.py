"""ScheduledTask model — cron-style recurring task registry."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ScheduledTask(TimestampMixin, Base):
    """Represents a recurring task with a cron expression and run tracking."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cron_expression: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScheduledTask type={self.task_type!r} cron={self.cron_expression!r}"
            f" enabled={self.is_enabled}>"
        )
