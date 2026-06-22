"""The audio engine: resolving tracks, building ffmpeg sources, driving the
per-guild queue, and maintaining the live Now Playing controller."""
import asyncio
import random
from collections import defaultdict, deque
from typing import Optional

import discord
import yt_dlp
from radio_browser import RadioBrowser

from .config import SEARCH_RESULTS, UPDATE_INTERVAL, VOLUME_STEP, YTDL_FORMAT_OPTIONS
from .embeds import added_embed, now_playing_embed
from .track import GuildState, Track, fmt_time
from .views import PlayerControls

# Suppress yt-dlp's "report this bug" suffix (it is called with a `before` kwarg)
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""

_ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
_ytdl_flat = yt_dlp.YoutubeDL({**YTDL_FORMAT_OPTIONS, "extract_flat": True})


def _extract(query: str) -> dict:
    data = _ytdl.extract_info(query, download=False)
    if "entries" in data:
        data = data["entries"][0]
    return data


def _http(url: Optional[str]) -> Optional[str]:
    """Return url only if it's a usable http(s) link (Discord rejects others in
    link buttons / thumbnails)."""
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    return None


class MusicManager:
    """Owns playback state for every guild and the logic to drive it."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.states: dict[int, GuildState] = defaultdict(GuildState)

    def state(self, guild_id: int) -> GuildState:
        return self.states[guild_id]

    def drop_state(self, guild_id: int) -> None:
        state = self.states.get(guild_id)
        if state and state.updater_task and not state.updater_task.done():
            state.updater_task.cancel()
        self.states.pop(guild_id, None)

    # -- voice ---------------------------------------------------------------

    async def ensure_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        """Connect to (or move to) the caller's voice channel."""
        user_voice = interaction.user.voice
        if not user_voice or not user_voice.channel:
            return None
        voice_client = interaction.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return await user_voice.channel.connect()
        if voice_client.channel != user_voice.channel:
            await voice_client.move_to(user_voice.channel)
        return voice_client

    def _voice(self, guild_id: int) -> Optional[discord.VoiceClient]:
        guild = self.bot.get_guild(guild_id)
        return guild.voice_client if guild else None

    # -- resolving -----------------------------------------------------------

    async def resolve_youtube(self, query: str) -> Track:
        """Resolve a YouTube URL or search term into a fully playable Track."""
        data = await self.bot.loop.run_in_executor(None, lambda: _extract(query))
        return Track(
            title=data.get("title", "Unknown"),
            duration=data.get("duration"),
            stream_url=data["url"],
            http_headers=data.get("http_headers"),
            is_live=bool(data.get("is_live")),
            url=_http(data.get("webpage_url")),
            thumbnail=_http(data.get("thumbnail")),
            author=data.get("uploader") or data.get("channel"),
            extra={"source": "YouTube", "views": data.get("view_count")},
        )

    def track_from_station(self, station: dict) -> Track:
        tags = station.get("tags") or ""
        bitrate = station.get("bitrate")
        return Track(
            title=(station.get("name") or "Unknown").strip() or "Unknown",
            duration=None,
            stream_url=station.get("url_resolved") or station.get("url"),
            is_live=True,
            url=_http(station.get("homepage")),
            thumbnail=_http(station.get("favicon")),
            author=station.get("country") or None,
            extra={
                "source": "Radio",
                "codec": station.get("codec") or None,
                "bitrate": f"{bitrate} kbps" if bitrate else None,
                "tags": ", ".join(t for t in tags.split(",")[:6] if t) or None,
            },
        )

    # -- search (lightweight, for the picker) --------------------------------

    async def search_youtube(self, query: str, n: int = SEARCH_RESULTS) -> list[dict]:
        def _run() -> list:
            data = _ytdl_flat.extract_info(f"ytsearch{n}:{query}", download=False)
            return data.get("entries") or []

        entries = await self.bot.loop.run_in_executor(None, _run)
        candidates = []
        for e in entries:
            if not e:
                continue
            url = e.get("url") or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else None)
            if not url:
                continue
            uploader = e.get("uploader") or e.get("channel") or ""
            duration = fmt_time(e["duration"]) if e.get("duration") else ""
            desc = " · ".join(p for p in (uploader, duration) if p)
            candidates.append({"label": e.get("title", "Unknown"), "description": desc, "url": url})
        return candidates

    async def search_radio(self, name: str, n: int = SEARCH_RESULTS) -> list[dict]:
        stations = await self.bot.loop.run_in_executor(
            None, lambda: RadioBrowser().search_radio(name=name)
        )
        candidates = []
        for s in stations[:n]:
            quality = f"{s.get('codec') or ''} {s.get('bitrate') or ''}".strip()
            desc = " · ".join(p for p in (s.get("country") or "", quality) if p)
            candidates.append(
                {"label": (s.get("name") or "Unknown").strip(), "description": desc, "station": s}
            )
        return candidates

    # -- sources -------------------------------------------------------------

    @staticmethod
    def build_source(track: Track, volume: float) -> discord.AudioSource:
        """Create a fresh ffmpeg source. Lists are passed for the ffmpeg options
        so values (like header blobs) don't need shell quoting."""
        before = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        headers = track.http_headers or {}
        user_agent = headers.get("User-Agent")
        if user_agent:
            before += ["-user_agent", user_agent]
        other = {k: v for k, v in headers.items() if k.lower() != "user-agent"}
        if other:
            before += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in other.items())]
        source = discord.FFmpegPCMAudio(track.stream_url, before_options=before, options=["-vn"])
        return discord.PCMVolumeTransformer(source, volume=volume)

    # -- queue + playback ----------------------------------------------------

    async def announce(self, state: GuildState, message: str) -> None:
        if state.text_channel is not None:
            try:
                await state.text_channel.send(message)
            except discord.DiscordException as e:
                print(f"[announce] failed to send message: {e!r}")

    async def enqueue(self, interaction: discord.Interaction, track: Track) -> None:
        """Add a track to the guild queue and start playback if idle."""
        state = self.state(interaction.guild.id)
        state.text_channel = interaction.channel
        track.requested_by = interaction.user.display_name
        state.queue.append(track)

        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            await interaction.followup.send(embed=added_embed(track, len(state.queue)))
        else:
            await interaction.followup.send(f"🎶 Starting **{track.title}**…")
            await self.advance(interaction.guild)

    async def play_track(self, guild: discord.Guild, track: Track) -> None:
        state = self.state(guild.id)
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return
        source = self.build_source(track, state.volume)
        state.current = track
        state.started = self.bot.loop.time()
        state.paused_since = None
        state.paused_total = 0.0
        voice_client.play(source, after=lambda err: self._after_play(guild, err))
        await self.start_controller(guild, track)

    def _after_play(self, guild: discord.Guild, error: Optional[Exception]) -> None:
        """Runs in a voice thread once a track finishes; schedule the next one."""
        if error:
            print(f"[player] playback error in guild {guild.id}: {error!r}")
        future = asyncio.run_coroutine_threadsafe(self.advance(guild), self.bot.loop)
        try:
            future.result()
        except Exception as e:
            print(f"[player] failed to advance queue: {e!r}")

    async def advance(self, guild: discord.Guild) -> None:
        state = self.state(guild.id)
        if state.loop and state.current is not None:
            state.queue.append(state.current)
        state.current = None
        if state.queue:
            await self.play_track(guild, state.queue.popleft())
        else:
            await self.stop_controller(guild.id)
            await self.announce(state, "✅ Queue ended.")
            if guild.voice_client is not None:
                await guild.voice_client.disconnect()

    # -- live controller -----------------------------------------------------

    async def start_controller(self, guild: discord.Guild, track: Track) -> None:
        state = self.state(guild.id)
        await self._teardown_controller(state)
        if state.text_channel is None:
            return
        view = PlayerControls(self, guild.id, track)
        embed = now_playing_embed(track, state, 0.0)
        try:
            state.controller_message = await state.text_channel.send(embed=embed, view=view)
        except discord.DiscordException as e:
            print(f"[controller] send failed: {e!r}")
            state.controller_message = None
            return
        if not track.is_live and track.duration:
            state.updater_task = self.bot.loop.create_task(self._run_updater(guild))

    async def _run_updater(self, guild: discord.Guild) -> None:
        state = self.state(guild.id)
        track = state.current
        try:
            while True:
                await asyncio.sleep(UPDATE_INTERVAL)
                if state.current is not track or state.controller_message is None:
                    return
                if state.paused_since is not None:
                    continue  # bar is frozen while paused; skip the edit
                elapsed = state.elapsed(self.bot.loop.time())
                try:
                    await state.controller_message.edit(
                        embed=now_playing_embed(track, state, elapsed)
                    )
                except discord.NotFound:
                    return
                except discord.DiscordException as e:
                    print(f"[updater] edit failed: {e!r}")
                if track.duration and elapsed >= track.duration:
                    return
        except asyncio.CancelledError:
            return

    async def stop_controller(self, guild_id: int) -> None:
        await self._teardown_controller(self.state(guild_id))

    async def refresh_controller(self, guild_id: int) -> None:
        """Re-render the controller in place (e.g. after /volume or /loop)."""
        state = self.state(guild_id)
        if state.controller_message is None or state.current is None:
            return
        elapsed = state.elapsed(self.bot.loop.time())
        view = PlayerControls(self, guild_id, state.current)
        try:
            await state.controller_message.edit(
                embed=now_playing_embed(state.current, state, elapsed), view=view
            )
        except discord.DiscordException:
            pass

    async def _teardown_controller(self, state: GuildState) -> None:
        if state.updater_task and not state.updater_task.done():
            state.updater_task.cancel()
        state.updater_task = None
        message = state.controller_message
        state.controller_message = None
        if message is not None:
            try:
                await message.edit(view=None)
            except discord.DiscordException:
                pass

    # -- shared control actions (used by both commands and buttons) ----------

    def pause(self, guild_id: int) -> bool:
        state = self.state(guild_id)
        voice_client = self._voice(guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            state.paused_since = self.bot.loop.time()
            return True
        return False

    def resume(self, guild_id: int) -> bool:
        state = self.state(guild_id)
        voice_client = self._voice(guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            if state.paused_since is not None:
                state.paused_total += self.bot.loop.time() - state.paused_since
            state.paused_since = None
            return True
        return False

    def toggle_pause(self, guild_id: int) -> None:
        if not self.resume(guild_id):
            self.pause(guild_id)

    def toggle_loop(self, guild_id: int) -> bool:
        state = self.state(guild_id)
        state.loop = not state.loop
        return state.loop

    def set_volume(self, guild_id: int, volume: float) -> float:
        """Set volume (0.0-1.0), applying it to the live source. Returns the
        clamped value."""
        state = self.state(guild_id)
        state.volume = max(0.0, min(1.0, volume))
        voice_client = self._voice(guild_id)
        if voice_client and isinstance(voice_client.source, discord.PCMVolumeTransformer):
            voice_client.source.volume = state.volume
        return state.volume

    def adjust_volume(self, guild_id: int, delta: float) -> float:
        return self.set_volume(guild_id, self.state(guild_id).volume + delta)

    def volume_up(self, guild_id: int) -> float:
        return self.adjust_volume(guild_id, VOLUME_STEP)

    def volume_down(self, guild_id: int) -> float:
        return self.adjust_volume(guild_id, -VOLUME_STEP)

    def shuffle(self, guild_id: int) -> None:
        state = self.state(guild_id)
        items = list(state.queue)
        random.shuffle(items)
        state.queue = deque(items)

    def skip(self, guild_id: int) -> bool:
        voice_client = self._voice(guild_id)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()  # triggers the after-callback, which advances
            return True
        return False

    def remove(self, guild_id: int, index: int) -> Optional[Track]:
        state = self.state(guild_id)
        if 1 <= index <= len(state.queue):
            track = state.queue[index - 1]
            del state.queue[index - 1]
            return track
        return None

    def clear(self, guild_id: int) -> int:
        state = self.state(guild_id)
        count = len(state.queue)
        state.queue.clear()
        return count

    async def stop(self, guild_id: int) -> None:
        state = self.state(guild_id)
        state.queue.clear()
        state.current = None
        state.loop = False
        await self.stop_controller(guild_id)
        voice_client = self._voice(guild_id)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
