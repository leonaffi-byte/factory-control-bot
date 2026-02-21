"""SelfResearchReport and SelfResearchSuggestion models — autonomous self-improvement tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SelfResearchReport(TimestampMixin, Base):
    """Represents a self-research run that analyses the factory codebase for improvements."""

    __tablename__ = "self_research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_by_user: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    suggestions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pr_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    suggestions = relationship(
        "SelfResearchSuggestion",
        back_populates="report",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<SelfResearchReport id={self.id} triggered_by={self.triggered_by!r}"
            f" suggestions={self.suggestions_count}>"
        )


class SelfResearchSuggestion(TimestampMixin, Base):
    """A single improvement suggestion produced by a self-research report."""

    __tablename__ = "self_research_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("self_research_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    changes_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    report = relationship("SelfResearchReport", back_populates="suggestions")

    def __repr__(self) -> str:
        return (
            f"<SelfResearchSuggestion id={self.id} category={self.category!r}"
            f" status={self.status!r} risk={self.risk_level!r}>"
        )
