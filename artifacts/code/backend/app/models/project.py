"""Project model with status enums."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    DEPLOYED = "deployed"


class Engine(str, enum.Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENCODE = "opencode"
    AIDER = "aider"


class DeployType(str, enum.Enum):
    TELEGRAM_BOT = "telegram_bot"
    WEB_APP = "web_app"
    API_SERVICE = "api_service"
    OTHER = "other"


class DeployTarget(str, enum.Enum):
    LOCAL_DOCKER = "local_docker"
    REMOTE_SSH = "remote_ssh"


class Project(TimestampMixin, Base):
    """Represents a software factory project."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(20), default=ProjectStatus.DRAFT.value, index=True
    )
    engines: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), default=list
    )
    requirements: Mapped[str] = mapped_column(Text, default="")
    settings_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    deploy_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    total_cost: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.0
    )
    github_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )

    # Relationships
    creator = relationship("User", back_populates="projects", lazy="selectin")
    runs = relationship(
        "FactoryRun", back_populates="project", lazy="selectin",
        cascade="all, delete-orphan",
    )
    deployments = relationship(
        "Deployment", back_populates="project", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project name={self.name} status={self.status}>"

    @property
    def project_name(self) -> str:
        """Alias for name, used in formatting."""
        return self.name
