"""PostgreSQL LISTEN/NOTIFY helper for cross-service communication."""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger()


class PgEventListener:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None
        self._listening: bool = False
        self._callbacks: dict[str, list[Callable]] = {}

    async def start_listening(
        self,
        channel: str,
        callback: Callable[[dict], Awaitable[None]],
    ) -> None:
        import asyncpg

        if self._conn is None:
            self._conn = await asyncpg.connect(
                self._dsn.replace("+asyncpg", "").replace("postgresql", "postgresql")
            )
        if channel not in self._callbacks:
            self._callbacks[channel] = []
            await self._conn.add_listener(channel, self._on_notification)
        self._callbacks[channel].append(callback)
        self._listening = True
        logger.info("pg_listener_started", channel=channel)

    async def stop_listening(self) -> None:
        if self._conn:
            for channel in self._callbacks:
                await self._conn.remove_listener(channel, self._on_notification)
            await self._conn.close()
            self._conn = None
        self._listening = False
        self._callbacks.clear()

    async def notify(self, channel: str, payload: dict) -> None:
        import asyncpg

        conn = await asyncpg.connect(
            self._dsn.replace("+asyncpg", "").replace("postgresql", "postgresql")
        )
        try:
            await conn.execute(f"NOTIFY {channel}, '{json.dumps(payload)}'")
        finally:
            await conn.close()

    def _on_notification(
        self,
        connection: object,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"raw": payload}
        for cb in self._callbacks.get(channel, []):
            asyncio.create_task(cb(data))
