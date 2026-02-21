"""Database package — engine, session factory, and convenience helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.database.session import AsyncSessionFactory


def get_session_factory(settings: "Settings") -> "AsyncSessionFactory":
    """
    Convenience factory for CLI commands: create engine + session factory.

    Creates a new AsyncEngine from *settings* and wraps it in an
    AsyncSessionFactory.  Each call to this function creates a fresh engine,
    which is appropriate for short-lived CLI invocations.

    For long-running server processes use app.main which manages the engine
    lifecycle explicitly.
    """
    from app.database.engine import create_engine
    from app.database.session import AsyncSessionFactory as _AsyncSessionFactory

    engine = create_engine(settings)
    return _AsyncSessionFactory(engine)
