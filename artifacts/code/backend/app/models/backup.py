"""Backup model — records of database and project backup operations."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Backup(TimestampMixin, Base):
    """Records a single backup operation including file path, checksum, and retention policy."""

    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    includes_db: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    includes_projects: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    includes_config: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<Backup id={self.id} type={self.backup_type!r} status={self.status!r}"
            f" size={self.file_size_bytes}>"
        )
