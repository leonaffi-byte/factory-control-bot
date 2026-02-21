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
