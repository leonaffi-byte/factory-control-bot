"""PTB BasePersistence implementation backed by PostgreSQL."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, TYPE_CHECKING

import structlog
from telegram.ext import BasePersistence, PersistenceInput
from sqlalchemy import text

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()

# Table for persistence data (created if not exists)
PERSISTENCE_TABLE = "bot_persistence"
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PERSISTENCE_TABLE} (
    key VARCHAR(255) PRIMARY KEY,
    data JSONB NOT NULL DEFAULT '{{}}'::jsonb
)
"""


class PostgreSQLPersistence(BasePersistence):
    """
    Telegram bot persistence using PostgreSQL.

    Stores bot_data, chat_data, user_data, and callback_data in a JSONB column.
    """

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        super().__init__(
            store_data=PersistenceInput(
                bot_data=True,
                chat_data=True,
                user_data=True,
                callback_data=True,
            )
        )
        self._session_factory = session_factory
        self._initialized = False

    async def _ensure_table(self) -> None:
        """Create the persistence table if it doesn't exist."""
        if self._initialized:
            return
        async with self._session_factory() as session:
            await session.execute(text(CREATE_TABLE_SQL))
        self._initialized = True

    async def _load(self, key: str) -> dict:
        """Load data for a given key."""
        await self._ensure_table()
        async with self._session_factory() as session:
            result = await session.execute(
                text(f"SELECT data FROM {PERSISTENCE_TABLE} WHERE key = :key"),
                {"key": key},
            )
            row = result.fetchone()
            if row and row[0]:
                return row[0]
        return {}

    async def _save(self, key: str, data: Any) -> None:
        """Save data for a given key (upsert)."""
        await self._ensure_table()
        serialized = json.loads(json.dumps(data, default=str))
        async with self._session_factory() as session:
            await session.execute(
                text(
                    f"INSERT INTO {PERSISTENCE_TABLE} (key, data) "
                    f"VALUES (:key, :data::jsonb) "
                    f"ON CONFLICT (key) DO UPDATE SET data = :data::jsonb"
                ),
                {"key": key, "data": json.dumps(serialized)},
            )

    # ── BasePersistence interface ──

    async def get_bot_data(self) -> Dict[str, Any]:
        return await self._load("bot_data")

    async def update_bot_data(self, data: Dict[str, Any]) -> None:
        await self._save("bot_data", data)

    async def refresh_bot_data(self, bot_data: Dict[str, Any]) -> Dict[str, Any]:
        return bot_data

    async def get_chat_data(self) -> Dict[int, Dict[str, Any]]:
        raw = await self._load("chat_data")
        return {int(k): v for k, v in raw.items()} if raw else {}

    async def update_chat_data(self, chat_id: int, data: Dict[str, Any]) -> None:
        all_chat_data = await self.get_chat_data()
        all_chat_data[chat_id] = data
        await self._save("chat_data", all_chat_data)

    async def refresh_chat_data(
        self, chat_id: int, chat_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        return chat_data

    async def get_user_data(self) -> Dict[int, Dict[str, Any]]:
        raw = await self._load("user_data")
        return {int(k): v for k, v in raw.items()} if raw else {}

    async def update_user_data(self, user_id: int, data: Dict[str, Any]) -> None:
        all_user_data = await self.get_user_data()
        all_user_data[user_id] = data
        await self._save("user_data", all_user_data)

    async def refresh_user_data(
        self, user_id: int, user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        return user_data

    async def get_callback_data(self) -> Optional[tuple[list[tuple], dict[str, str]]]:
        raw = await self._load("callback_data")
        if not raw:
            return None
        try:
            return (raw.get("callback_data", []), raw.get("mapping", {}))
        except Exception:
            return None

    async def update_callback_data(
        self, data: tuple[list[tuple], dict[str, str]]
    ) -> None:
        await self._save("callback_data", {
            "callback_data": data[0],
            "mapping": data[1],
        })

    async def drop_chat_data(self, chat_id: int) -> None:
        all_chat_data = await self.get_chat_data()
        all_chat_data.pop(chat_id, None)
        await self._save("chat_data", all_chat_data)

    async def drop_user_data(self, user_id: int) -> None:
        all_user_data = await self.get_user_data()
        all_user_data.pop(user_id, None)
        await self._save("user_data", all_user_data)

    async def get_conversations(self, name: str) -> Dict[str, Any]:
        raw = await self._load(f"conversations:{name}")
        return raw

    async def update_conversation(
        self, name: str, key: tuple, new_state: Optional[object]
    ) -> None:
        conversations = await self.get_conversations(name)
        str_key = str(key)
        if new_state is None:
            conversations.pop(str_key, None)
        else:
            conversations[str_key] = new_state
        await self._save(f"conversations:{name}", conversations)

    async def flush(self) -> None:
        """Flush is a no-op — we write on every update."""
        pass
