"""System health and service management handlers."""

from __future__ import annotations

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer
from app.utils.formatting import truncate_message

logger = structlog.get_logger()

MONITORED_SERVICES = ["docker", "nginx", "postgresql", "tailscaled", "fail2ban"]


async def system_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /system command — show system health."""
    await _show_system_health(update, context)


async def _show_system_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display system health metrics and service status overview."""
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        health = await services.system_service.get_health()
    except Exception as e:
        text = f"<b>System Health</b>\n\nFailed to retrieve metrics: {e}"
        if update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(text)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
        return

    # Progress bar helper
    def bar(percent: float) -> str:
        filled = int(percent / 10)
        return "\u2588" * filled + "\u2591" * (10 - filled)

    # Uptime formatting
    uptime_h = health.uptime_seconds // 3600
    uptime_d = uptime_h // 24
    uptime_rem = uptime_h % 24

    text = (
        "<b>System Health</b>\n\n"
        f"<b>CPU:</b> {bar(health.cpu_percent)} {health.cpu_percent:.1f}%\n"
        f"<b>RAM:</b> {bar(health.memory_percent)} {health.memory_used_gb:.1f}/{health.memory_total_gb:.1f} GB "
        f"({health.memory_percent:.1f}%)\n"
        f"<b>Disk:</b> {bar(health.disk_percent)} {health.disk_used_gb:.1f}/{health.disk_total_gb:.1f} GB "
        f"({health.disk_percent:.1f}%)\n"
        f"<b>Uptime:</b> {uptime_d}d {uptime_rem}h\n"
    )

    # Disk warning
    if health.disk_percent > 90:
        text += "\n\u26a0\ufe0f <b>CRITICAL:</b> Disk usage above 90%!"
    elif health.disk_percent > 80:
        text += "\n\u26a0\ufe0f WARNING: Disk usage above 80%"

    buttons = []
    for svc_name in MONITORED_SERVICES:
        buttons.append([
            InlineKeyboardButton(
                f"\U0001f50d {svc_name}",
                callback_data=f"system:service:{svc_name}",
            )
        ])

    buttons.append([InlineKeyboardButton("\U0001f504 Refresh", callback_data="system:refresh")])
    buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="menu:back")])

    keyboard = InlineKeyboardMarkup(buttons)

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def system_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle system-level action callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("system:")

    if data == "refresh":
        await _show_system_health(update, context)
        return

    if data.startswith("service:"):
        service_name = data.removeprefix("service:")
        await _show_service_detail(update, context, service_name)


async def _show_service_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_name: str
) -> None:
    """Show detail for a specific systemd service."""
    query = update.callback_query
    services: ServiceContainer = context.application.bot_data["services"]

    if service_name not in MONITORED_SERVICES:
        if query:
            await query.edit_message_text(f"Unknown service: {service_name}")
        return

    try:
        status = await services.system_service.get_service_status(service_name)
    except Exception as e:
        if query:
            await query.edit_message_text(f"Failed to get status: {e}")
        return

    emoji = "\U0001f7e2" if status.active else "\U0001f534"
    text = (
        f"{emoji} <b>Service: {status.name}</b>\n\n"
        f"Status: {status.status}\n"
    )
    if status.uptime:
        text += f"Uptime: {status.uptime}\n"

    user_id = update.effective_user.id if update.effective_user else 0
    is_admin = await services.user_service.is_admin(user_id)

    buttons = [
        [InlineKeyboardButton("\U0001f4dc Logs", callback_data=f"service:logs:{service_name}")],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(
                "\U0001f504 Restart",
                callback_data=f"service:restart:{service_name}",
            ),
        ])
    buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="system:refresh")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def service_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle service-level actions (logs, restart)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data.removeprefix("service:")
    parts = data.split(":", 1)
    if len(parts) < 2:
        await query.answer("Invalid action.")
        return

    action, service_name = parts
    services: ServiceContainer = context.application.bot_data["services"]

    if service_name not in MONITORED_SERVICES:
        await query.answer("Unknown service.", show_alert=True)
        return

    if action == "logs":
        await query.answer()
        try:
            logs = await services.system_service.get_service_logs(service_name, lines=50)
            text = (
                f"<b>Logs: {service_name}</b>\n\n"
                f"<pre>{truncate_message(logs, max_len=3500)}</pre>"
            )
        except Exception as e:
            text = f"Failed to get logs: {e}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"service:logs:{service_name}")],
            [InlineKeyboardButton("\u00ab Back", callback_data=f"system:service:{service_name}")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard)

    elif action == "restart":
        user_id = update.effective_user.id if update.effective_user else 0
        if not await services.user_service.is_admin(user_id):
            await query.answer("Admin only action.", show_alert=True)
            return

        await query.answer(f"Restarting {service_name}...")
        try:
            success = await services.system_service.restart_service(service_name)
            if success:
                text = f"Service <b>{service_name}</b> restarted successfully."
            else:
                text = f"Failed to restart <b>{service_name}</b>."
        except Exception as e:
            text = f"Restart failed: {e}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u00ab Back", callback_data=f"system:service:{service_name}")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
