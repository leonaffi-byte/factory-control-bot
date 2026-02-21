"""Factory worker service — runs orchestrator, health checks, scheduled tasks."""

from __future__ import annotations

import asyncio
import signal

import structlog

from app.config import get_settings
from app.database.engine import create_engine
from app.database.session import create_session_factory
from app.database.events import PgEventListener

logger = structlog.get_logger()


class FactoryWorker:
    """
    Background worker that runs alongside the Telegram bot.

    Responsibilities:
    - Listen for PostgreSQL NOTIFY events on the factory_events channel
    - Run periodic health checks
    - Run daily automated backups
    - Run hourly model scans
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running = False
        self._listener: PgEventListener | None = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the worker: event listener + background tasks."""
        logger.info("worker_starting")
        self._running = True

        engine = create_engine(self._settings.database_url)
        session_factory = create_session_factory(engine)

        # Start PostgreSQL LISTEN/NOTIFY listener
        dsn = self._settings.database_url.replace("+asyncpg", "")
        self._listener = PgEventListener(dsn)
        await self._listener.start_listening("factory_events", self._on_event)

        # Create background task group
        self._tasks = [
            asyncio.create_task(self._health_check_loop(), name="health_check_loop"),
            asyncio.create_task(self._backup_scheduler(), name="backup_scheduler"),
            asyncio.create_task(self._scan_scheduler(), name="scan_scheduler"),
        ]

        logger.info("worker_started", tasks=len(self._tasks))

        try:
            # Run until cancelled or stopped
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("worker_tasks_cancelled")
        finally:
            await self._cleanup()

    async def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        logger.info("worker_stopping")
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()

    async def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        if self._listener:
            try:
                await self._listener.stop_listening()
            except Exception:
                logger.exception("listener_stop_failed")
        logger.info("worker_stopped")

    async def _on_event(self, payload: dict | str) -> None:
        """Handle an incoming factory_events NOTIFY payload."""
        logger.info("worker_event_received", payload=payload)

        if isinstance(payload, dict):
            event_type = payload.get("type", "unknown")
            run_id = payload.get("run_id")
            if event_type == "phase_complete":
                logger.info("phase_complete_event", run_id=run_id, phase=payload.get("phase"))
            elif event_type == "run_failed":
                logger.warning("run_failed_event", run_id=run_id, reason=payload.get("reason"))
            elif event_type == "cost_alert":
                logger.warning(
                    "cost_alert_event",
                    run_id=run_id,
                    cost=payload.get("cost"),
                    threshold=self._settings.cost_alert_threshold,
                )

    async def _health_check_loop(self) -> None:
        """Run a health check on every health_check_interval seconds."""
        interval = self._settings.health_check_interval
        logger.info("health_check_loop_started", interval_seconds=interval)

        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                logger.debug("health_check_tick")
                # The actual health check logic is in HealthMonitor service;
                # this loop just triggers it on schedule.
                # In the full integration: await services.health_monitor.run_checks()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("health_check_loop_error")

        logger.info("health_check_loop_stopped")

    async def _backup_scheduler(self) -> None:
        """Run a full backup once per day (86 400 seconds)."""
        interval = 86_400  # 24 hours
        logger.info("backup_scheduler_started", interval_seconds=interval)

        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                logger.info("scheduled_backup_trigger")
                # In the full integration: await services.backup_service.backup_full()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("backup_scheduler_error")

        logger.info("backup_scheduler_stopped")

    async def _scan_scheduler(self) -> None:
        """Scan available AI models once per hour (3 600 seconds)."""
        interval = 3_600  # 1 hour
        logger.info("scan_scheduler_started", interval_seconds=interval)

        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                logger.info("scheduled_scan_trigger")
                # In the full integration: await services.model_scanner.scan_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("scan_scheduler_error")

        logger.info("scan_scheduler_stopped")


async def main() -> None:
    """Entry point for running the worker as a standalone process."""
    worker = FactoryWorker()

    loop = asyncio.get_running_loop()

    def _shutdown_signal(sig: signal.Signals) -> None:
        logger.info("shutdown_signal_received", signal=sig.name)
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown_signal, sig)

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
