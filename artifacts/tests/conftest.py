"""
Shared pytest fixtures for Factory Control Bot test suite.
Black-box tests — tests against interfaces, not implementation.
"""
from __future__ import annotations

import sys
import os
import time
from types import SimpleNamespace
from typing import Any
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add backend code to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code", "backend"))


@pytest.fixture()
def time_controller(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """Control time.time() and time.monotonic() for deterministic tests."""
    state = {"t": 1_700_000_000.0}

    monkeypatch.setattr(time, "time", lambda: float(state["t"]))
    monkeypatch.setattr(time, "monotonic", lambda: float(state["t"]))

    def advance(seconds: float) -> None:
        state["t"] += float(seconds)

    return advance


@pytest.fixture()
def mock_bot() -> AsyncMock:
    """Mock Telegram Bot instance."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture()
def mock_update() -> MagicMock:
    """Mock Telegram Update with user, chat, and message."""
    update = MagicMock()
    update.effective_user = SimpleNamespace(id=42, username="tester", first_name="Test")
    update.effective_chat = SimpleNamespace(id=123)
    update.message = AsyncMock()
    update.message.text = ""
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


@pytest.fixture()
def mock_context(mock_bot) -> MagicMock:
    """Mock PTB CallbackContext."""
    context = MagicMock()
    context.bot = mock_bot
    context.user_data = {}
    context.bot_data = {"allowed_users": {42}}
    context.args = []
    return context


# ── v2.0 Fixtures ──────────────────────────────────────────────


@pytest.fixture
def mock_settings(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A Settings instance populated with deterministic test values for v2.0."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345678")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_1234567890")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test_key_1234567890")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("TOGETHER_API_KEY", "tog-test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test-key")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "sn-test-key")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "mis-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("FACTORY_ROOT_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    from app.config import Settings
    return Settings()


@pytest.fixture
def mock_db_session():
    """AsyncSession mock for database operations."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_project_dict():
    """Sample project data dict for v2.0 tests."""
    import uuid
    return {
        "id": uuid.uuid4(),
        "name": "test-project",
        "description": "A test project",
        "status": "draft",
        "engines": ["claude"],
        "requirements": "Build a test app",
        "created_by": 12345678,
    }


@pytest.fixture
def sample_run_dict():
    """Sample run data dict for v2.0 tests."""
    import uuid
    return {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "engine": "claude",
        "status": "running",
        "current_phase": 1,
        "quality_scores": {},
        "total_cost": 0.0,
        "interface_source": "telegram",
        "created_by": 12345678,
    }
