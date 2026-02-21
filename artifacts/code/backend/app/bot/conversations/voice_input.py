"""Voice/text input sub-flow logic — reusable across conversation states."""

from __future__ import annotations

from typing import Any

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services import ServiceContainer
from app.utils.formatting import truncate_message

logger = structlog.get_logger()

# Keys in context.user_data for voice input state
SEGMENTS_KEY = "voice_segments"
EDITING_KEY = "voice_editing"


def get_voice_input_keyboard() -> InlineKeyboardMarkup:
    """Return the standard keyboard for voice/text input flow."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Done", callback_data="req:done"),
            InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="req:edit"),
        ],
        [InlineKeyboardButton("\U0001f5d1 Delete Last", callback_data="req:delete_last")],
    ])


def get_segments(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    """Get current voice/text segments from user_data."""
    if context.user_data is None:
        return []
    wizard = context.user_data.get("wizard", {})
    return wizard.get(SEGMENTS_KEY, [])


def set_segments(context: ContextTypes.DEFAULT_TYPE, segments: list[str]) -> None:
    """Set voice/text segments in user_data."""
    if context.user_data is None:
        return
    wizard = context.user_data.setdefault("wizard", {})
    wizard[SEGMENTS_KEY] = segments


def add_segment(context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    """Add a segment and return the new count."""
    segments = get_segments(context)
    segments.append(text)
    set_segments(context, segments)
    return len(segments)


def remove_last_segment(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Remove and return the last segment, or None if empty."""
    segments = get_segments(context)
    if not segments:
        return None
    removed = segments.pop()
    set_segments(context, segments)
    return removed


def get_concatenated(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Concatenate all segments into a single text."""
    return "\n\n".join(get_segments(context))


async def transcribe_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> str | None:
    """
    Transcribe a voice message from the update.

    Returns the transcribed text, or None on failure.
    Sends status messages to the user.
    """
    if not update.effective_message or not update.effective_message.voice:
        return None

    services: ServiceContainer = context.application.bot_data["services"]
    voice = update.effective_message.voice

    status_msg = await update.effective_message.reply_text("Transcribing...")

    try:
        voice_file = await voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        result = await services.transcription.transcribe(
            bytes(audio_bytes),
            f"voice_{update.update_id}.ogg",
        )

        # Update status message with result
        await status_msg.edit_text(
            f"Transcribed ({result.provider}, {result.language}, "
            f"{result.duration_ms}ms):\n\n<i>{result.text}</i>"
        )

        return result.text

    except Exception as e:
        logger.error("voice_transcription_failed", error=str(e))
        await status_msg.edit_text(
            f"Transcription failed: {e}\nPlease type your input instead."
        )
        return None


def format_segments_review(segments: list[str]) -> str:
    """Format segments for review display."""
    if not segments:
        return "No segments recorded."

    lines = ["<b>Current input segments:</b>\n"]
    total_len = 0
    for i, seg in enumerate(segments, 1):
        preview = seg[:200] + ("..." if len(seg) > 200 else "")
        lines.append(f"<b>Segment {i}:</b> {preview}")
        total_len += len(seg)

    lines.append(f"\nTotal: {len(segments)} segments, ~{total_len} chars")
    return "\n".join(lines)
