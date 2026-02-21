"""User management service with in-memory caching."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, delete, update

from app.models.user import User

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()


class UserService:
    """
    Manages user whitelist with an in-memory cache for fast auth checks.

    The cache is refreshed on startup and after any add/remove operation.
    """

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory
        self._cache: dict[int, User] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_loaded = False

    async def _ensure_cache(self) -> None:
        """Load the cache if not yet loaded."""
        if self._cache_loaded:
            return
        await self.refresh_cache()

    async def refresh_cache(self) -> None:
        """Refresh the in-memory user whitelist cache from the database."""
        async with self._cache_lock:
            async with self._session_factory() as session:
                result = await session.execute(select(User))
                users = result.scalars().all()
                self._cache = {u.telegram_id: u for u in users}
                self._cache_loaded = True
                logger.info("user_cache_refreshed", count=len(self._cache))

    async def is_authorized(self, telegram_id: int) -> bool:
        """Check if a user is in the whitelist (cached)."""
        await self._ensure_cache()
        return telegram_id in self._cache

    async def is_admin(self, telegram_id: int) -> bool:
        """Check if a user is an admin (cached)."""
        await self._ensure_cache()
        user = self._cache.get(telegram_id)
        return user is not None and user.role == "admin"

    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID."""
        await self._ensure_cache()
        cached = self._cache.get(telegram_id)
        if cached:
            return cached

        # Fallback to DB
        async with self._session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def add_user(
        self,
        telegram_id: int,
        display_name: str,
        role: str = "user",
    ) -> User:
        """Add a user to the whitelist."""
        async with self._session_factory() as session:
            # Check if exists
            existing = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"User {telegram_id} already exists")

            user = User(
                telegram_id=telegram_id,
                display_name=display_name,
                role=role,
            )
            session.add(user)
            await session.flush()

            logger.info("user_added", telegram_id=telegram_id, role=role)

        await self.refresh_cache()
        return user

    async def remove_user(self, telegram_id: int) -> bool:
        """Remove a user from the whitelist."""
        async with self._session_factory() as session:
            result = await session.execute(
                delete(User).where(User.telegram_id == telegram_id)
            )
            removed = result.rowcount > 0

        if removed:
            logger.info("user_removed", telegram_id=telegram_id)
            await self.refresh_cache()

        return removed

    async def list_users(self) -> list[User]:
        """List all whitelisted users."""
        await self._ensure_cache()
        return list(self._cache.values())

    async def ensure_admin(self, admin_telegram_id: int) -> None:
        """Ensure the admin user exists in the database."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == admin_telegram_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                if existing.role != "admin":
                    existing.role = "admin"
                    session.add(existing)
                    logger.info("admin_role_upgraded", telegram_id=admin_telegram_id)
            else:
                admin = User(
                    telegram_id=admin_telegram_id,
                    display_name="Admin",
                    role="admin",
                )
                session.add(admin)
                logger.info("admin_user_created", telegram_id=admin_telegram_id)

        await self.refresh_cache()

    async def touch_last_active(self, telegram_id: int) -> None:
        """Update last_active timestamp for a user."""
        async with self._session_factory() as session:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(last_active=datetime.utcnow())
            )
