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

    Provides lazy initialization and clean shutdown.
    """

    def __init__(
        self,
        settings: "Settings",
        session_factory: "AsyncSessionFactory",
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

        # Eagerly initialize all services
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

        logger.info("service_container_initialized")

    async def close(self) -> None:
        """Shutdown all services that need cleanup."""
        logger.info("shutting_down_services")

        try:
            await self.run_monitor.stop_all()
        except Exception:
            logger.exception("run_monitor_shutdown_failed")

        try:
            await self.docker_service.close()
        except Exception:
            logger.exception("docker_service_shutdown_failed")

        try:
            await self.transcription.close()
        except Exception:
            logger.exception("transcription_shutdown_failed")

        try:
            await self.translation.close()
        except Exception:
            logger.exception("translation_shutdown_failed")

        logger.info("services_shutdown_complete")
