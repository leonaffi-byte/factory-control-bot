"""Model scanner handlers — /scan, /providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.keyboards.scan_results import get_scan_results_keyboard
from app.bot.views.scan_report import format_scan_report
from app.services import ServiceContainer

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


async def scan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /scan command — trigger model scan and show results."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not await services.user_service.is_admin(user_id):
        await update.effective_message.reply_text(
            "Only admins can trigger model scans."
        )
        return

    # Send "scanning" message first
    msg = await update.effective_message.reply_text(
        "<b>Model Scanner</b>\n\nScanning available providers and models...",
        parse_mode="HTML",
    )

    try:
        result = await services.model_scanner.scan_all()
        text = format_scan_report(result)
        has_suggestion = bool(result.routing_suggestion)
        keyboard = get_scan_results_keyboard(has_suggestion=has_suggestion)

        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        logger.info(
            "model_scan_completed",
            providers_found=len(result.providers),
            user_id=user_id,
        )
    except Exception as e:
        logger.error("model_scan_failed", error=str(e), user_id=user_id)
        await msg.edit_text(
            f"<b>Scan Failed</b>\n\n<code>{e}</code>",
            parse_mode="HTML",
        )


async def providers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /providers command — show provider status table."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]

    try:
        providers = await services.provider_registry.list_providers()
    except Exception as e:
        logger.error("provider_list_failed", error=str(e))
        await update.effective_message.reply_text(
            f"<b>Provider Status</b>\n\nFailed to load providers: <code>{e}</code>",
            parse_mode="HTML",
        )
        return

    if not providers:
        await update.effective_message.reply_text(
            "<b>Provider Status</b>\n\nNo providers registered. Run /scan first.",
            parse_mode="HTML",
        )
        return

    STATUS_EMOJI = {
        "ok": "OK",
        "error": "ERR",
        "unknown": "?",
        "degraded": "WARN",
    }

    lines = ["<b>Provider Status</b>\n", "<code>"]
    lines.append(f"{'Provider':<20} {'Status':<8} {'Models':<6} {'Latency'}")
    lines.append("-" * 46)

    for p in providers:
        tag = STATUS_EMOJI.get(getattr(p, "status", "unknown"), "?")
        model_count = len(getattr(p, "models", []))
        latency = getattr(p, "latency_ms", None)
        latency_str = f"{latency}ms" if latency is not None else "N/A"
        name = getattr(p, "name", str(p))[:20]
        lines.append(f"{name:<20} {tag:<8} {model_count:<6} {latency_str}")

    lines.append("</code>")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Scan Now", callback_data="scan:refresh"),
                InlineKeyboardButton("Details", callback_data="scan:details"),
            ],
            [InlineKeyboardButton("Back", callback_data="menu:back")],
        ]),
    )


async def scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle scan:* inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("scan:")

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    if data == "accept":
        # Accept the routing suggestion from the last scan
        try:
            result = await services.model_scanner.get_last_result()
            if not result or not result.routing_suggestion:
                await query.edit_message_text(
                    "No routing suggestion available. Run /scan first.",
                )
                return

            await services.model_router.apply_suggestion(result.routing_suggestion)
            await query.edit_message_text(
                "<b>Routing suggestion applied.</b>\n\n"
                f"Mode: <code>{result.routing_suggestion.mode}</code>\n"
                "New provider routing is now active.",
                parse_mode="HTML",
            )
            logger.info(
                "routing_suggestion_accepted",
                user_id=user_id,
                mode=result.routing_suggestion.mode,
            )
        except Exception as e:
            logger.error("routing_suggestion_apply_failed", error=str(e))
            await query.edit_message_text(f"Failed to apply suggestion: {e}")
        return

    if data == "refresh":
        await query.edit_message_text(
            "<b>Model Scanner</b>\n\nScanning...",
            parse_mode="HTML",
        )
        try:
            result = await services.model_scanner.scan_all()
            text = format_scan_report(result)
            has_suggestion = bool(result.routing_suggestion)
            keyboard = get_scan_results_keyboard(has_suggestion=has_suggestion)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error("model_scan_refresh_failed", error=str(e))
            await query.edit_message_text(f"Scan failed: {e}")
        return

    if data == "details":
        try:
            result = await services.model_scanner.get_last_result()
            if not result:
                await query.edit_message_text("No scan results yet. Run /scan first.")
                return

            lines = ["<b>Scan Details</b>\n"]
            for p in result.providers:
                name = getattr(p, "name", "unknown")
                models = getattr(p, "models", [])
                lines.append(f"<b>{name}</b>: {len(models)} models")
                for m in models[:5]:
                    model_id = getattr(m, "id", str(m))
                    grade = getattr(m, "grade", "?")
                    lines.append(f"  • {model_id} [{grade}]")
                if len(models) > 5:
                    lines.append(f"  ... and {len(models) - 5} more")

            text = "\n".join(lines)
            if len(text) > 4096:
                text = text[:4093] + "..."

            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back", callback_data="scan:refresh")],
                ]),
            )
        except Exception as e:
            logger.error("scan_details_failed", error=str(e))
            await query.edit_message_text(f"Failed to load details: {e}")
        return

    logger.warning("scan_callback_unknown_action", data=data)
    await query.edit_message_text("Unknown action.")
