"""PTB Application builder and handler registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine

import structlog
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)

from app.bot.handlers.start import start_handler, menu_handler, main_menu_callback
from app.bot.handlers.projects import (
    projects_handler,
    project_detail_callback,
    project_action_callback,
)
from app.bot.handlers.docker import (
    docker_handler,
    docker_container_callback,
    docker_action_callback,
)
from app.bot.handlers.system import (
    system_handler,
    system_action_callback,
    service_action_callback,
)
from app.bot.handlers.analytics import analytics_handler, analytics_callback
from app.bot.handlers.settings import settings_handler, settings_callback
from app.bot.handlers.admin import admin_handler, admin_callback
from app.bot.handlers.help import help_handler
from app.bot.conversations.new_project import get_new_project_conversation
from app.bot.middleware import AuthMiddleware
from app.database.engine import create_engine
from app.database.session import AsyncSessionFactory
from app.database.persistence import PostgreSQLPersistence
from app.services import ServiceContainer

if TYPE_CHECKING:
    from app.config import Settings
    from telegram.ext import Application as TGApplication

logger = structlog.get_logger()


def build_application(
    settings: "Settings",
    post_init: Callable[["TGApplication"], Coroutine[Any, Any, None]] | None = None,
    post_shutdown: Callable[["TGApplication"], Coroutine[Any, Any, None]] | None = None,
) -> "TGApplication":
    """Build and configure the PTB Application with all handlers."""

    # Create database engine and session factory
    engine = create_engine(settings)
    session_factory = AsyncSessionFactory(engine)

    # Create service container
    services = ServiceContainer(settings=settings, session_factory=session_factory)

    # Build persistence
    persistence = PostgreSQLPersistence(session_factory=session_factory)

    # Build application
    defaults = Defaults(parse_mode="HTML")

    builder = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .defaults(defaults)
        .persistence(persistence)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )

    application = builder.build()

    # Store references in bot_data for access from handlers
    application.bot_data["settings"] = settings
    application.bot_data["services"] = services
    application.bot_data["session_factory"] = session_factory

    # Register handlers
    _register_handlers(application, services)

    logger.info("application_built")
    return application


def _register_handlers(application: "TGApplication", services: ServiceContainer) -> None:
    """Register all command handlers, conversation handlers, and callbacks."""

    # ── Group -1: Auth middleware (runs before all handlers) ──
    auth = AuthMiddleware(services.user_service)
    application.add_handler(auth.get_handler(), group=-1)

    # ── Group 0: Conversation handlers (must come before simple commands) ──
    new_project_conv = get_new_project_conversation()
    application.add_handler(new_project_conv, group=0)

    # ── Group 0: Command handlers ──
    application.add_handler(CommandHandler("start", start_handler), group=0)
    application.add_handler(CommandHandler("menu", menu_handler), group=0)
    application.add_handler(CommandHandler("projects", projects_handler), group=0)
    application.add_handler(CommandHandler("docker", docker_handler), group=0)
    application.add_handler(CommandHandler("system", system_handler), group=0)
    application.add_handler(CommandHandler("analytics", analytics_handler), group=0)
    application.add_handler(CommandHandler("settings", settings_handler), group=0)
    application.add_handler(CommandHandler("admin", admin_handler), group=0)
    application.add_handler(CommandHandler("help", help_handler), group=0)

    # ── Group 0: Callback query handlers ──
    application.add_handler(
        CallbackQueryHandler(main_menu_callback, pattern=r"^menu:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(project_detail_callback, pattern=r"^project:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(project_action_callback, pattern=r"^proj_action:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(docker_container_callback, pattern=r"^docker:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(docker_action_callback, pattern=r"^dock_action:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(system_action_callback, pattern=r"^system:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(service_action_callback, pattern=r"^service:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(analytics_callback, pattern=r"^analytics:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(settings_callback, pattern=r"^settings:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(admin_callback, pattern=r"^admin:"),
        group=0,
    )

    # ── Global error handler ──
    application.add_error_handler(_error_handler)

    logger.info("handlers_registered")


async def _error_handler(update: object, context) -> None:
    """Global error handler for all unhandled exceptions."""
    logger.error(
        "unhandled_exception",
        error=str(context.error),
        exc_info=context.error,
    )

    from telegram import Update

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An unexpected error occurred. Please try again.",
            )
        except Exception:
            logger.exception("error_handler_send_failed")
