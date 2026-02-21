"""Import all models so Alembic can discover them."""

from app.models.base import Base, TimestampMixin
from app.models.user import User
from app.models.project import Project, ProjectStatus, Engine, DeployType, DeployTarget
from app.models.factory_run import FactoryRun, RunStatus
from app.models.factory_event import FactoryEvent
from app.models.deployment import Deployment
from app.models.node import Node
from app.models.setting import Setting
from app.models.analytics import Analytics

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "Project",
    "ProjectStatus",
    "Engine",
    "DeployType",
    "DeployTarget",
    "FactoryRun",
    "RunStatus",
    "FactoryEvent",
    "Deployment",
    "Node",
    "Setting",
    "Analytics",
]
