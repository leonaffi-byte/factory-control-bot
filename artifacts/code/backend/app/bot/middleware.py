"""Authentication whitelist middleware — silently drops unauthorized updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from telegram import Update
from telegram.ext import BaseHandler, MessageHandler, CallbackQueryHandler, filters

if TYPE_CHECKING:
    from app.services.user_service import UserService

logger = structlog.get_logger()


class AuthMiddleware:
    """
    Middleware that checks every incoming update against the user whitelist.

    Runs in handler group -1 (before all other handlers).
    Unauthorized users are silently ignored — no response is sent.
    """

    def __init__(self, user_service: "UserService") -> None:
        self.user_service = user_service

    def get_handler(self) -> BaseHandler:
        """Return a TypeHandler-like handler for auth checking."""
        return _AuthHandler(self.user_service)


class _AuthHandler(BaseHandler):
    """Custom handler that intercepts all updates for auth checking."""

    def __init__(self, user_service: "UserService") -> None:
        super().__init__(callback=self._check_auth)
        self.user_service = user_service

    def check_update(self, update: object) -> bool | object:
        """Check every update type — always returns True to intercept."""
        if isinstance(update, Update):
            return True
        return False

    async def _check_auth(self, update: Update, context) -> None:
        """
        Check if the user is authorized.

        If not authorized, raise ApplicationHandlerStop to prevent further processing.
        This results in silent rejection — the unauthorized user receives no response.
        """
        from telegram.ext import ApplicationHandlerStop

        user = update.effective_user
        if user is None:
            # System updates without a user (channel posts, etc.) — allow
            return

        telegram_id = user.id

        if not await self.user_service.is_authorized(telegram_id):
            logger.debug(
                "unauthorized_access_attempt",
                telegram_id=telegram_id,
                username=user.username,
            )
            raise ApplicationHandlerStop()

        # Update last_active timestamp (fire-and-forget)
        try:
            await self.user_service.touch_last_active(telegram_id)
        except Exception:
            pass  # Non-critical — don't block the request
