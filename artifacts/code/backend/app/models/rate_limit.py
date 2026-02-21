"""RateLimit model — per-provider per-model rate limit tracking."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RateLimit(TimestampMixin, Base):
    """Tracks current rate limit counters for a (provider, model) pair."""

    __tablename__ = "rate_limits"

    __table_args__ = (
        PrimaryKeyConstraint("provider_name", "model_name", name="pk_rate_limits"),
    )

    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rpd_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tpm_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rpm_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rpd_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<RateLimit provider={self.provider_name!r} model={self.model_name!r}"
            f" rpm_remaining={self.rpm_remaining} rpd_remaining={self.rpd_remaining}>"
        )
