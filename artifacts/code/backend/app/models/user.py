"""User model — Telegram whitelist users."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """Represents an authorized Telegram user in the whitelist."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(
        String(20), default="user", server_default=text("'user'")
    )
    last_active: Mapped[Optional[datetime]] = mapped_column(default=None)

    # Relationships
    projects = relationship("Project", back_populates="creator", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} role={self.role}>"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
