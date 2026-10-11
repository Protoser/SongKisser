"""Embed and progress-bar builders. Pure functions, no Discord I/O. Every
builder takes the language to render in (see i18n.py)."""
from typing import Optional

import discord

from .i18n import language_name, t
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


def duration_text(track: Track, lang: str) -> str:
    if track.is_live or not track.duration:
        return t(lang, "embeds.live")
    return fmt_time(track.duration)


def progress_bar(elapsed: float, total: Optional[float], lang: str, length: int = 20) -> str:
    """Render a progress bar like '▬▬▬🔘▬▬  1:23 / 3:45', or '🔴 Live'."""
    if not total:
        return t(lang, "embeds.live_bar")
    fraction = min(max(elapsed / total, 0.0), 1.0)
    filled = int(fraction * length)
    filled = min(filled, length - 1)
    bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
    return f"{bar}\n`{fmt_time(elapsed)} / {fmt_time(total)}`"


def now_playing_embed(
    track: Track, state: GuildState, elapsed: float, lang: str
) -> discord.Embed:
    source = track.extra.get("source", "")
    embed = discord.Embed(
        title=track.title[:256],
        url=track.url or None,
        description=progress_bar(elapsed, None if track.is_live else track.duration, lang),
        color=COLOR,
    )
    embed.set_author(
        name=t(lang, "embeds.now_streaming" if track.is_live else "embeds.now_playing")
    )
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    if source == "Radio":
        if track.author:
            embed.add_field(name=t(lang, "embeds.country"), value=track.author, inline=True)
        quality = " · ".join(
            p for p in (track.extra.get("codec"), track.extra.get("bitrate")) if p
        )
        if quality:
            embed.add_field(name=t(lang, "embeds.quality"), value=quality, inline=True)
        if track.extra.get("tags"):
            embed.add_field(
                name=t(lang, "embeds.tags"), value=track.extra["tags"][:200], inline=False
            )
    else:
        if track.author:
            embed.add_field(name=t(lang, "embeds.channel"), value=track.author, inline=True)
        views = _humanize(track.extra.get("views"))
        if views:
            embed.add_field(name=t(lang, "embeds.views"), value=views, inline=True)

    if track.requested_by:
        embed.add_field(
            name=t(lang, "embeds.requested_by"), value=track.requested_by, inline=True
        )

    footer = f"🔊 {int(state.volume * 100)}%"
    if state.loop:
        footer += "  ·  " + t(lang, "embeds.loop_on")
    if state.audio_filter and state.audio_filter != "none":
        footer += f"  ·  🎛️ {state.audio_filter}"
    if state.queue:
        footer += "  ·  " + t(lang, "embeds.in_queue", count=len(state.queue))
    embed.set_footer(text=footer)
    return embed


def added_embed(track: Track, position: int, lang: str) -> discord.Embed:
    embed = discord.Embed(
        title=track.title[:256],
        url=track.url or None,
        color=COLOR,
    )
    embed.set_author(name=t(lang, "embeds.added_to_queue"))
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    embed.add_field(name=t(lang, "embeds.duration"), value=duration_text(track, lang), inline=True)
    embed.add_field(name=t(lang, "embeds.position"), value=f"#{position}", inline=True)
    if track.requested_by:
        embed.add_field(
            name=t(lang, "embeds.requested_by"), value=track.requested_by, inline=True
        )
    return embed


def queue_embed(state: GuildState, lang: str) -> discord.Embed:
    embed = discord.Embed(title=t(lang, "embeds.queue_title"), color=COLOR)
    if state.current is not None:
        embed.add_field(
            name=t(lang, "embeds.queue_now_playing"),
            value=f"**{state.current.title}** ({duration_text(state.current, lang)})",
            inline=False,
        )
    if state.queue:
        lines = []
        for i, track in enumerate(list(state.queue)[:10], start=1):
            lines.append(f"`{i}.` {track.title} ({duration_text(track, lang)})")
        remaining = len(state.queue) - 10
        if remaining > 0:
            lines.append(t(lang, "embeds.queue_more", count=remaining))
        embed.add_field(name=t(lang, "embeds.queue_up_next"), value="\n".join(lines), inline=False)
    elif state.current is None:
        embed.description = t(lang, "music.queue_empty")
    return embed


def config_embed(guild: discord.Guild, settings, lang: str) -> discord.Embed:
    """Render a guild's persisted settings (used by /config)."""
    embed = discord.Embed(title=t(lang, "embeds.settings_title"), color=COLOR)
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
    dj = guild.get_role(settings.dj_role_id) if settings.dj_role_id else None
    embed.add_field(
        name=t(lang, "embeds.dj_role"),
        value=dj.mention if dj else t(lang, "embeds.dj_role_none"),
        inline=False,
    )
    embed.add_field(
        name=t(lang, "embeds.default_volume"),
        value=f"{int(settings.default_volume * 100)}%",
        inline=False,
    )
    embed.add_field(
        name=t(lang, "embeds.language"),
        value=(
            language_name(settings.language)
            if settings.language
            else t(lang, "embeds.language_auto")
        ),
        inline=False,
    )
    return embed


def lyrics_embed(title: str, lyrics: str) -> discord.Embed:
    """Lyrics, truncated to Discord's 4096-char description limit."""
    limit = 4096
    if len(lyrics) > limit:
        lyrics = lyrics[: limit - 1].rstrip() + "…"
    return discord.Embed(title=f"🎤 {title}"[:256], description=lyrics, color=COLOR)


def _finish_text(limit: Optional[float], lang: str) -> str:
    if limit is None:
        return t(lang, "sleep.finish_always")
    if limit <= 0:
        return t(lang, "sleep.finish_never")
    return t(lang, "sleep.finish_limit", minutes=int(limit // 60))


def sleep_timer_embed(
    deadline: Optional[float], finish_limit: Optional[float], lang: str
) -> discord.Embed:
    """The /sleep_timer panel. `deadline` is a unix timestamp, or None if no
    timer is running. Discord renders the relative timestamp as a live countdown."""
    embed = discord.Embed(title=t(lang, "sleep.title"), color=COLOR)
    if deadline is None:
        embed.description = t(lang, "sleep.none")
    else:
        stamp = int(deadline)
        embed.description = (
            t(lang, "sleep.active", relative=f"<t:{stamp}:R>", time=f"<t:{stamp}:t>")
            + "\n\n"
            + _finish_text(finish_limit, lang)
        )
    return embed


def help_embed(lang: str, sections: list[tuple[str, list[str]]], footer: str) -> discord.Embed:
    """The /help overview: one field per section, split into several fields when
    a section is longer than Discord's 1024-character field limit."""
    embed = discord.Embed(
        title=t(lang, "help.title"), description=t(lang, "help.description"), color=COLOR
    )
    for title, lines in sections:
        chunk: list[str] = []
        for line in lines:
            if chunk and len("\n".join(chunk + [line])) > 1024:
                embed.add_field(name=title, value="\n".join(chunk), inline=False)
                title, chunk = "\u200b", []
            chunk.append(line)
        if chunk:
            embed.add_field(name=title, value="\n".join(chunk), inline=False)
    embed.set_footer(text=footer)
    return embed
