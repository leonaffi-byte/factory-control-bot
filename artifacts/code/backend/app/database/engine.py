"""AsyncEngine setup with connection pool configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine as _create_async_engine

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()

# Module-level engine reference
_engine: AsyncEngine | None = None


def create_engine(settings: "Settings") -> AsyncEngine:
    """Create and return an async SQLAlchemy engine with pool config."""
    global _engine

    _engine = _create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        echo=settings.log_level == "DEBUG",
    )

    logger.info(
        "database_engine_created",
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )

    return _engine


def get_engine() -> AsyncEngine:
    """Get the current engine instance."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call create_engine() first.")
    return _engine


async def dispose_engine() -> None:
    """Dispose of the engine and close all connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_disposed")
        _engine = None
