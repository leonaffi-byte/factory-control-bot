"""Settings management handlers — global and per-project settings."""

from __future__ import annotations

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer

logger = structlog.get_logger()

# Settings that can be edited via Telegram
EDITABLE_SETTINGS = {
    "default_engine": {
        "label": "Default Engine",
        "type": "choice",
        "choices": ["claude", "gemini", "opencode", "aider"],
    },
    "voice_provider": {
        "label": "Voice Provider",
        "type": "choice",
        "choices": ["auto", "groq", "openai"],
    },
    "translation_model": {
        "label": "Translation Model",
        "type": "text",
    },
    "requirements_model": {
        "label": "Requirements Model",
        "type": "text",
    },
    "quality_gate_threshold": {
        "label": "Quality Gate Threshold",
        "type": "int",
        "min": 80,
        "max": 100,
    },
    "max_quality_retries": {
        "label": "Max Quality Retries",
        "type": "int",
        "min": 1,
        "max": 10,
    },
    "max_fix_cycles": {
        "label": "Max Fix Cycles",
        "type": "int",
        "min": 1,
        "max": 15,
    },
    "cost_alert_threshold": {
        "label": "Cost Alert Threshold ($)",
        "type": "float",
        "min": 1.0,
        "max": 500.0,
    },
    "log_poll_interval": {
        "label": "Log Poll Interval (sec)",
        "type": "int",
        "min": 1,
        "max": 10,
    },
    "domain_name": {
        "label": "Domain Name",
        "type": "text",
    },
    "ssl_email": {
        "label": "SSL Email",
        "type": "text",
    },
}


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command — show settings menu."""
    await _show_settings_menu(update, context)


async def _show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display settings menu."""
    services: ServiceContainer = context.application.bot_data["services"]

    try:
        all_settings = await services.settings_service.get_all()
    except Exception as e:
        text = f"<b>Settings</b>\n\nFailed to load settings: {e}"
        if update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(text)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
        return

    text = "<b>Settings</b>\n\n"
    for key, meta in EDITABLE_SETTINGS.items():
        current = all_settings.get(key, "not set")
        text += f"<b>{meta['label']}:</b> <code>{current}</code>\n"

    # OpenRouter usage
    try:
        current_count, daily_limit = await services.settings_service.get_openrouter_usage()
        text += f"\n<b>OpenRouter Usage:</b> {current_count}/{daily_limit} today"
    except Exception:
        pass

    buttons = []
    row = []
    for i, (key, meta) in enumerate(EDITABLE_SETTINGS.items()):
        row.append(
            InlineKeyboardButton(
                meta["label"][:20],
                callback_data=f"settings:edit:{key}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="menu:back")])
    keyboard = InlineKeyboardMarkup(buttons)

    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle settings callback queries."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data.removeprefix("settings:")

    services: ServiceContainer = context.application.bot_data["services"]
    user_id = update.effective_user.id if update.effective_user else 0

    # Only admin can edit settings
    if not await services.user_service.is_admin(user_id):
        await query.edit_message_text(
            "Only admins can modify settings.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u00ab Back", callback_data="menu:settings")],
            ]),
        )
        return

    if data.startswith("edit:"):
        key = data.removeprefix("edit:")
        meta = EDITABLE_SETTINGS.get(key)
        if not meta:
            return

        if meta["type"] == "choice":
            # Show choice buttons
            buttons = []
            for choice in meta["choices"]:
                buttons.append([
                    InlineKeyboardButton(
                        choice,
                        callback_data=f"settings:set:{key}:{choice}",
                    )
                ])
            buttons.append([InlineKeyboardButton("\u00ab Back", callback_data="settings:menu")])
            await query.edit_message_text(
                f"Select value for <b>{meta['label']}</b>:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        else:
            # For text/int/float, prompt user to type value
            if context.user_data is not None:
                context.user_data["awaiting_setting"] = key
            await query.edit_message_text(
                f"Send the new value for <b>{meta['label']}</b>:\n"
                f"(Type: {meta['type']})",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data="settings:menu")],
                ]),
            )

    elif data.startswith("set:"):
        parts = data.removeprefix("set:").split(":", 1)
        if len(parts) < 2:
            return
        key, value = parts
        try:
            await services.settings_service.set(key, value, updated_by=user_id)
            await query.edit_message_text(
                f"Setting <b>{key}</b> updated to <code>{value}</code>.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u00ab Back to Settings", callback_data="settings:menu")],
                ]),
            )
        except Exception as e:
            await query.edit_message_text(f"Failed to update setting: {e}")

    elif data == "menu":
        await _show_settings_menu(update, context)
