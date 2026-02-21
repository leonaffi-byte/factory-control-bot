"""Health monitoring handler — /health."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.views.health_report import format_health_report
from app.services import ServiceContainer

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


async def health_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /health command — show health report."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    logger.info("health_command", user_id=user_id)

    try:
        report = await services.health_monitor.get_report()
        text = format_health_report(report)
    except Exception as e:
        logger.error("health_report_failed", error=str(e), user_id=user_id)
        await update.effective_message.reply_text(
            f"<b>Health Check Failed</b>\n\n<code>{e}</code>",
            parse_mode="HTML",
        )
        return

    overall_status = getattr(report, "overall_status", "unknown")
    status_label = {
        "ok": "All systems operational",
        "warning": "Some issues detected",
        "critical": "Critical issues — action required",
        "unknown": "Status unknown",
    }.get(overall_status, overall_status)

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Refresh", callback_data="health:refresh"),
                InlineKeyboardButton("Details", callback_data="health:details"),
            ],
            [InlineKeyboardButton("Back", callback_data="menu:back")],
        ]),
    )


async def health_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle health:* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("health:")

    services: ServiceContainer = context.application.bot_data["services"]

    if data == "refresh":
        try:
            report = await services.health_monitor.get_report()
            text = format_health_report(report)
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Refresh", callback_data="health:refresh"),
                        InlineKeyboardButton("Details", callback_data="health:details"),
                    ],
                    [InlineKeyboardButton("Back", callback_data="menu:back")],
                ]),
            )
        except Exception as e:
            logger.error("health_refresh_failed", error=str(e))
            await query.edit_message_text(f"Health check failed: {e}")
        return

    if data == "details":
        try:
            report = await services.health_monitor.get_report()
            checks = getattr(report, "checks", [])

            lines = ["<b>Health Details</b>\n"]
            for check in checks:
                name = getattr(check, "name", "unknown")
                status = getattr(check, "status", "unknown")
                message = getattr(check, "message", "")
                value = getattr(check, "value", None)

                STATUS_TAG = {
                    "ok": "OK",
                    "warning": "WARN",
                    "critical": "CRIT",
                    "unknown": "?",
                }
                tag = STATUS_TAG.get(status, status.upper())
                line = f"[{tag}] <b>{name}</b>"
                if value is not None:
                    line += f": {value}"
                if message:
                    line += f"\n      {message}"
                lines.append(line)

            text = "\n".join(lines)
            if len(text) > 4096:
                text = text[:4093] + "..."

            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back", callback_data="health:refresh")],
                ]),
            )
        except Exception as e:
            logger.error("health_details_failed", error=str(e))
            await query.edit_message_text(f"Failed to load details: {e}")
        return

    logger.warning("health_callback_unknown_action", data=data)
