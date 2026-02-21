"""Application entry point — startup sequence for the Factory Control Bot."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from app.config import Settings, get_settings
from app.bot.application import build_application
from app.database.engine import create_engine, dispose_engine
from app.database.session import AsyncSessionFactory
from app.services import ServiceContainer

if TYPE_CHECKING:
    from telegram.ext import Application


def configure_logging(log_level: str) -> None:
    """Configure structlog with stdlib logging integration."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def run_migrations(settings: Settings) -> None:
    """Run Alembic migrations to bring the database up to date."""
    logger = structlog.get_logger()
    logger.info("running_alembic_migrations")

    from alembic.config import Config
    from alembic import command
    import os

    alembic_cfg = Config()
    # Determine alembic directory relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)

    # Run upgrade in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
    logger.info("alembic_migrations_complete")


async def verify_database(session_factory: AsyncSessionFactory) -> None:
    """Verify database connectivity."""
    logger = structlog.get_logger()
    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    logger.info("database_connection_verified")


async def reconcile_orphaned_runs(services: ServiceContainer) -> None:
    """On startup, check for runs marked 'running' whose tmux sessions are gone."""
    logger = structlog.get_logger()
    active_runs = await services.factory_runner.get_active_runs()
    tmux_sessions = await services.factory_runner.list_tmux_sessions()
    tmux_session_names = set(tmux_sessions)

    orphaned = 0
    for run in active_runs:
        session_name = f"{run.project_name}-{run.engine}"
        if session_name not in tmux_session_names:
            logger.warning(
                "orphaned_run_detected",
                run_id=str(run.id),
                project=run.project_name,
                engine=run.engine,
            )
            await services.factory_runner.mark_run_failed(
                run.id, reason="Bot restarted; tmux session not found"
            )
            await services.notification.notify_admins(
                f"Orphaned run detected: {run.project_name} ({run.engine}). "
                f"Marked as failed."
            )
            orphaned += 1
        else:
            # Re-attach monitor
            await services.run_monitor.attach(run)
            logger.info(
                "reattached_run_monitor",
                run_id=str(run.id),
                project=run.project_name,
            )

    logger.info("reconciliation_complete", orphaned=orphaned, reattached=len(active_runs) - orphaned)


async def post_init(application: "Application") -> None:
    """PTB post_init callback — runs after the application is built but before polling."""
    logger = structlog.get_logger()
    settings: Settings = application.bot_data["settings"]
    services: ServiceContainer = application.bot_data["services"]

    # 1. Run Alembic migrations
    try:
        await run_migrations(settings)
    except Exception:
        logger.exception("migration_failed")
        # Continue anyway — tables may already exist

    # 2. Verify database connectivity
    await verify_database(application.bot_data["session_factory"])

    # 3. Ensure admin user exists
    await services.user_service.ensure_admin(settings.admin_telegram_id)

    # 4. Reconcile orphaned runs
    await reconcile_orphaned_runs(services)

    # 5. Schedule periodic jobs
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            health_check_job,
            interval=settings.health_check_interval,
            first=30,  # first check 30s after startup
            name="health_check",
        )
        job_queue.run_repeating(
            disk_check_job,
            interval=settings.health_check_interval,
            first=60,
            name="disk_check",
        )

    logger.info("post_init_complete")


async def health_check_job(context) -> None:
    """Periodic health check — runs every 5 minutes."""
    logger = structlog.get_logger()
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        health = await services.system_service.get_health()

        if health.disk_percent > 90:
            await services.notification.notify_admins(
                f"CRITICAL: Disk usage at {health.disk_percent:.1f}%"
            )
        elif health.disk_percent > 80:
            await services.notification.notify_admins(
                f"WARNING: Disk usage at {health.disk_percent:.1f}%"
            )

        if health.memory_percent > 90:
            await services.notification.notify_admins(
                f"WARNING: Memory usage at {health.memory_percent:.1f}%"
            )
    except Exception:
        logger.exception("health_check_failed")


async def disk_check_job(context) -> None:
    """Separate disk check that may refuse new projects."""
    logger = structlog.get_logger()
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        alert = await services.system_service.check_disk_space()
        if alert and alert.level == "critical":
            await services.settings_service.set(
                "disk_critical", True, updated_by=0
            )
        else:
            await services.settings_service.set(
                "disk_critical", False, updated_by=0
            )
    except Exception:
        logger.exception("disk_check_failed")


async def post_shutdown(application: "Application") -> None:
    """PTB post_shutdown callback — cleanup resources."""
    logger = structlog.get_logger()
    logger.info("shutting_down")

    services: ServiceContainer = application.bot_data.get("services")
    if services:
        await services.close()

    await dispose_engine()
    logger.info("shutdown_complete")


def main() -> None:
    """Main entry point."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = structlog.get_logger()
    logger.info(
        "starting_factory_control_bot",
        log_level=settings.log_level,
        factory_root=str(settings.factory_root_dir),
    )

    # Build the PTB application
    application = build_application(settings, post_init=post_init, post_shutdown=post_shutdown)

    # Handle graceful shutdown signals
    loop = asyncio.new_event_loop()

    # Run the bot with polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "callback_query",
            "edited_message",
        ],
    )


if __name__ == "__main__":
    main()
