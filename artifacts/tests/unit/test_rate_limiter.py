"""
Black-box tests for rate limiters.

v1.0: TelegramRateLimiter (notification rate limiting)
v2.0: ProviderRateLimiter (API provider rate limiting)
"""
import pytest


class TestTokenBucket:
    """Test the Telegram token bucket rate limiter (v1.0)."""

    def _make_limiter(self):
        from app.services.notification import TelegramRateLimiter
        return TelegramRateLimiter()

    def test_initial_burst_allowed(self, time_controller):
        limiter = self._make_limiter()
        assert limiter.can_send(chat_id=100) is True
        assert limiter.can_send(chat_id=100) is True
        assert limiter.can_send(chat_id=100) is True

    def test_per_chat_blocks_after_burst(self, time_controller):
        limiter = self._make_limiter()
        for _ in range(3):
            limiter.can_send(chat_id=100)
        assert limiter.can_send(chat_id=100) is False

    def test_per_chat_refills_over_time(self, time_controller):
        limiter = self._make_limiter()
        for _ in range(3):
            limiter.can_send(chat_id=100)
        assert limiter.can_send(chat_id=100) is False
        time_controller(2.0)
        assert limiter.can_send(chat_id=100) is True

    def test_different_chats_independent(self, time_controller):
        limiter = self._make_limiter()
        for _ in range(3):
            limiter.can_send(chat_id=100)
        assert limiter.can_send(chat_id=100) is False
        assert limiter.can_send(chat_id=200) is True


# ── v2.0: Provider Rate Limiter ──────────────────────────────

class TestProviderRateLimiterBasic:
    """Test provider-level API rate limiting (v2.0)."""

    def test_new_provider_always_allowed(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        assert limiter.check_allowed("groq") is True

    def test_unlimited_provider_always_allowed(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=0, rpd=0)
        for _ in range(100):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is True


class TestProviderRPM:
    def test_rpm_blocks_at_limit(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=5)
        for _ in range(5):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is False

    def test_rpm_allows_below_limit(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=5)
        for _ in range(4):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is True


class TestProviderDailyLimits:
    def test_daily_limit_tracking(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpd=10)
        for _ in range(10):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is False

    def test_reset_daily_clears_counts(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpd=5)
        for _ in range(5):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is False
        limiter.reset_daily("groq")
        assert limiter.check_allowed("groq") is True


class TestProviderUsageReporting:
    def test_get_usage_correct_counts(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=60, rpd=1000)
        limiter.record_request("groq", tokens=100)
        limiter.record_request("groq", tokens=200)
        usage = limiter.get_usage("groq")
        assert usage["rpm_used"] == 2
        assert usage["rpd_used"] == 2
        assert usage["rpd_limit"] == 1000
        assert usage["tokens_today"] == 300


class TestProviderWarningLevels:
    def test_no_warning_below_80_percent(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=100)
        for _ in range(79):
            limiter.record_request("groq")
        assert limiter.get_warning_level("groq") is None

    def test_warning_at_80_percent(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=100)
        for _ in range(80):
            limiter.record_request("groq")
        assert limiter.get_warning_level("groq") == "warning"

    def test_critical_at_100_percent(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=100)
        for _ in range(100):
            limiter.record_request("groq")
        assert limiter.get_warning_level("groq") == "critical"


class TestProviderIsolation:
    def test_limits_per_provider(self):
        from app.providers.rate_limiter import ProviderRateLimiter
        limiter = ProviderRateLimiter()
        limiter.set_limits("groq", rpm=5)
        limiter.set_limits("nvidia", rpm=10)
        for _ in range(5):
            limiter.record_request("groq")
        assert limiter.check_allowed("groq") is False
        assert limiter.check_allowed("nvidia") is True
