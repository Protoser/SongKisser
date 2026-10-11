"""Music slash commands. Thin handlers that delegate to MusicManager; the
control buttons in views.py call the same manager methods."""
import discord
from discord import app_commands
from discord.ext import commands

from .. import i18n
from ..config import AUDIO_FILTERS, SLEEP_MAX, SLEEP_MIN
from ..embeds import lyrics_embed, now_playing_embed, queue_embed
from ..i18n import t, user_language
from ..lyrics import fetch_lyrics, guess_artist_title
from ..permissions import dj_or_admin
from ..player import MusicManager
from ..sleep import SleepTimers
from ..track import fmt_time, parse_duration, parse_time
from ..views import SearchView, SleepTimerView


def _is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


def _in_voice(interaction: discord.Interaction) -> bool:
    return interaction.user.voice is not None and interaction.user.voice.channel is not None


async def _reply(interaction: discord.Interaction, key: str, **kwargs) -> None:
    """Send a translated reply in the user's language."""
    await interaction.response.send_message(t(user_language(interaction), key, **kwargs))


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = MusicManager(bot)
        self.sleep_timers = SleepTimers(bot, self.manager)

    async def cog_unload(self):
        self.sleep_timers.cancel_all()

    @i18n.command("play")
    async def play(self, interaction: discord.Interaction, query: str):
        await self._play(interaction, query)

    @i18n.command("search")
    async def search(self, interaction: discord.Interaction, query: str):
        await self._play(interaction, query)

    async def _play(self, interaction: discord.Interaction, query: str):
        lang = user_language(interaction)
        if not _in_voice(interaction):
            await interaction.response.send_message(
                t(lang, "music.not_in_voice_mention", user=interaction.user.mention),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if _is_url(query):
            if await self.manager.ensure_voice(interaction) is None:
                await interaction.followup.send(t(lang, "music.not_in_voice"))
                return
            try:
                track = await self.manager.resolve_youtube(query)
                await self.manager.enqueue(interaction, track)
            except Exception as e:
                print(f"[play] {e!r}")
                await interaction.followup.send(t(lang, "music.play_failed", error=e))
            return

        candidates = await self.manager.search_youtube(query)
        if not candidates:
            await interaction.followup.send(t(lang, "music.no_results"))
            return
        view = SearchView(
            self.manager, candidates, lambda c: self.manager.resolve_youtube(c["url"]), lang
        )
        await interaction.followup.send(t(lang, "music.results", query=query), view=view)

    @i18n.command("playnext")
    @dj_or_admin()
    async def playnext(self, interaction: discord.Interaction, query: str):
        lang = user_language(interaction)
        if not _in_voice(interaction):
            await interaction.response.send_message(
                t(lang, "music.not_in_voice_mention", user=interaction.user.mention),
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        if await self.manager.ensure_voice(interaction) is None:
            await interaction.followup.send(t(lang, "music.not_in_voice"))
            return
        if not _is_url(query):
            candidates = await self.manager.search_youtube(query, n=1)
            if not candidates:
                await interaction.followup.send(t(lang, "music.no_results"))
                return
            query = candidates[0]["url"]
        try:
            track = await self.manager.resolve_youtube(query)
            await self.manager.enqueue(interaction, track, at_front=True)
        except Exception as e:
            print(f"[playnext] {e!r}")
            await interaction.followup.send(t(lang, "music.play_failed", error=e))

    @i18n.command("radio")
    async def radio(self, interaction: discord.Interaction, station_name: str):
        lang = user_language(interaction)
        if not _in_voice(interaction):
            await interaction.response.send_message(t(lang, "music.not_in_voice"), ephemeral=True)
            return

        await interaction.response.defer()
        candidates = await self.manager.search_radio(station_name)
        if not candidates:
            await interaction.followup.send(t(lang, "music.no_station"))
            return

        async def resolver(candidate):
            return self.manager.track_from_station(candidate["station"])

        view = SearchView(self.manager, candidates, resolver, lang)
        await interaction.followup.send(t(lang, "music.stations", query=station_name), view=view)

    @i18n.command("skip")
    @dj_or_admin()
    async def skip(self, interaction: discord.Interaction):
        if self.manager.skip(interaction.guild.id):
            await _reply(interaction, "music.skipped")
        else:
            await _reply(interaction, "music.nothing_playing")

    @i18n.command("pause")
    @dj_or_admin()
    async def pause(self, interaction: discord.Interaction):
        if self.manager.pause(interaction.guild.id):
            await self.manager.refresh_controller(interaction.guild.id)
            await _reply(interaction, "music.paused")
        else:
            await _reply(interaction, "music.nothing_playing")

    @i18n.command("resume")
    @dj_or_admin()
    async def resume(self, interaction: discord.Interaction):
        if self.manager.resume(interaction.guild.id):
            await self.manager.refresh_controller(interaction.guild.id)
            await _reply(interaction, "music.resumed")
        else:
            await _reply(interaction, "music.nothing_paused")

    @i18n.command("shuffle")
    @dj_or_admin()
    async def shuffle(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if len(state.queue) < 2:
            await _reply(interaction, "music.shuffle_too_few")
            return
        count = len(state.queue)
        self.manager.shuffle(interaction.guild.id)
        await _reply(interaction, "music.shuffled", count=count)

    @i18n.command("remove")
    @dj_or_admin()
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, None]):
        track = self.manager.remove(interaction.guild.id, position)
        if track is not None:
            await _reply(interaction, "music.removed", title=track.title)
        else:
            await _reply(interaction, "music.no_track_at_position")

    @i18n.command("clear")
    @dj_or_admin()
    async def clear(self, interaction: discord.Interaction):
        count = self.manager.clear(interaction.guild.id)
        await _reply(interaction, "music.cleared", count=count)

    @i18n.command("queue")
    async def queue(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if state.current is None and not state.queue:
            await _reply(interaction, "music.queue_empty")
            return
        await interaction.response.send_message(
            embed=queue_embed(state, user_language(interaction))
        )

    @i18n.command("nowplaying")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if state.current is None:
            await _reply(interaction, "music.nothing_playing")
            return
        elapsed = state.elapsed(self.bot.loop.time())
        await interaction.response.send_message(
            embed=now_playing_embed(state.current, state, elapsed, user_language(interaction))
        )

    @i18n.command("volume")
    @dj_or_admin()
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        self.manager.set_volume(interaction.guild.id, level / 100)
        await self.manager.refresh_controller(interaction.guild.id)
        await _reply(interaction, "music.volume_set", level=level)

    @i18n.command("loop")
    @dj_or_admin()
    async def loop(self, interaction: discord.Interaction):
        enabled = self.manager.toggle_loop(interaction.guild.id)
        await self.manager.refresh_controller(interaction.guild.id)
        await _reply(interaction, "music.loop_on" if enabled else "music.loop_off")

    @i18n.command("stop")
    @dj_or_admin()
    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self.manager.stop(interaction.guild.id)
            await _reply(interaction, "music.stopped")
        else:
            await _reply(interaction, "music.not_connected")

    @i18n.command("leave")
    @dj_or_admin()
    async def leave(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self.manager.stop(interaction.guild.id)
            await _reply(interaction, "music.left")
        else:
            await _reply(interaction, "music.not_connected")

    @i18n.command("seek")
    @dj_or_admin()
    async def seek(self, interaction: discord.Interaction, position: str):
        lang = user_language(interaction)
        seconds = parse_time(position)
        if seconds is None:
            await interaction.response.send_message(t(lang, "music.seek_bad_time"), ephemeral=True)
            return
        result = self.manager.seek(interaction.guild.id, seconds)
        if result is None:
            await interaction.response.send_message(t(lang, "music.seek_unavailable"))
            return
        await interaction.response.send_message(t(lang, "music.seeked", position=fmt_time(result)))

    @i18n.command("filter")
    @app_commands.choices(
        preset=[app_commands.Choice(name=name, value=name) for name in AUDIO_FILTERS]
    )
    @dj_or_admin()
    async def filter(self, interaction: discord.Interaction, preset: app_commands.Choice[str]):
        lang = user_language(interaction)
        if not self.manager.apply_filter(interaction.guild.id, preset.value):
            await interaction.response.send_message(t(lang, "music.filter_unknown"), ephemeral=True)
            return
        await self.manager.refresh_controller(interaction.guild.id)
        if preset.value == "none":
            await interaction.response.send_message(t(lang, "music.filter_off"))
        else:
            await interaction.response.send_message(t(lang, "music.filter_set", preset=preset.value))

    @i18n.command("move")
    @dj_or_admin()
    async def move(
        self,
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1, None],
        to: app_commands.Range[int, 1, None],
    ):
        track = self.manager.move(interaction.guild.id, position, to)
        if track is None:
            await _reply(interaction, "music.move_invalid")
            return
        await _reply(interaction, "music.moved", title=track.title, position=to)

    @i18n.command("lyrics")
    async def lyrics(self, interaction: discord.Interaction, query: str | None = None):
        lang = user_language(interaction)
        await interaction.response.defer()
        if query:
            artist, title = guess_artist_title(query, None)
        else:
            current = self.manager.state(interaction.guild.id).current
            if current is None:
                await interaction.followup.send(t(lang, "music.lyrics_nothing_playing"))
                return
            artist, title = guess_artist_title(current.title, current.author)
        text = await fetch_lyrics(artist, title)
        if not text:
            await interaction.followup.send(t(lang, "music.lyrics_not_found", title=title or query))
            return
        heading = f"{artist} - {title}" if artist else title
        await interaction.followup.send(embed=lyrics_embed(heading, text))

    @i18n.command("sleep_timer")
    async def sleep_timer(self, interaction: discord.Interaction, time: str | None = None):
        await self._sleep_timer(interaction, time)

    @i18n.command("st")
    async def st(self, interaction: discord.Interaction, time: str | None = None):
        await self._sleep_timer(interaction, time)

    async def _sleep_timer(self, interaction: discord.Interaction, time: str | None):
        lang = user_language(interaction)
        timers = self.sleep_timers
        note = None
        if time is not None:
            if time.strip().lower() in ("off", "cancel", "stop", "0"):
                cancelled = timers.cancel(interaction.guild.id, interaction.user.id)
                await interaction.response.send_message(
                    t(lang, "sleep.cancelled" if cancelled else "sleep.no_timer"), ephemeral=True
                )
                return
            seconds = parse_duration(time)
            if seconds is None:
                await interaction.response.send_message(t(lang, "sleep.bad_time"), ephemeral=True)
                return
            if not _in_voice(interaction):
                await interaction.response.send_message(t(lang, "sleep.join_voice"), ephemeral=True)
                return
            if timers.set(interaction.user, seconds, interaction.channel) != seconds:
                note = t(lang, "sleep.limits", min=SLEEP_MIN // 60, max=SLEEP_MAX // 3600)

        # With a time the timer is already set; the panel then just shows it and
        # allows adjusting. Without one, the panel is how the timer gets set.
        view = SleepTimerView(timers, interaction)
        await interaction.response.send_message(
            note, embed=view.embed(), view=view, ephemeral=True
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Clear state when the bot disconnects, end sleep timers of members who
        leave voice, and leave once no listeners remain in the bot's channel."""
        guild = member.guild
        if member.id == self.bot.user.id:
            if after.channel is None:
                self.manager.drop_state(guild.id)
            return
        if after.channel is None:
            # Leaving voice ends that member's sleep timer.
            self.sleep_timers.cancel(guild.id, member.id)

        # Leave once the last listener (ignoring other bots) leaves our channel.
        voice_client = guild.voice_client
        if (
            voice_client
            and voice_client.channel
            and before.channel == voice_client.channel
            and after.channel != voice_client.channel
            and not any(not m.bot for m in voice_client.channel.members)
        ):
            await self.manager.announce(
                self.manager.state(guild.id), t(self.manager.lang(guild.id), "music.everyone_left")
            )
            await self.manager.stop(guild.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
