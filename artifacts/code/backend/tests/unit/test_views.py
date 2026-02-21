"""Unit tests for Telegram view rendering (black-box, per spec-v2.md)."""

from __future__ import annotations

import pytest

from app.bot.views.base import TelegramView


class TestProgressBar:
    def test_zero_progress(self):
        result = TelegramView.progress_bar(0, 7)
        assert "0/7" in result
        assert "░" in result

    def test_full_progress(self):
        result = TelegramView.progress_bar(7, 7)
        assert "7/7" in result
        assert "█" in result

    def test_partial_progress(self):
        result = TelegramView.progress_bar(4, 7)
        assert "4/7" in result
        assert "█" in result
        assert "░" in result

    def test_custom_width(self):
        result = TelegramView.progress_bar(5, 10, width=10)
        assert "5/10" in result


class TestTruncate:
    def test_short_text_not_truncated(self):
        text = "Hello, world!"
        result = TelegramView.truncate(text)
        assert result == text

    def test_long_text_truncated(self):
        text = "x" * 5000
        result = TelegramView.truncate(text)
        assert len(result) <= 4096

    def test_truncated_text_has_indicator(self):
        text = "x" * 5000
        result = TelegramView.truncate(text)
        assert "truncated" in result.lower() or "..." in result

    def test_custom_max_length(self):
        text = "x" * 200
        result = TelegramView.truncate(text, max_len=100)
        assert len(result) <= 100

    def test_exact_max_length_not_truncated(self):
        text = "x" * 4096
        result = TelegramView.truncate(text)
        assert result == text


class TestViewConstants:
    def test_max_length(self):
        assert TelegramView.MAX_LENGTH == 4096

    def test_status_emoji_mapping(self):
        emojis = TelegramView.STATUS_EMOJI
        assert "running" in emojis
        assert "completed" in emojis
        assert "failed" in emojis
        assert "paused" in emojis
        assert "pending" in emojis
