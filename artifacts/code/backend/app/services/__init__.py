"""Service container — dependency injection for all services."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.config import Settings
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()


class ServiceContainer:
    """
    Central container for all application services.

    Provides eager initialization and clean shutdown.
    v2.0 extends v1.0 with: provider registry, model routing/scanning,
    health monitoring, backup, cost tracking, self-research, orchestration,
    Clink routing, and template rendering.
    """

    def __init__(
        self,
        settings: "Settings",
        session_factory: "AsyncSessionFactory",
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

        # ── v1.0 services ─────────────────────────────────────
        from app.services.user_service import UserService
        from app.services.project_service import ProjectService
        from app.services.factory_runner import FactoryRunner
        from app.services.run_monitor import RunMonitor
        from app.services.transcription import TranscriptionService
        from app.services.translation import TranslationService
        from app.services.docker_service import DockerService
        from app.services.system_service import SystemService
        from app.services.analytics_service import AnalyticsService
        from app.services.notification import NotificationService
        from app.services.settings_service import SettingsService

        self.settings_service = SettingsService(session_factory=session_factory)
        self.user_service = UserService(session_factory=session_factory)
        self.project_service = ProjectService(session_factory=session_factory)
        self.notification = NotificationService(settings=settings)
        self.analytics_service = AnalyticsService(session_factory=session_factory)
        self.transcription = TranscriptionService(settings=settings)
        self.translation = TranslationService(settings=settings)
        self.docker_service = DockerService()
        self.system_service = SystemService()
        self.factory_runner = FactoryRunner(
            settings=settings,
            session_factory=session_factory,
        )
        self.run_monitor = RunMonitor(
            settings=settings,
            session_factory=session_factory,
            notification=self.notification,
            analytics_service=self.analytics_service,
            factory_runner=self.factory_runner,
        )

        # ── v2.0 services ─────────────────────────────────────
        from app.services.provider_registry import ProviderRegistryService
        from app.services.model_router import ModelRouter
        from app.services.model_scanner import ModelScanner
        from app.services.health_monitor import HealthMonitor
        from app.services.backup_service import BackupService
        from app.services.cost_tracker import CostTracker
        from app.services.self_researcher import SelfResearcher
        from app.services.factory_orchestrator import FactoryOrchestrator
        from app.services.clink_router import ClinkRouter
        from app.services.template_service import TemplateService
        from app.providers.registry import ProviderRegistry
        from app.providers.rate_limiter import ProviderRateLimiter

        # Provider infrastructure
        self.provider_registry = ProviderRegistryService(settings=settings)
        self._raw_registry = ProviderRegistry(settings=settings)
        self._rate_limiter = ProviderRateLimiter()

        # Model routing and scanning (use raw ProviderRegistry as they expect it)
        self.model_router = ModelRouter(
            registry=self._raw_registry,
            rate_limiter=self._rate_limiter,
        )
        self.model_scanner = ModelScanner(registry=self._raw_registry)

        # Health monitoring (uses ProviderRegistry + Settings)
        self.health_monitor = HealthMonitor(
            settings=settings,
            registry=self._raw_registry,
        )

        # Backup and cost tracking (use session_factory)
        self.backup_service = BackupService(session_factory=session_factory)
        self.cost_tracker = CostTracker(session_factory=session_factory)

        # Self-research and orchestration (use session_factory + model_router)
        self.self_researcher = SelfResearcher(
            session_factory=session_factory,
            model_router=self.model_router,
        )
        self.factory_orchestrator = FactoryOrchestrator(
            session_factory=session_factory,
            model_router=self.model_router,
        )

        # Clink (no-arg) and template service (needs settings)
        self.clink_router = ClinkRouter()
        self.template_service = TemplateService(settings=settings)

        logger.info("service_container_initialized")

    async def close(self) -> None:
        """Shutdown all services that need cleanup."""
        logger.info("shutting_down_services")

        shutdown_pairs = [
            ("run_monitor", self.run_monitor, "stop_all"),
            ("docker_service", self.docker_service, "close"),
            ("transcription", self.transcription, "close"),
            ("translation", self.translation, "close"),
        ]

        for svc_name, svc, method_name in shutdown_pairs:
            try:
                fn = getattr(svc, method_name, None)
                if fn is not None:
                    await fn()
            except Exception:
                logger.exception("service_shutdown_failed", service=svc_name)

        logger.info("services_shutdown_complete")
