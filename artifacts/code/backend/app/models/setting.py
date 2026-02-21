"""Setting model — key-value settings storage."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Setting(TimestampMixin, Base):
    """Key-value settings store for global and per-project configuration."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)
    # Value is stored as JSONB for flexibility. Scalar values wrapped as {"v": value}
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, default=None)

    def __repr__(self) -> str:
        return f"<Setting key={self.key}>"

    def get_value(self):
        """Unwrap the JSONB value."""
        if self.value is None:
            return None
        return self.value.get("v", self.value)

    @staticmethod
    def wrap_value(val) -> dict:
        """Wrap a scalar value for JSONB storage."""
        if isinstance(val, dict):
            return val
        return {"v": val}
