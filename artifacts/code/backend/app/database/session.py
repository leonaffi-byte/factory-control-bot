"""AsyncSession factory for database operations."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)


class AsyncSessionFactory:
    """Creates async database sessions with proper lifecycle management."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[AsyncSession, None]:
        """Create a new session with automatic commit/rollback."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def create_session(self) -> AsyncSession:
        """Create a raw session (caller manages lifecycle)."""
        return self._session_factory()

    @property
    def engine(self) -> AsyncEngine:
        return self._engine
