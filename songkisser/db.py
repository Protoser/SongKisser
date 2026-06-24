"""Per-guild settings, persisted in SQLite.

State that must survive a restart (DJ role, default volume) lives here; ephemeral
playback state stays in-memory in GuildState. All DB access goes through an
executor so the event loop is never blocked, matching the pattern used elsewhere
(e.g. yt-dlp calls in player.py)."""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .config import DEFAULT_VOLUME


@dataclass
class GuildSettings:
    dj_role_id: Optional[int] = None
    default_volume: float = DEFAULT_VOLUME


class SettingsStore:
    """SQLite-backed store with a write-through in-memory cache."""

    def __init__(self, path: str):
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._cache: dict[int, GuildSettings] = {}

    async def init(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id       INTEGER PRIMARY KEY,
                dj_role_id     INTEGER,
                default_volume REAL
            )
            """
        )
        self._conn.commit()
        for guild_id, dj_role_id, default_volume in self._conn.execute(
            "SELECT guild_id, dj_role_id, default_volume FROM guild_settings"
        ):
            self._cache[guild_id] = GuildSettings(
                dj_role_id=dj_role_id,
                default_volume=DEFAULT_VOLUME if default_volume is None else default_volume,
            )

    def get(self, guild_id: int) -> GuildSettings:
        """Return cached settings (defaults if the guild has never been configured)."""
        return self._cache.get(guild_id, GuildSettings())

    async def _upsert(self, settings: GuildSettings, guild_id: int) -> None:
        self._cache[guild_id] = settings
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._upsert_sync, guild_id, settings)

    def _upsert_sync(self, guild_id: int, settings: GuildSettings) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT INTO guild_settings (guild_id, dj_role_id, default_volume)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                dj_role_id = excluded.dj_role_id,
                default_volume = excluded.default_volume
            """,
            (guild_id, settings.dj_role_id, settings.default_volume),
        )
        self._conn.commit()

    async def set_dj_role(self, guild_id: int, role_id: Optional[int]) -> None:
        current = self.get(guild_id)
        await self._upsert(
            GuildSettings(dj_role_id=role_id, default_volume=current.default_volume),
            guild_id,
        )

    async def set_default_volume(self, guild_id: int, volume: float) -> None:
        current = self.get(guild_id)
        await self._upsert(
            GuildSettings(dj_role_id=current.dj_role_id, default_volume=volume),
            guild_id,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
