"""Telegram notification service with throttling and rate limiting."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.config import Settings
    from app.models.factory_run import FactoryRun

logger = structlog.get_logger()

# Phase names for display
PHASE_NAMES = {
    0: "Setup",
    1: "Requirements",
    2: "Brainstorm",
    3: "Architecture",
    4: "Implementation",
    5: "Review",
    6: "Fix Cycle",
    7: "Documentation",
}


class MessageSession:
    """Tracks the state of a live-updating message."""

    def __init__(self, chat_id: int, message_id: int) -> None:
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_edit_time: float = 0
        self.last_text_hash: str = ""
        self.min_edit_interval: float = 3.0

    def should_edit(self, new_text: str) -> bool:
        """Check if the message should be edited (rate limit + change check)."""
        now = time.time()
        if now - self.last_edit_time < self.min_edit_interval:
            return False

        text_hash = hashlib.md5(new_text.encode()).hexdigest()
        if text_hash == self.last_text_hash:
            return False

        return True

    def mark_edited(self, text: str) -> None:
        """Mark that the message was just edited."""
        self.last_edit_time = time.time()
        self.last_text_hash = hashlib.md5(text.encode()).hexdigest()


class NotificationService:
    """
    Sends Telegram notifications for factory events.

    Features:
    - Per-chat rate limiting (respect Telegram API limits)
    - Message deduplication
    - Live message sessions for real-time monitoring
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._bot = None  # Set during application initialization
        self._admin_chat_id = settings.admin_telegram_id
        self._sessions: dict[str, MessageSession] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._last_send_time: dict[int, float] = {}
        self._min_send_interval: float = 1.0  # 1 second between messages per chat

    def set_bot(self, bot) -> None:
        """Set the bot instance for sending messages."""
        self._bot = bot

    async def notify_admins(self, text: str) -> None:
        """Send a message to the admin user."""
        if self._bot and self._admin_chat_id:
            await self._send_message(self._admin_chat_id, text)

    async def send_phase_start(self, run: "FactoryRun", phase: int) -> None:
        """Notify about a phase starting."""
        phase_name = PHASE_NAMES.get(phase, f"Phase {phase}")
        text = (
            f"<b>Phase {phase} Started</b>\n\n"
            f"Project: {run.project_name} ({run.engine})\n"
            f"Phase: {phase_name}"
        )
        await self._notify_run_owner(run, text)

    async def send_phase_end(self, run: "FactoryRun", phase: int, score: int) -> None:
        """Notify about a phase ending with quality score."""
        phase_name = PHASE_NAMES.get(phase, f"Phase {phase}")
        emoji = "\u2705" if score >= 97 else "\u26a0\ufe0f" if score >= 90 else "\u274c"

        text = (
            f"{emoji} <b>Phase {phase} Complete</b>\n\n"
            f"Project: {run.project_name} ({run.engine})\n"
            f"Phase: {phase_name}\n"
            f"Score: {score}/100"
        )
        await self._notify_run_owner(run, text)

    async def send_clarification(self, run: "FactoryRun", data: dict) -> None:
        """Send a clarification question to the user."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        question = data.get("question", "Clarification needed")
        q_type = data.get("type", "open")
        options = data.get("options", [])
        context_text = data.get("context", "")

        text = (
            f"<b>Clarification Needed</b>\n\n"
            f"Project: {run.project_name} ({run.engine})\n"
            f"Phase: {run.current_phase}\n\n"
            f"<b>Question:</b> {question}"
        )
        if context_text:
            text += f"\n\n<i>{context_text}</i>"

        if q_type == "multiple_choice" and options:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(opt, callback_data=f"clarify:{run.id}:{i}:{opt}")]
                for i, opt in enumerate(options)
            ])
        else:
            keyboard = None
            text += "\n\nReply to this message with your answer."

        await self._notify_run_owner(run, text, reply_markup=keyboard)

    async def send_error(self, run: "FactoryRun", message: str) -> None:
        """Send an error notification."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        text = (
            f"\u274c <b>Factory Error</b>\n\n"
            f"Project: {run.project_name} ({run.engine})\n"
            f"Phase: {run.current_phase}\n"
            f"Error: {message}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("View Logs", callback_data=f"proj_action:logs:{run.project_id}"),
                InlineKeyboardButton("Stop Factory", callback_data=f"proj_action:stop:{run.project_id}"),
            ],
        ])

        await self._notify_run_owner(run, text, reply_markup=keyboard)

    async def send_warning(self, run: "FactoryRun", message: str) -> None:
        """Send a warning notification."""
        text = (
            f"\u26a0\ufe0f <b>Warning</b>\n\n"
            f"Project: {run.project_name} ({run.engine})\n"
            f"{message}"
        )
        await self._notify_run_owner(run, text)

    async def send_completion(self, run: "FactoryRun", data: dict) -> None:
        """Send a completion summary."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        duration = data.get("duration_minutes", 0)
        total_cost = data.get("total_cost", 0)
        phases = data.get("phases", {})
        test_results = data.get("test_results", {})
        github_url = data.get("github_url", "")

        text = (
            f"\u2705 <b>Factory Complete!</b>\n\n"
            f"<b>Project:</b> {run.project_name}\n"
            f"<b>Engine:</b> {run.engine}\n"
            f"<b>Duration:</b> {duration:.0f} min\n"
            f"<b>Cost:</b> ${total_cost:.2f}\n\n"
        )

        if phases:
            text += "<b>Quality Scores:</b>\n"
            for phase_num, score in sorted(phases.items()):
                text += f"  Phase {phase_num}: {score}/100\n"
            text += "\n"

        if test_results:
            passed = test_results.get("passed", 0)
            failed = test_results.get("failed", 0)
            skipped = test_results.get("skipped", 0)
            text += f"<b>Tests:</b> {passed} passed, {failed} failed, {skipped} skipped\n"

        if github_url:
            text += f"\n<b>GitHub:</b> {github_url}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("View Details", callback_data=f"project:{run.project_id}"),
                InlineKeyboardButton("Analytics", callback_data=f"analytics:project:{run.project_id}"),
            ],
        ])

        await self._notify_run_owner(run, text, reply_markup=keyboard)

    async def _notify_run_owner(
        self, run: "FactoryRun", text: str, reply_markup=None
    ) -> None:
        """Send notification to the run owner (or admin as fallback)."""
        chat_id = run.created_by or self._admin_chat_id
        await self._send_message(chat_id, text, reply_markup=reply_markup)

    async def _send_message(
        self, chat_id: int, text: str, reply_markup=None
    ) -> None:
        """Send a message with rate limiting."""
        if not self._bot:
            logger.warning("bot_not_set_for_notifications")
            return

        # Rate limiting
        now = time.time()
        last_time = self._last_send_time.get(chat_id, 0)
        if now - last_time < self._min_send_interval:
            await asyncio.sleep(self._min_send_interval - (now - last_time))

        try:
            from telegram.error import RetryAfter

            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            self._last_send_time[chat_id] = time.time()

        except RetryAfter as e:
            logger.warning("telegram_rate_limited", retry_after=e.retry_after)
            await asyncio.sleep(e.retry_after)
            # Retry once
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except Exception:
                logger.exception("notification_retry_failed")

        except Exception:
            logger.exception("notification_send_failed", chat_id=chat_id)
