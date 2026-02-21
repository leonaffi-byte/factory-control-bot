"""Base view with design language — shared helpers for all Telegram views."""

from __future__ import annotations


class TelegramView:
    """
    Base class providing the shared design language for all Telegram message views.

    All view modules should use these helpers to ensure consistent formatting.
    """

    MAX_LENGTH = 4096

    STATUS_EMOJI: dict[str, str] = {
        "ok": "\u2705",           # checkmark
        "warning": "\u26a0\ufe0f",  # warning sign
        "critical": "\U0001f534",  # red circle
        "running": "\U0001f504",   # arrows (running)
        "pending": "\u23f3",       # hourglass
        "completed": "\u2705",     # checkmark
        "failed": "\u274c",        # cross
        "escalated": "\U0001f198", # SOS button
        "paused": "\u23f8",        # pause button
        "queued": "\u231b",        # hourglass not done
        "draft": "\u270f\ufe0f",   # pencil
        "deployed": "\U0001f680",  # rocket
        "unknown": "\u2753",       # question mark
    }

    @staticmethod
    def progress_bar(current: int, total: int, width: int = 10) -> str:
        """
        Generate a progress bar like: ████░░░░░░ 4/7

        Args:
            current: Current progress value.
            total: Total value.
            width: Character width of the bar.

        Returns:
            A string with filled/empty blocks and a count suffix.
        """
        filled = int(width * current / max(total, 1))
        filled = max(0, min(filled, width))
        bar = "\u2588" * filled + "\u2591" * (width - filled)
        return f"{bar} {current}/{total}"

    @staticmethod
    def truncate(text: str, max_len: int = 4096) -> str:
        """Truncate text to max_len, appending '...' if truncated."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def section_header(title: str) -> str:
        """
        Format a bold section header with a horizontal rule.

        Example output:
            <b>Title</b>
            ━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        return f"<b>{title}</b>\n{'━' * 26}"

    @staticmethod
    def status_badge(status: str) -> str:
        """Return an emoji badge for the given status string."""
        return TelegramView.STATUS_EMOJI.get(status, TelegramView.STATUS_EMOJI["unknown"])

    @staticmethod
    def code_block(text: str) -> str:
        """Wrap text in a Telegram <code> block."""
        return f"<code>{text}</code>"

    @staticmethod
    def key_value(key: str, value: str) -> str:
        """Format a key-value pair as bold key + value."""
        return f"<b>{key}:</b> {value}"

    @staticmethod
    def bullet_list(items: list[str], indent: int = 0) -> str:
        """Format a list of items as bullet points."""
        prefix = " " * indent
        return "\n".join(f"{prefix}• {item}" for item in items)
