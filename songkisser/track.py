"""The Track model and per-guild playback state."""
import asyncio
import re
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


def parse_time(value: str) -> Optional[float]:
    """Parse '83', '1:23' or '1:02:03' into seconds. Returns None if invalid."""
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) > 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    seconds = 0
    for n in nums:
        seconds = seconds * 60 + n
    return float(seconds)


_DURATION_UNITS = re.compile(r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$")


def parse_duration(value: str) -> Optional[float]:
    """Parse a timer length into seconds. A bare number means minutes ('30');
    also accepts unit forms ('1h30m', '45m', '90s') and h:mm ('1:30').
    Returns None if invalid."""
    value = value.strip().lower().replace(" ", "")
    if not value:
        return None
    if value.isdigit():
        return int(value) * 60.0
    if ":" in value:
        parts = value.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            return None
        return (int(parts[0]) * 60 + int(parts[1])) * 60.0
    match = _DURATION_UNITS.match(value)
    if not match or not any(match.groups()):
        return None
    h, m, s = (int(g) if g else 0 for g in match.groups())
    return float(h * 3600 + m * 60 + s)


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
    audio_filter: str = "none"  # key into config.AUDIO_FILTERS

    # When set, the next advance() re-plays the current track at this offset
    # (used by /seek and /filter) instead of moving to the next queued track.
    pending_seek: Optional[float] = None

    # Bumped every time a track finishes or is skipped (not on seek/filter
    # replays), so sleep timers can wait for "the current song to end".
    tracks_finished: int = 0

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
