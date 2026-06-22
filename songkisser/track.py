"""The Track model and per-guild playback state."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import discord

from .config import DEFAULT_VOLUME


def fmt_time(seconds: Optional[float]) -> str:
    """Format seconds as m:ss (or h:mm:ss for long tracks)."""
    if not seconds:
        return "0:00"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@dataclass
class Track:
    """Metadata for a queued item. The actual ffmpeg source is built lazily, at
    play time, by the player — never at enqueue time."""

    title: str
    duration: Optional[float]
    stream_url: str
    http_headers: Optional[dict] = None
    is_live: bool = False
    requested_by: Optional[str] = None
    url: Optional[str] = None          # link to the source page (YouTube / homepage)
    thumbnail: Optional[str] = None    # artwork image URL
    author: Optional[str] = None       # uploader/channel, or radio country
    extra: dict = field(default_factory=dict)  # source-specific bits for the embed

    @property
    def display_duration(self) -> str:
        if self.is_live or not self.duration:
            return "Live"
        return fmt_time(self.duration)


@dataclass
class GuildState:
    queue: deque = field(default_factory=deque)
    current: Optional[Track] = None
    text_channel: Optional[discord.abc.Messageable] = None
    volume: float = DEFAULT_VOLUME
    loop: bool = False

    # Playback clock (monotonic, from bot.loop.time()) for the progress bar
    started: float = 0.0
    paused_since: Optional[float] = None
    paused_total: float = 0.0

    # Live "Now Playing" controller
    controller_message: Optional[discord.Message] = None
    updater_task: Optional[asyncio.Task] = None

    def elapsed(self, now: float) -> float:
        """Seconds the current track has actually been playing, excluding paused time."""
        if not self.started:
            return 0.0
        reference = self.paused_since if self.paused_since is not None else now
        return max(0.0, reference - self.started - self.paused_total)
