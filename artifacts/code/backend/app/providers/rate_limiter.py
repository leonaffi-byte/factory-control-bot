"""Per-provider rate limit tracking with sliding window."""
from __future__ import annotations

import time
from collections import defaultdict


class ProviderRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)  # provider -> timestamps
        self._daily_counts: dict[str, int] = defaultdict(int)
        self._daily_tokens: dict[str, int] = defaultdict(int)
        self._limits: dict[str, dict] = {}  # provider -> {rpm, rpd, tpm}
        self._last_reset_date: str = ""

    def set_limits(self, provider_name: str, rpm: int = 0, rpd: int = 0, tpm: int = 0) -> None:
        self._limits[provider_name] = {"rpm": rpm, "rpd": rpd, "tpm": tpm}

    def check_allowed(self, provider_name: str, model_name: str = "") -> bool:
        """Check if request is allowed under rate limits."""
        self._cleanup_old_requests(provider_name)
        self._maybe_reset_daily()
        limits = self._limits.get(provider_name, {})
        rpm = limits.get("rpm", 0)
        rpd = limits.get("rpd", 0)
        if rpm > 0 and len(self._requests[provider_name]) >= rpm:
            return False
        if rpd > 0 and self._daily_counts[provider_name] >= rpd:
            return False
        return True

    def record_request(self, provider_name: str, model_name: str = "", tokens: int = 0) -> None:
        now = time.time()
        self._requests[provider_name].append(now)
        self._daily_counts[provider_name] += 1
        self._daily_tokens[provider_name] += tokens

    def get_usage(self, provider_name: str) -> dict:
        self._cleanup_old_requests(provider_name)
        limits = self._limits.get(provider_name, {})
        return {
            "rpm_used": len(self._requests[provider_name]),
            "rpm_limit": limits.get("rpm", 0),
            "rpd_used": self._daily_counts[provider_name],
            "rpd_limit": limits.get("rpd", 0),
            "tokens_today": self._daily_tokens[provider_name],
        }

    def get_warning_level(self, provider_name: str) -> str | None:
        """Returns 'warning' at 80%, 'critical' at 100%, None otherwise."""
        usage = self.get_usage(provider_name)
        for key in ("rpm", "rpd"):
            limit = usage[f"{key}_limit"]
            used = usage[f"{key}_used"]
            if limit > 0:
                ratio = used / limit
                if ratio >= 1.0:
                    return "critical"
                if ratio >= 0.8:
                    return "warning"
        return None

    def reset_daily(self, provider_name: str | None = None) -> None:
        if provider_name:
            self._daily_counts[provider_name] = 0
            self._daily_tokens[provider_name] = 0
        else:
            self._daily_counts.clear()
            self._daily_tokens.clear()

    def _cleanup_old_requests(self, provider_name: str) -> None:
        cutoff = time.time() - 60  # 1 minute window
        self._requests[provider_name] = [
            t for t in self._requests[provider_name] if t > cutoff
        ]

    def _maybe_reset_daily(self) -> None:
        import datetime

        today = datetime.date.today().isoformat()
        if today != self._last_reset_date:
            self._last_reset_date = today
            self.reset_daily()
