"""RunSupervisor + RunMonitor — log file watching and event processing."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.models.factory_run import FactoryRun
from app.models.factory_event import FactoryEvent
from app.utils.log_parser import parse_factory_marker, FactoryMarker

if TYPE_CHECKING:
    from app.config import Settings
    from app.database.session import AsyncSessionFactory
    from app.services.notification import NotificationService
    from app.services.analytics_service import AnalyticsService
    from app.services.factory_runner import FactoryRunner

logger = structlog.get_logger()


class RunMonitor:
    """
    Supervises all active factory run monitors.

    Each monitored run gets its own asyncio task that watches the log file
    for [FACTORY:...] markers and dispatches events/notifications.
    """

    def __init__(
        self,
        settings: "Settings",
        session_factory: "AsyncSessionFactory",
        notification: "NotificationService",
        analytics_service: "AnalyticsService",
        factory_runner: "FactoryRunner",
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._notification = notification
        self._analytics = analytics_service
        self._factory_runner = factory_runner
        self._monitors: dict[UUID, asyncio.Task] = {}
        self._poll_interval = settings.log_poll_interval
        self._max_monitors = settings.max_concurrent_monitors
        self._idle_timeout = settings.idle_timeout_minutes * 60  # convert to seconds

    async def attach(self, run: FactoryRun) -> None:
        """Start monitoring a factory run."""
        if run.id in self._monitors:
            logger.debug("monitor_already_attached", run_id=str(run.id))
            return

        if len(self._monitors) >= self._max_monitors:
            logger.warning("max_monitors_reached", max=self._max_monitors)
            return

        task = asyncio.create_task(
            self._monitor_loop(run),
            name=f"monitor-{run.id}",
        )
        self._monitors[run.id] = task
        logger.info("monitor_attached", run_id=str(run.id), engine=run.engine)

    async def detach(self, run_id: UUID) -> None:
        """Stop monitoring a factory run."""
        task = self._monitors.pop(run_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("monitor_detached", run_id=str(run_id))

    async def stop_all(self) -> None:
        """Stop all monitors gracefully."""
        for run_id in list(self._monitors.keys()):
            await self.detach(run_id)
        logger.info("all_monitors_stopped")

    @property
    def active_count(self) -> int:
        return len(self._monitors)

    async def _monitor_loop(self, run: FactoryRun) -> None:
        """Main monitoring loop for a single factory run."""
        log_file = run.log_file_path
        if not log_file:
            logger.error("no_log_file_path", run_id=str(run.id))
            return

        offset = run.last_log_offset or 0
        last_activity = time.time()
        last_offset_flush = time.time()
        consecutive_empty = 0

        logger.info(
            "monitor_loop_started",
            run_id=str(run.id),
            log_file=log_file,
            offset=offset,
        )

        try:
            while True:
                await asyncio.sleep(self._poll_interval)

                # Check if tmux session is still alive
                if consecutive_empty > 0 and consecutive_empty % 20 == 0:
                    sessions = await self._factory_runner.list_tmux_sessions()
                    if run.tmux_session and run.tmux_session not in sessions:
                        logger.warning(
                            "tmux_session_died",
                            run_id=str(run.id),
                            session=run.tmux_session,
                        )
                        await self._factory_runner.mark_run_failed(
                            run.id, reason="tmux session terminated unexpectedly"
                        )
                        await self._notification.send_error(
                            run, "Factory process terminated unexpectedly."
                        )
                        break

                # Check idle timeout
                if time.time() - last_activity > self._idle_timeout:
                    logger.warning("run_idle_timeout", run_id=str(run.id))
                    await self._notification.send_warning(
                        run, f"No log activity for {self._settings.idle_timeout_minutes} minutes."
                    )
                    last_activity = time.time()  # Reset to avoid spamming

                # Read log file
                try:
                    if not os.path.exists(log_file):
                        consecutive_empty += 1
                        continue

                    file_size = os.path.getsize(log_file)

                    # Handle file rotation
                    if file_size < offset:
                        logger.info("log_file_rotated", run_id=str(run.id))
                        offset = 0

                    if file_size <= offset:
                        consecutive_empty += 1
                        continue

                    # Read new content
                    with open(log_file, "r", encoding="utf-8") as f:
                        f.seek(offset)
                        new_content = f.read()
                        offset = f.tell()

                    if not new_content:
                        consecutive_empty += 1
                        continue

                    consecutive_empty = 0
                    last_activity = time.time()

                    # Process lines
                    lines = new_content.split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        marker = parse_factory_marker(line)
                        if marker:
                            await self._handle_marker(run, marker)

                    # Flush offset to DB periodically (every 30 seconds)
                    if time.time() - last_offset_flush > 30:
                        await self._factory_runner.update_log_offset(run.id, offset)
                        last_offset_flush = time.time()

                except Exception as e:
                    logger.error(
                        "log_read_error",
                        run_id=str(run.id),
                        error=str(e),
                    )
                    await asyncio.sleep(self._poll_interval)

        except asyncio.CancelledError:
            logger.info("monitor_cancelled", run_id=str(run.id))
        except Exception:
            logger.exception("monitor_loop_error", run_id=str(run.id))
        finally:
            # Final offset flush
            try:
                await self._factory_runner.update_log_offset(run.id, offset)
            except Exception:
                pass
            self._monitors.pop(run.id, None)

    async def _handle_marker(self, run: FactoryRun, marker: FactoryMarker) -> None:
        """Handle a parsed factory log marker."""
        logger.info(
            "factory_marker",
            run_id=str(run.id),
            marker_type=marker.marker_type,
            phase=marker.phase,
            data=marker.data,
        )

        # Record event in DB
        async with self._session_factory() as session:
            event = FactoryEvent(
                run_id=run.id,
                event_type=marker.marker_type,
                phase=marker.phase,
                data=marker.data,
            )

            if marker.marker_type == "cost":
                event.cost_amount = marker.data.get("amount")
                event.cost_provider = marker.data.get("provider")

            session.add(event)

        # Dispatch based on marker type
        if marker.marker_type == "phase_start":
            phase = marker.phase or 0
            await self._factory_runner.update_run_phase(run.id, phase)
            await self._notification.send_phase_start(run, phase)

        elif marker.marker_type == "phase_end":
            phase = marker.phase or 0
            score = marker.data.get("score", 0)
            await self._notification.send_phase_end(run, phase, score)

        elif marker.marker_type == "clarify":
            await self._notification.send_clarification(run, marker.data)

        elif marker.marker_type == "error":
            message = marker.data.get("message", "Unknown error")
            await self._notification.send_error(run, message)

        elif marker.marker_type == "cost":
            amount = marker.data.get("amount", 0)
            provider = marker.data.get("provider", "unknown")
            await self._factory_runner.update_run_cost(run.id, amount, provider)
            await self._analytics.record_cost_entry(
                run_id=run.id,
                project_id=run.project_id,
                amount=amount,
                provider=provider,
                engine=run.engine,
                phase=run.current_phase,
            )

        elif marker.marker_type == "complete":
            await self._factory_runner.mark_run_completed(run.id)
            await self._notification.send_completion(run, marker.data)
            # Detach monitor
            await self.detach(run.id)
