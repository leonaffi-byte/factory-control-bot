"""System health monitoring and service management."""

from __future__ import annotations

import asyncio
import time

import psutil
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class SystemHealth(BaseModel):
    """System health metrics."""
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int


class ServiceStatus(BaseModel):
    """systemd service status."""
    name: str
    active: bool
    status: str  # active, inactive, failed
    uptime: str | None = None


class DiskAlert(BaseModel):
    """Disk space alert."""
    percent_used: float
    level: str  # "warning" (>80%) or "critical" (>90%)


# Allowed services for management
ALLOWED_SERVICES = frozenset({"docker", "nginx", "postgresql", "tailscaled", "fail2ban"})


class SystemService:
    """System health metrics and service management."""

    async def get_health(self) -> SystemHealth:
        """Get current system health metrics."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_health_sync)

    def _get_health_sync(self) -> SystemHealth:
        """Synchronous health metric collection."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # Memory
        mem = psutil.virtual_memory()
        memory_percent = mem.percent
        memory_used_gb = mem.used / (1024 ** 3)
        memory_total_gb = mem.total / (1024 ** 3)

        # Disk
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)

        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)

        return SystemHealth(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_gb=round(memory_used_gb, 1),
            memory_total_gb=round(memory_total_gb, 1),
            disk_percent=disk_percent,
            disk_used_gb=round(disk_used_gb, 1),
            disk_total_gb=round(disk_total_gb, 1),
            uptime_seconds=uptime_seconds,
        )

    async def get_service_status(self, service_name: str) -> ServiceStatus:
        """Get systemd service status."""
        if service_name not in ALLOWED_SERVICES:
            raise ValueError(f"Service '{service_name}' not in allowed list")

        # Check if active
        is_active = await self._run_systemctl("is-active", service_name)
        active = is_active.strip() == "active"

        # Get status text
        status_text = is_active.strip()

        # Get uptime if active
        uptime = None
        if active:
            show_output = await self._run_systemctl(
                "show", service_name, "--property=ActiveEnterTimestamp"
            )
            if "ActiveEnterTimestamp=" in show_output:
                timestamp_str = show_output.split("=", 1)[1].strip()
                if timestamp_str:
                    uptime = timestamp_str

        return ServiceStatus(
            name=service_name,
            active=active,
            status=status_text,
            uptime=uptime,
        )

    async def restart_service(self, service_name: str) -> bool:
        """Restart a systemd service. Returns success."""
        if service_name not in ALLOWED_SERVICES:
            raise ValueError(f"Service '{service_name}' not in allowed list")

        proc = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "restart", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        success = proc.returncode == 0
        if not success:
            logger.error(
                "service_restart_failed",
                service=service_name,
                error=stderr.decode() if stderr else "",
            )
        else:
            logger.info("service_restarted", service=service_name)

        return success

    async def get_service_logs(self, service_name: str, lines: int = 50) -> str:
        """Get last N lines of service journal logs."""
        if service_name not in ALLOWED_SERVICES:
            raise ValueError(f"Service '{service_name}' not in allowed list")

        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", service_name, "-n", str(lines), "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return f"Failed to get logs: {stderr.decode() if stderr else 'unknown error'}"

        return stdout.decode() if stdout else "No logs available."

    async def check_disk_space(self) -> DiskAlert | None:
        """Check disk space, return alert if >80% used."""
        health = await self.get_health()

        if health.disk_percent > 90:
            return DiskAlert(percent_used=health.disk_percent, level="critical")
        elif health.disk_percent > 80:
            return DiskAlert(percent_used=health.disk_percent, level="warning")

        return None

    async def _run_systemctl(self, *args: str) -> str:
        """Run a systemctl command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            "systemctl", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode() if stdout else ""
