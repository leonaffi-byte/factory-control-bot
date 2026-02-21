"""Global and per-project settings service."""

from __future__ import annotations

import asyncio
from datetime import datetime, date
from typing import Any, TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.models.setting import Setting

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()

# Default settings values
DEFAULTS = {
    "default_engine": "claude",
    "voice_provider": "auto",
    "translation_model": "gpt-4o-mini",
    "requirements_model": "gpt-4o-mini",
    "notification_events": ["phase_end", "error", "complete"],
    "quality_gate_threshold": 97,
    "max_quality_retries": 3,
    "max_fix_cycles": 5,
    "cost_alert_threshold": 50.0,
    "domain_name": None,
    "ssl_email": None,
    "log_poll_interval": 3,
    "disk_critical": False,
    "openrouter_daily_count": 0,
    "openrouter_daily_reset_at": None,
}


class SettingsService:
    """
    Manages global settings stored in the database.

    Settings are stored as JSONB in the settings table with a key-value pattern.
    Provides caching and type-safe access.
    """

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory
        self._cache: dict[str, Any] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_loaded = False
        self._openrouter_count = 0
        self._openrouter_flush_count = 0

    async def _ensure_cache(self) -> None:
        """Load the cache if not yet loaded."""
        if self._cache_loaded:
            return
        await self._refresh_cache()

    async def _refresh_cache(self) -> None:
        """Refresh cache from database."""
        async with self._cache_lock:
            async with self._session_factory() as session:
                result = await session.execute(select(Setting))
                settings = result.scalars().all()
                self._cache = {s.key: s.get_value() for s in settings}
                self._cache_loaded = True

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value. Returns default if not set."""
        await self._ensure_cache()
        value = self._cache.get(key)
        if value is None:
            return default if default is not None else DEFAULTS.get(key)
        return value

    async def set(self, key: str, value: Any, updated_by: int) -> None:
        """Set a setting value."""
        wrapped = Setting.wrap_value(value)

        async with self._session_factory() as session:
            existing = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = existing.scalar_one_or_none()

            if setting:
                setting.value = wrapped
                setting.updated_by = updated_by
                session.add(setting)
            else:
                new_setting = Setting(
                    key=key,
                    value=wrapped,
                    updated_by=updated_by,
                )
                session.add(new_setting)

        # Update cache
        async with self._cache_lock:
            self._cache[key] = value

        logger.info("setting_updated", key=key, updated_by=updated_by)

    async def get_all(self) -> dict[str, Any]:
        """Get all settings as a dict (merged with defaults)."""
        await self._ensure_cache()
        merged = dict(DEFAULTS)
        merged.update(self._cache)
        return merged

    async def get_openrouter_usage(self) -> tuple[int, int]:
        """Get (current_count, daily_limit) for OpenRouter rate tracking."""
        # Check if we need to reset daily counter
        reset_at = await self.get("openrouter_daily_reset_at")
        today = date.today().isoformat()

        if reset_at != today:
            # Reset counter for new day
            await self.set("openrouter_daily_count", 0, updated_by=0)
            await self.set("openrouter_daily_reset_at", today, updated_by=0)
            self._openrouter_count = 0

        count = await self.get("openrouter_daily_count", 0)
        if isinstance(count, str):
            count = int(count)
        self._openrouter_count = count

        # The daily limit comes from Settings (env), not DB
        # Default is 200
        return count, 200

    async def increment_openrouter_usage(self) -> None:
        """Increment OpenRouter daily usage counter."""
        self._openrouter_count += 1
        self._openrouter_flush_count += 1

        # Flush to DB every 10 requests or if explicitly called
        if self._openrouter_flush_count >= 10:
            await self.set("openrouter_daily_count", self._openrouter_count, updated_by=0)
            self._openrouter_flush_count = 0
