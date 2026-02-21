"""Start and main menu handlers."""

from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards.main_menu import get_main_menu_keyboard
from app.services import ServiceContainer

logger = structlog.get_logger()

WELCOME_TEXT = (
    "<b>Black Box Factory v2</b>\n\n"
    "Welcome to the Factory Control Bot.\n"
    "Use the menu below to manage projects, monitor runs, "
    "and control your VPS infrastructure."
)

MENU_TEXT = "<b>Black Box Factory v2</b>\n\nSelect an option:"


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — show welcome message and main menu."""
    if not update.effective_message:
        return

    services: ServiceContainer = context.application.bot_data["services"]
    user = update.effective_user
    if user:
        logger.info("start_command", telegram_id=user.id, username=user.username)

    keyboard = get_main_menu_keyboard()
    await update.effective_message.reply_text(
        WELCOME_TEXT,
        reply_markup=keyboard,
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command — show main menu."""
    if not update.effective_message:
        return

    keyboard = get_main_menu_keyboard()
    await update.effective_message.reply_text(
        MENU_TEXT,
        reply_markup=keyboard,
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    action = query.data.removeprefix("menu:")

    services: ServiceContainer = context.application.bot_data["services"]

    if action == "new_project":
        # Trigger the /new command flow
        await query.message.reply_text(
            "Starting new project wizard...\n"
            "Use /new to begin the project creation flow."
        )

    elif action == "projects":
        from app.bot.handlers.projects import _show_project_list
        await _show_project_list(update, context)

    elif action == "analytics":
        from app.bot.handlers.analytics import _show_analytics_menu
        await _show_analytics_menu(update, context)

    elif action == "docker":
        from app.bot.handlers.docker import _show_container_list
        await _show_container_list(update, context)

    elif action == "system":
        from app.bot.handlers.system import _show_system_health
        await _show_system_health(update, context)

    elif action == "settings":
        from app.bot.handlers.settings import _show_settings_menu
        await _show_settings_menu(update, context)

    elif action == "help":
        from app.bot.handlers.help import _show_help
        await _show_help(update, context)

    elif action == "back":
        keyboard = get_main_menu_keyboard()
        await query.edit_message_text(MENU_TEXT, reply_markup=keyboard)
