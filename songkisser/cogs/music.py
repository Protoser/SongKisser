"""Music slash commands. Thin handlers that delegate to MusicManager; the
control buttons in views.py call the same manager methods."""
import discord
from discord import app_commands
from discord.ext import commands

from ..embeds import now_playing_embed, queue_embed
from ..player import MusicManager
from ..views import SearchView


def _is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


def _in_voice(interaction: discord.Interaction) -> bool:
    return interaction.user.voice is not None and interaction.user.voice.channel is not None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = MusicManager(bot)

    @app_commands.command(name="play", description="Play a YouTube song or search term")
    @app_commands.describe(query="A YouTube link or search term")
    async def play(self, interaction: discord.Interaction, query: str):
        if not _in_voice(interaction):
            await interaction.response.send_message(
                f"{interaction.user.mention}, you're not connected to a voice channel!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if _is_url(query):
            if await self.manager.ensure_voice(interaction) is None:
                await interaction.followup.send("You're not connected to a voice channel!")
                return
            try:
                track = await self.manager.resolve_youtube(query)
                await self.manager.enqueue(interaction, track)
            except Exception as e:
                print(f"[play] {e!r}")
                await interaction.followup.send(f"Couldn't play that: `{e}`")
            return

        candidates = await self.manager.search_youtube(query)
        if not candidates:
            await interaction.followup.send("No results found.")
            return
        view = SearchView(self.manager, candidates, lambda c: self.manager.resolve_youtube(c["url"]))
        await interaction.followup.send(f"🔎 Results for **{query}**:", view=view)

    @app_commands.command(name="search", description="Search and play an internet radio station")
    @app_commands.describe(station_name="The name of the radio station to search")
    async def search(self, interaction: discord.Interaction, station_name: str):
        if not _in_voice(interaction):
            await interaction.response.send_message(
                "You're not connected to a voice channel!", ephemeral=True
            )
            return

        await interaction.response.defer()
        candidates = await self.manager.search_radio(station_name)
        if not candidates:
            await interaction.followup.send("No station found with that name.")
            return

        async def resolver(candidate):
            return self.manager.track_from_station(candidate["station"])

        view = SearchView(self.manager, candidates, resolver)
        await interaction.followup.send(f"📻 Stations for **{station_name}**:", view=view)

    @app_commands.command(name="skip", description="Skip the current song or stream")
    async def skip(self, interaction: discord.Interaction):
        if self.manager.skip(interaction.guild.id):
            await interaction.response.send_message("⏭️ Skipped.")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @app_commands.command(name="pause", description="Pause the current track")
    async def pause(self, interaction: discord.Interaction):
        if self.manager.pause(interaction.guild.id):
            await self.manager.refresh_controller(interaction.guild.id)
            await interaction.response.send_message("⏸️ Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @app_commands.command(name="resume", description="Resume a paused track")
    async def resume(self, interaction: discord.Interaction):
        if self.manager.resume(interaction.guild.id):
            await self.manager.refresh_controller(interaction.guild.id)
            await interaction.response.send_message("▶️ Resumed.")
        else:
            await interaction.response.send_message("Nothing is paused.")

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if len(state.queue) < 2:
            await interaction.response.send_message("Not enough tracks in the queue to shuffle.")
            return
        count = len(state.queue)
        self.manager.shuffle(interaction.guild.id)
        await interaction.response.send_message(f"🔀 Shuffled {count} tracks.")

    @app_commands.command(name="remove", description="Remove a track from the queue by position")
    @app_commands.describe(position="The queue position to remove (see /queue)")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, None]):
        track = self.manager.remove(interaction.guild.id, position)
        if track is not None:
            await interaction.response.send_message(f"🗑️ Removed **{track.title}**.")
        else:
            await interaction.response.send_message("There's no track at that position.")

    @app_commands.command(name="clear", description="Clear the queue (keeps the current track)")
    async def clear(self, interaction: discord.Interaction):
        count = self.manager.clear(interaction.guild.id)
        await interaction.response.send_message(f"🧹 Cleared {count} tracks from the queue.")

    @app_commands.command(name="queue", description="Show the current queue")
    async def queue(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if state.current is None and not state.queue:
            await interaction.response.send_message("The queue is empty.")
            return
        await interaction.response.send_message(embed=queue_embed(state))

    @app_commands.command(name="nowplaying", description="Show the currently playing track")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self.manager.state(interaction.guild.id)
        if state.current is None:
            await interaction.response.send_message("Nothing is playing.")
            return
        elapsed = state.elapsed(self.bot.loop.time())
        await interaction.response.send_message(
            embed=now_playing_embed(state.current, state, elapsed)
        )

    @app_commands.command(name="volume", description="Set playback volume (0-100)")
    @app_commands.describe(level="Volume from 0 to 100")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        self.manager.set_volume(interaction.guild.id, level / 100)
        await self.manager.refresh_controller(interaction.guild.id)
        await interaction.response.send_message(f"🔊 Volume set to {level}%.")

    @app_commands.command(name="loop", description="Toggle looping of the current track")
    async def loop(self, interaction: discord.Interaction):
        enabled = self.manager.toggle_loop(interaction.guild.id)
        await self.manager.refresh_controller(interaction.guild.id)
        await interaction.response.send_message(
            f"🔁 Loop {'enabled' if enabled else 'disabled'}."
        )

    @app_commands.command(name="stop", description="Stop and clear the queue")
    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self.manager.stop(interaction.guild.id)
            await interaction.response.send_message("⏹️ Stopped and cleared the queue.")
        else:
            await interaction.response.send_message("Bot is not connected.")

    @app_commands.command(name="leave", description="Disconnect the bot from voice")
    async def leave(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self.manager.stop(interaction.guild.id)
            await interaction.response.send_message("👋 Left the voice channel.")
        else:
            await interaction.response.send_message("Bot is not connected.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect and clear state if the bot is left alone in a channel."""
        if member.id == self.bot.user.id and after.channel is None:
            self.manager.drop_state(member.guild.id)
            return
        voice_client = member.guild.voice_client
        if voice_client and voice_client.channel and len(voice_client.channel.members) == 1:
            await self.manager.stop(member.guild.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
