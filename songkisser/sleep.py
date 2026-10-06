"""Per-user sleep timers: disconnect a member from voice once their timer runs
out. Timers live in memory only, so a bot restart clears them."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import discord

from .config import (
    SLEEP_DEFAULT_FINISH_LIMIT,
    SLEEP_MAX,
    SLEEP_MIN,
)

if TYPE_CHECKING:
    from .player import MusicManager

# Never wait on a song for longer than its remaining time plus this slack (it
# covers a short pause, and stops a paused song from postponing the timer forever).
_FINISH_SLACK = 60
_POLL_INTERVAL = 2

Key = tuple[int, int]  # (guild_id, user_id)


@dataclass
class SleepTimer:
    deadline: float  # wall-clock unix time, so it can be shown as a Discord timestamp
    channel: Optional[discord.abc.Messageable]  # where to announce the disconnect
    task: asyncio.Task


class SleepTimers:
    def __init__(self, bot: discord.Client, music: "MusicManager"):
        self.bot = bot
        self.music = music
        self._timers: dict[Key, SleepTimer] = {}
        # "Let the song finish if at most this many seconds remain" (0 = never,
        # None = always). A per-user preference that outlives individual timers.
        self._finish_limits: dict[Key, Optional[float]] = {}

    # -- queries -------------------------------------------------------------

    def deadline(self, guild_id: int, user_id: int) -> Optional[float]:
        timer = self._timers.get((guild_id, user_id))
        return timer.deadline if timer else None

    def remaining(self, guild_id: int, user_id: int) -> Optional[float]:
        deadline = self.deadline(guild_id, user_id)
        return None if deadline is None else max(0.0, deadline - time.time())

    def finish_limit(self, guild_id: int, user_id: int) -> Optional[float]:
        return self._finish_limits.get((guild_id, user_id), SLEEP_DEFAULT_FINISH_LIMIT)

    def set_finish_limit(self, guild_id: int, user_id: int, limit: Optional[float]) -> None:
        self._finish_limits[(guild_id, user_id)] = limit

    # -- changes -------------------------------------------------------------

    def set(
        self, member: discord.Member, seconds: float, channel: Optional[discord.abc.Messageable]
    ) -> float:
        """Start (or replace) a member's timer. Returns the clamped length in seconds."""
        seconds = max(SLEEP_MIN, min(SLEEP_MAX, float(seconds)))
        key = (member.guild.id, member.id)
        old = self._timers.pop(key, None)
        if old is not None:
            old.task.cancel()
            channel = channel or old.channel
        deadline = time.time() + seconds
        task = self.bot.loop.create_task(self._run(member.guild.id, member.id, deadline))
        self._timers[key] = SleepTimer(deadline, channel, task)
        return seconds

    def adjust(
        self, member: discord.Member, delta: float, channel: Optional[discord.abc.Messageable]
    ) -> float:
        """Add (or with a negative delta, remove) time. Starts a timer if none runs."""
        current = self.remaining(member.guild.id, member.id) or 0.0
        return self.set(member, current + delta, channel)

    def cancel(self, guild_id: int, user_id: int) -> bool:
        timer = self._timers.pop((guild_id, user_id), None)
        if timer is None:
            return False
        timer.task.cancel()
        return True

    def cancel_all(self) -> None:
        for timer in self._timers.values():
            timer.task.cancel()
        self._timers.clear()

    # -- expiry --------------------------------------------------------------

    async def _run(self, guild_id: int, user_id: int, deadline: float) -> None:
        try:
            await asyncio.sleep(max(0.0, deadline - time.time()))
            await self._wait_for_song(guild_id, user_id)
        except asyncio.CancelledError:
            return

        key = (guild_id, user_id)
        timer = self._timers.get(key)
        if timer is None or timer.deadline != deadline:
            return
        # Drop the timer before disconnecting: the resulting voice update cancels
        # any timer the member still has, which must not cancel this task.
        del self._timers[key]

        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        if member is None or member.voice is None:
            return  # already gone
        try:
            await member.move_to(None, reason="Sleep timer ended")
        except discord.Forbidden:
            await self._announce(
                timer,
                f"💤 {member.display_name}'s sleep timer ended, but I need the "
                "**Move Members** permission to disconnect them.",
            )
            return
        except discord.HTTPException as e:
            print(f"[sleep] failed to disconnect {user_id} in guild {guild_id}: {e!r}")
            return
        await self._announce(
            timer, f"💤 {member.display_name}'s sleep timer ended. Good night!"
        )

    async def _wait_for_song(self, guild_id: int, user_id: int) -> None:
        """If the member is listening to a song that ends soon enough (within
        their finish limit), wait for it to finish."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        member = guild.get_member(user_id)
        voice_client = guild.voice_client
        state = self.music.states.get(guild_id)
        if (
            member is None
            or member.voice is None
            or voice_client is None
            or member.voice.channel != voice_client.channel
            or state is None
            or state.current is None
            or state.current.is_live
            or not state.current.duration
        ):
            return

        left = state.current.duration - state.elapsed(self.bot.loop.time())
        limit = self.finish_limit(guild_id, user_id)
        if limit is not None and left > limit:
            return

        finished = state.tracks_finished
        give_up = time.time() + left + _FINISH_SLACK
        while time.time() < give_up:
            if (
                self.music.states.get(guild_id) is not state  # bot left / state reset
                or state.current is None
                or state.tracks_finished != finished
                or member.voice is None
            ):
                return
            await asyncio.sleep(_POLL_INTERVAL)

    async def _announce(self, timer: SleepTimer, message: str) -> None:
        if timer.channel is None:
            return
        try:
            await timer.channel.send(message)
        except discord.DiscordException as e:
            print(f"[sleep] announce failed: {e!r}")
