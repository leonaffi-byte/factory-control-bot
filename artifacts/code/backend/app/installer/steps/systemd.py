"""Systemd service installation step."""

from __future__ import annotations

import asyncio
import os

import structlog

logger = structlog.get_logger()


BOT_SERVICE_TEMPLATE = """\
[Unit]
Description=Factory Control Bot (Telegram Bot)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User={user}
WorkingDirectory={working_dir}
EnvironmentFile={working_dir}/.env
ExecStart={working_dir}/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-bot

[Install]
WantedBy=multi-user.target
"""

WORKER_SERVICE_TEMPLATE = """\
[Unit]
Description=Factory Worker Service
After=network.target postgresql.service factory-bot.service
Wants=postgresql.service

[Service]
Type=simple
User={user}
WorkingDirectory={working_dir}
EnvironmentFile={working_dir}/.env
ExecStart={working_dir}/.venv/bin/python -m app.worker
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=factory-worker

[Install]
WantedBy=multi-user.target
"""

BOT_SERVICE_NAME = "factory-bot.service"
WORKER_SERVICE_NAME = "factory-worker.service"
SYSTEMD_DIR = "/etc/systemd/system"


async def install_services(user: str, working_dir: str) -> bool:
    """
    Write factory-bot.service and factory-worker.service to /etc/systemd/system.

    Requires sudo/root privileges.

    Args:
        user: Linux user to run the services as.
        working_dir: Absolute path to the project root directory.

    Returns:
        True if both service files were written successfully.
    """
    bot_content = BOT_SERVICE_TEMPLATE.format(user=user, working_dir=working_dir)
    worker_content = WORKER_SERVICE_TEMPLATE.format(user=user, working_dir=working_dir)

    services = {
        os.path.join(SYSTEMD_DIR, BOT_SERVICE_NAME): bot_content,
        os.path.join(SYSTEMD_DIR, WORKER_SERVICE_NAME): worker_content,
    }

    for path, content in services.items():
        try:
            # Write via tee (so sudo can be used if needed via external shell)
            await asyncio.to_thread(_write_file, path, content)
            logger.info("service_file_written", path=path)
        except OSError as e:
            logger.error("service_file_write_failed", path=path, error=str(e))
            return False

    # Reload systemd daemon
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "daemon-reload",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "daemon_reload_failed",
                stderr=stderr.decode(errors="replace")[:300],
            )
        else:
            logger.info("systemd_daemon_reloaded")
    except OSError as e:
        logger.warning("daemon_reload_error", error=str(e))

    return True


async def enable_services() -> bool:
    """
    Enable factory-bot and factory-worker services to start on boot.

    Returns:
        True if both services were enabled successfully.
    """
    services = [BOT_SERVICE_NAME, WORKER_SERVICE_NAME]
    for svc in services:
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "enable", svc,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    "service_enable_failed",
                    service=svc,
                    stderr=stderr.decode(errors="replace")[:300],
                )
                return False
            logger.info("service_enabled", service=svc)
        except OSError as e:
            logger.error("service_enable_error", service=svc, error=str(e))
            return False
    return True


async def check_service_status(service_name: str) -> str:
    """
    Return the active state of a systemd service.

    Args:
        service_name: e.g. "factory-bot.service"

    Returns:
        One of: "active", "inactive", "failed", "activating", "unknown"
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() or "unknown"
    except OSError as e:
        logger.warning("check_service_status_error", service=service_name, error=str(e))
        return "unknown"


def _write_file(path: str, content: str) -> None:
    """Write content to path (sync helper for asyncio.to_thread)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
