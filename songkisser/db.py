"""Per-guild settings, persisted in SQLite.

State that must survive a restart (DJ role, default volume, language) lives here; ephemeral
playback state stays in-memory in GuildState. All DB access goes through an
executor so the event loop is never blocked, matching the pattern used elsewhere
(e.g. yt-dlp calls in player.py)."""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, replace
from typing import Optional

from .config import DEFAULT_VOLUME


@dataclass
class GuildSettings:
    dj_role_id: Optional[int] = None
    default_volume: float = DEFAULT_VOLUME
    language: Optional[str] = None  # None = each user's own Discord language


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
        # Databases created before the language setting existed lack its column.
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(guild_settings)")}
        if "language" not in columns:
            self._conn.execute("ALTER TABLE guild_settings ADD COLUMN language TEXT")
        self._conn.commit()
        for guild_id, dj_role_id, default_volume, language in self._conn.execute(
            "SELECT guild_id, dj_role_id, default_volume, language FROM guild_settings"
        ):
            self._cache[guild_id] = GuildSettings(
                dj_role_id=dj_role_id,
                default_volume=DEFAULT_VOLUME if default_volume is None else default_volume,
                language=language,
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
            INSERT INTO guild_settings (guild_id, dj_role_id, default_volume, language)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                dj_role_id = excluded.dj_role_id,
                default_volume = excluded.default_volume,
                language = excluded.language
            """,
            (guild_id, settings.dj_role_id, settings.default_volume, settings.language),
        )
        self._conn.commit()

    async def set_dj_role(self, guild_id: int, role_id: Optional[int]) -> None:
        await self._upsert(replace(self.get(guild_id), dj_role_id=role_id), guild_id)

    async def set_default_volume(self, guild_id: int, volume: float) -> None:
        await self._upsert(replace(self.get(guild_id), default_volume=volume), guild_id)

    async def set_language(self, guild_id: int, language: Optional[str]) -> None:
        await self._upsert(replace(self.get(guild_id), language=language), guild_id)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
