"""Embed and progress-bar builders. Pure functions — no Discord I/O."""
from typing import Optional

import discord

from .track import GuildState, Track, fmt_time

COLOR = discord.Color.blurple()


def _humanize(n: Optional[int]) -> Optional[str]:
    """1785448395 -> '1.8B'."""
    if n is None:
        return None
    value = float(n)
    for unit in ("", "K", "M", "B"):
        if abs(value) < 1000:
            return f"{int(value)}{unit}" if unit == "" else f"{value:.1f}{unit}"
        value /= 1000
    return f"{value:.1f}T"


def progress_bar(elapsed: float, total: Optional[float], length: int = 20) -> str:
    """Render a progress bar like '▬▬▬🔘▬▬  1:23 / 3:45', or '🔴 Live'."""
    if not total:
        return "🔴 **Live**"
    fraction = min(max(elapsed / total, 0.0), 1.0)
    filled = int(fraction * length)
    filled = min(filled, length - 1)
    bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
    return f"{bar}\n`{fmt_time(elapsed)} / {fmt_time(total)}`"


def now_playing_embed(track: Track, state: GuildState, elapsed: float) -> discord.Embed:
    source = track.extra.get("source", "")
    embed = discord.Embed(
        title=track.title[:256],
        url=track.url or None,
        description=progress_bar(elapsed, None if track.is_live else track.duration),
        color=COLOR,
    )
    embed.set_author(name="🔴 Now Streaming" if track.is_live else "🎶 Now Playing")
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    if source == "Radio":
        if track.author:
            embed.add_field(name="Country", value=track.author, inline=True)
        quality = " · ".join(
            p for p in (track.extra.get("codec"), track.extra.get("bitrate")) if p
        )
        if quality:
            embed.add_field(name="Quality", value=quality, inline=True)
        if track.extra.get("tags"):
            embed.add_field(name="Tags", value=track.extra["tags"][:200], inline=False)
    else:
        if track.author:
            embed.add_field(name="Channel", value=track.author, inline=True)
        views = _humanize(track.extra.get("views"))
        if views:
            embed.add_field(name="Views", value=views, inline=True)

    if track.requested_by:
        embed.add_field(name="Requested by", value=track.requested_by, inline=True)

    footer = f"🔊 {int(state.volume * 100)}%"
    if state.loop:
        footer += "  ·  🔁 Loop on"
    if state.audio_filter and state.audio_filter != "none":
        footer += f"  ·  🎛️ {state.audio_filter}"
    if state.queue:
        footer += f"  ·  📋 {len(state.queue)} in queue"
    embed.set_footer(text=footer)
    return embed


def added_embed(track: Track, position: int) -> discord.Embed:
    embed = discord.Embed(
        title=track.title[:256],
        url=track.url or None,
        color=COLOR,
    )
    embed.set_author(name="➕ Added to queue")
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    embed.add_field(name="Duration", value=track.display_duration, inline=True)
    embed.add_field(name="Position", value=f"#{position}", inline=True)
    if track.requested_by:
        embed.add_field(name="Requested by", value=track.requested_by, inline=True)
    return embed


def queue_embed(state: GuildState) -> discord.Embed:
    embed = discord.Embed(title="📋 Queue", color=COLOR)
    if state.current is not None:
        embed.add_field(
            name="Now playing",
            value=f"**{state.current.title}** ({state.current.display_duration})",
            inline=False,
        )
    if state.queue:
        lines = []
        for i, track in enumerate(list(state.queue)[:10], start=1):
            lines.append(f"`{i}.` {track.title} ({track.display_duration})")
        remaining = len(state.queue) - 10
        if remaining > 0:
            lines.append(f"...and **{remaining}** more.")
        embed.add_field(name="Up next", value="\n".join(lines), inline=False)
    elif state.current is None:
        embed.description = "The queue is empty."
    return embed


def config_embed(guild: discord.Guild, settings) -> discord.Embed:
    """Render a guild's persisted settings (used by /config)."""
    embed = discord.Embed(title="⚙️ Server settings", color=COLOR)
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
    dj = guild.get_role(settings.dj_role_id) if settings.dj_role_id else None
    embed.add_field(
        name="DJ role",
        value=dj.mention if dj else "Not set — everyone can control playback",
        inline=False,
    )
    embed.add_field(
        name="Default volume", value=f"{int(settings.default_volume * 100)}%", inline=False
    )
    return embed


def lyrics_embed(title: str, lyrics: str) -> discord.Embed:
    """Lyrics, truncated to Discord's 4096-char description limit."""
    limit = 4096
    if len(lyrics) > limit:
        lyrics = lyrics[: limit - 1].rstrip() + "…"
    return discord.Embed(title=f"🎤 {title}"[:256], description=lyrics, color=COLOR)
