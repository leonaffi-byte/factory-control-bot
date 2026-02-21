"""
Black-box tests for the Telegram rate limiter.

Tests against spec:
  - Global: 25 tokens/sec, burst 30
  - Per-chat: 0.8 tokens/sec, burst 3
"""
import pytest


class TestTokenBucket:
    """Test the token bucket rate limiter."""

    def _make_limiter(self):
        """Create a rate limiter. Import here to isolate from other tests."""
        from app.services.notification import TelegramRateLimiter
        return TelegramRateLimiter()

    def test_initial_burst_allowed(self, time_controller):
        """Should allow initial burst up to capacity."""
        limiter = self._make_limiter()
        # Per-chat burst is 3, so first 3 should be allowed
        assert limiter.can_send(chat_id=100) is True
        assert limiter.can_send(chat_id=100) is True
        assert limiter.can_send(chat_id=100) is True

    def test_per_chat_blocks_after_burst(self, time_controller):
        """After burst exhausted, should block."""
        limiter = self._make_limiter()
        for _ in range(3):
            limiter.can_send(chat_id=100)
        # 4th request should be blocked
        assert limiter.can_send(chat_id=100) is False

    def test_per_chat_refills_over_time(self, time_controller):
        """After waiting, tokens should refill."""
        limiter = self._make_limiter()
        for _ in range(3):
            limiter.can_send(chat_id=100)
        assert limiter.can_send(chat_id=100) is False

        # Wait 2 seconds -> ~1.6 tokens at 0.8/sec
        time_controller(2.0)
        assert limiter.can_send(chat_id=100) is True

    def test_different_chats_independent(self, time_controller):
        """Each chat has its own bucket."""
        limiter = self._make_limiter()
        # Exhaust chat A
        for _ in range(3):
            limiter.can_send(chat_id=100)
        assert limiter.can_send(chat_id=100) is False

        # Chat B should still have tokens
        assert limiter.can_send(chat_id=200) is True
        assert limiter.can_send(chat_id=200) is True
        assert limiter.can_send(chat_id=200) is True
