"""Unit tests for token counting utilities (black-box, per interfaces-v2.md)."""

from __future__ import annotations

import pytest

from app.utils.token_counter import estimate_tokens, fits_in_context


class TestEstimateTokens:
    def test_empty_string_is_zero(self):
        assert estimate_tokens("") == 0

    def test_non_empty_text_is_positive(self):
        assert estimate_tokens("hello world") > 0

    def test_longer_text_has_more_tokens(self):
        short = estimate_tokens("hello")
        long = estimate_tokens("hello world this is a longer piece of text")
        assert long > short

    def test_returns_integer(self):
        result = estimate_tokens("test text")
        assert isinstance(result, int)


class TestFitsInContext:
    def test_short_text_fits_large_context(self):
        assert fits_in_context("short text", 128000) is True

    def test_very_large_text_does_not_fit_small_context(self):
        assert fits_in_context("x" * 500000, 1000) is False

    def test_empty_text_always_fits(self):
        assert fits_in_context("", 100) is True

    def test_margin_parameter_restricts(self, monkeypatch: pytest.MonkeyPatch):
        """Margin reduces effective context window."""
        import app.utils.token_counter as tc

        monkeypatch.setattr(tc, "estimate_tokens", lambda _text: 900)

        # 900 tokens <= 1000 * 0.95 = 950 -> fits
        assert tc.fits_in_context("anything", 1000, margin=0.95) is True
        # 900 tokens > 1000 * 0.80 = 800 -> doesn't fit
        assert tc.fits_in_context("anything", 1000, margin=0.80) is False

    def test_default_margin_is_0_9(self, monkeypatch: pytest.MonkeyPatch):
        """Default margin is 0.9 (90% of context window)."""
        import app.utils.token_counter as tc

        monkeypatch.setattr(tc, "estimate_tokens", lambda _text: 850)

        # 850 <= 1000 * 0.9 = 900 -> fits
        assert tc.fits_in_context("anything", 1000) is True

        monkeypatch.setattr(tc, "estimate_tokens", lambda _text: 950)

        # 950 > 1000 * 0.9 = 900 -> doesn't fit
        assert tc.fits_in_context("anything", 1000) is False
