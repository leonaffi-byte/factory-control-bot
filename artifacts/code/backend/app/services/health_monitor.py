"""Health monitor service — system-wide health checks and alerting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.config import Settings
    from app.providers.registry import ProviderRegistry

logger = structlog.get_logger()

# ── DTOs ────────────────────────────────────────────────────────────────────


@dataclass
class HealthMetric:
    name: str
    status: str              # "healthy" | "warning" | "critical" | "unknown"
    value: str
    details: str | None = None


@dataclass
class Alert:
    alert_type: str          # "disk" | "memory" | "provider" | "database" | "runs"
    severity: str            # "warning" | "critical"
    message: str
    metric_name: str
    metric_value: str
    threshold: str
    remediation: str | None = None


@dataclass
class HealthReport:
    timestamp: datetime
    overall_status: str      # "healthy" | "warning" | "critical" | "unknown"
    metrics: list[HealthMetric] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)


# ── Status helpers ───────────────────────────────────────────────────────────

def _overall_status(metrics: list[HealthMetric]) -> str:
    statuses = {m.status for m in metrics}
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    if all(m.status == "healthy" for m in metrics):
        return "healthy"
    return "unknown"


class HealthMonitor:
    """
    Aggregates health checks across disk, database, providers, memory, and active runs.

    Produces a HealthReport with per-metric details and actionable Alerts.
    """

    def __init__(
        self,
        settings: "Settings",
        registry: "ProviderRegistry",
    ) -> None:
        self._settings = settings
        self._registry = registry

    async def check_health(self) -> HealthReport:
        """
        Run all health checks concurrently and return a combined HealthReport.

        Checks performed:
        - Disk usage (psutil)
        - Database connectivity
        - Provider health
        - Memory usage (psutil)
        - Active run count
        """
        disk_metric, db_metric, memory_metric, provider_metrics, runs_metric = (
            await asyncio.gather(
                self.check_disk(),
                self.check_database(),
                self._check_memory(),
                self.check_providers(),
                self._check_active_runs(),
                return_exceptions=True,
            )
        )

        metrics: list[HealthMetric] = []
        alerts: list[Alert] = []

        for item in [disk_metric, db_metric, memory_metric, runs_metric]:
            if isinstance(item, HealthMetric):
                metrics.append(item)
            elif isinstance(item, Exception):
                metrics.append(
                    HealthMetric(
                        name="unknown",
                        status="unknown",
                        value="check_failed",
                        details=str(item),
                    )
                )

        if isinstance(provider_metrics, list):
            metrics.extend(provider_metrics)
        elif isinstance(provider_metrics, Exception):
            metrics.append(
                HealthMetric(
                    name="providers",
                    status="unknown",
                    value="check_failed",
                    details=str(provider_metrics),
                )
            )

        # Build alerts from any non-healthy metric
        for m in metrics:
            if m.status in ("warning", "critical"):
                alert = self._metric_to_alert(m)
                if alert:
                    alerts.append(alert)

        report = HealthReport(
            timestamp=datetime.now(timezone.utc),
            overall_status=_overall_status(metrics),
            metrics=metrics,
            alerts=alerts,
        )

        logger.info(
            "health_check_complete",
            overall=report.overall_status,
            metrics=len(metrics),
            alerts=len(alerts),
        )
        return report

    async def check_disk(self) -> HealthMetric:
        """
        Check available disk space using psutil.

        Returns a HealthMetric with the current usage percentage.
        """
        try:
            import psutil  # type: ignore[import-untyped]

            usage = await asyncio.to_thread(psutil.disk_usage, "/")
            percent = usage.percent
            used_gb = usage.used / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            value = f"{percent:.1f}%"

            if percent >= self._settings.disk_critical_percent:
                status = "critical"
            elif percent >= self._settings.disk_warning_percent:
                status = "warning"
            else:
                status = "healthy"

            return HealthMetric(
                name="disk",
                status=status,
                value=value,
                details=f"{used_gb:.1f} GB / {total_gb:.1f} GB used",
            )
        except ImportError:
            return HealthMetric(
                name="disk",
                status="unknown",
                value="N/A",
                details="psutil not installed",
            )
        except Exception as exc:
            return HealthMetric(
                name="disk",
                status="unknown",
                value="error",
                details=str(exc),
            )

    async def check_database(self) -> HealthMetric:
        """
        Check database connectivity by importing and using the engine.

        Returns a HealthMetric reflecting DB reachability.
        """
        try:
            from app.database.engine import get_engine
            from sqlalchemy import text

            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

            return HealthMetric(
                name="database",
                status="healthy",
                value="connected",
                details="PostgreSQL connection successful",
            )
        except Exception as exc:
            logger.error("db_health_check_failed", error=str(exc))
            return HealthMetric(
                name="database",
                status="critical",
                value="disconnected",
                details=str(exc),
            )

    async def check_providers(self) -> list[HealthMetric]:
        """
        Run health checks on all registered providers.

        Returns one HealthMetric per provider.
        """
        try:
            health_map = await self._registry.check_health_all()
        except Exception as exc:
            logger.error("provider_health_check_failed", error=str(exc))
            return [
                HealthMetric(
                    name="providers",
                    status="unknown",
                    value="error",
                    details=str(exc),
                )
            ]

        metrics: list[HealthMetric] = []
        for provider_name, status in health_map.items():
            if status.is_healthy:
                health_status = "healthy"
                value = f"{status.latency_ms}ms"
            else:
                health_status = "warning"
                value = "unreachable"

            metrics.append(
                HealthMetric(
                    name=f"provider:{provider_name}",
                    status=health_status,
                    value=value,
                    details=status.error,
                )
            )

        return metrics

    # ── Private checks ───────────────────────────────────────────────────────

    async def _check_memory(self) -> HealthMetric:
        """Check system memory usage via psutil."""
        try:
            import psutil  # type: ignore[import-untyped]

            mem = await asyncio.to_thread(psutil.virtual_memory)
            percent = mem.percent
            available_gb = mem.available / (1024 ** 3)

            if percent >= 90:
                status = "critical"
            elif percent >= 80:
                status = "warning"
            else:
                status = "healthy"

            return HealthMetric(
                name="memory",
                status=status,
                value=f"{percent:.1f}%",
                details=f"{available_gb:.1f} GB available",
            )
        except ImportError:
            return HealthMetric(
                name="memory",
                status="unknown",
                value="N/A",
                details="psutil not installed",
            )
        except Exception as exc:
            return HealthMetric(
                name="memory",
                status="unknown",
                value="error",
                details=str(exc),
            )

    async def _check_active_runs(self) -> HealthMetric:
        """
        Check how many factory runs are currently active.

        Uses a direct database query; returns an informational metric.
        """
        try:
            from app.database.engine import get_engine
            from sqlalchemy import text

            engine = get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM factory_runs "
                        "WHERE status IN ('running', 'queued')"
                    )
                )
                count: int = result.scalar() or 0

            max_concurrent = self._settings.max_concurrent_monitors
            if count >= max_concurrent:
                status = "warning"
            else:
                status = "healthy"

            return HealthMetric(
                name="active_runs",
                status=status,
                value=str(count),
                details=f"{count}/{max_concurrent} concurrent runs",
            )
        except Exception as exc:
            return HealthMetric(
                name="active_runs",
                status="unknown",
                value="error",
                details=str(exc),
            )

    @staticmethod
    def _metric_to_alert(metric: HealthMetric) -> Alert | None:
        """Convert a non-healthy HealthMetric into an Alert with remediation hints."""
        remediation_map: dict[str, str] = {
            "disk": "Free disk space: remove old backups, clear Docker images (docker system prune).",
            "memory": "Restart idle services, or scale up the host memory.",
            "database": "Check PostgreSQL is running: systemctl status postgresql",
        }

        if metric.status not in ("warning", "critical"):
            return None

        base_name = metric.name.split(":")[0]
        return Alert(
            alert_type=base_name,
            severity=metric.status,
            message=f"{metric.name} is {metric.status}: {metric.value}",
            metric_name=metric.name,
            metric_value=metric.value,
            threshold=metric.details or "",
            remediation=remediation_map.get(base_name),
        )
