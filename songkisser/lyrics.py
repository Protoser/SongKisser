"""Lyrics lookup via the free lyrics.ovh API (no key required)."""
from __future__ import annotations

import re
from typing import Optional

import aiohttp

_API = "https://api.lyrics.ovh/v1/{artist}/{title}"

# Junk commonly appended to YouTube titles that hurts the artist/title match.
_NOISE = re.compile(
    r"\((?:official|lyric|audio|video|hd|hq|visualizer|remaster).*?\)"
    r"|\[(?:official|lyric|audio|video|hd|hq|visualizer|remaster).*?\]"
    r"|official\s+(?:music\s+)?video"
    r"|lyric[s]?\s+video",
    re.IGNORECASE,
)


def guess_artist_title(track_title: str, fallback_author: Optional[str]) -> tuple[str, str]:
    """Best-effort split of a track title into (artist, title)."""
    cleaned = _NOISE.sub("", track_title).strip(" -|")
    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return artist.strip(), title.strip()
    return (fallback_author or "").strip(), cleaned.strip()


async def fetch_lyrics(artist: str, title: str) -> Optional[str]:
    """Return lyrics text, or None if nothing usable was found."""
    if not title:
        return None
    url = _API.format(artist=artist or "", title=title)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, ValueError) as e:
        print(f"[lyrics] fetch failed: {e!r}")
        return None
    lyrics = (data or {}).get("lyrics")
    if not lyrics or not lyrics.strip():
        return None
    # lyrics.ovh returns CRLF and occasional double blank lines
    return re.sub(r"\n{3,}", "\n\n", lyrics.replace("\r\n", "\n")).strip()
