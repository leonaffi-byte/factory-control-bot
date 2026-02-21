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
from app.models.orchestration_state import OrchestrationState
from app.models.model_provider import ModelProvider
from app.models.api_usage import ApiUsageLog
from app.models.model_benchmark import ModelBenchmark
from app.models.self_research import SelfResearchReport, SelfResearchSuggestion
from app.models.scheduled_task import ScheduledTask
from app.models.backup import Backup
from app.models.rate_limit import RateLimit

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
    "OrchestrationState",
    "ModelProvider",
    "ApiUsageLog",
    "ModelBenchmark",
    "SelfResearchReport",
    "SelfResearchSuggestion",
    "ScheduledTask",
    "Backup",
    "RateLimit",
]
