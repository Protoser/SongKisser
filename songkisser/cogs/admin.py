"""Admin and operator commands.

Guild admins (Manage Server, or a global bot admin) can force the bot into a
channel, configure the server, and override playback. Global bot admins / the
application owner additionally get maintenance commands (sync, reload)."""
import discord
from discord import app_commands
from discord.ext import commands

from ..embeds import config_embed
from ..permissions import bot_admin, guild_admin

# Cogs that /reload is allowed to target.
RELOADABLE = ("music", "fun", "admin")


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def manager(self):
        """Share the Music cog's MusicManager so overrides act on live state."""
        music = self.bot.get_cog("Music")
        return music.manager if music else None

    # -- channel / playback overrides ---------------------------------------

    @app_commands.command(name="join", description="[Admin] Make the bot join a voice channel")
    @app_commands.describe(channel="The voice channel to join (defaults to yours)")
    @guild_admin()
    async def join(
        self, interaction: discord.Interaction, channel: discord.VoiceChannel | None = None
    ):
        if channel is None:
            user_voice = interaction.user.voice
            channel = user_voice.channel if user_voice else None
        if channel is None:
            await interaction.response.send_message(
                "Pick a voice channel, or join one yourself first.", ephemeral=True
            )
            return
        manager = self.manager
        if manager is None:
            await interaction.response.send_message("Music engine unavailable.", ephemeral=True)
            return
        try:
            await manager.connect_to(channel)
        except discord.DiscordException as e:
            await interaction.response.send_message(f"Couldn't join: `{e}`", ephemeral=True)
            return
        manager.state(interaction.guild.id).text_channel = interaction.channel
        await interaction.response.send_message(f"📡 Joined **{channel.name}**.")

    @app_commands.command(name="forceskip", description="[Admin] Skip the current track")
    @guild_admin()
    async def forceskip(self, interaction: discord.Interaction):
        if self.manager and self.manager.skip(interaction.guild.id):
            await interaction.response.send_message("⏭️ Force-skipped.")
        else:
            await interaction.response.send_message("Nothing is playing.")

    @app_commands.command(name="forcestop", description="[Admin] Stop playback and disconnect")
    @guild_admin()
    async def forcestop(self, interaction: discord.Interaction):
        if self.manager:
            await self.manager.stop(interaction.guild.id)
        await interaction.response.send_message("⏹️ Force-stopped.")

    # -- per-guild configuration --------------------------------------------

    @app_commands.command(name="config", description="[Admin] Show this server's settings")
    @guild_admin()
    async def config(self, interaction: discord.Interaction):
        settings = self.bot.settings.get(interaction.guild.id)
        await interaction.response.send_message(
            embed=config_embed(interaction.guild, settings), ephemeral=True
        )

    @app_commands.command(name="setdjrole", description="[Admin] Restrict playback control to a role")
    @app_commands.describe(role="Members with this role (and admins) may control playback")
    @guild_admin()
    async def setdjrole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.settings.set_dj_role(interaction.guild.id, role.id)
        await interaction.response.send_message(
            f"🎧 DJ role set to {role.mention}. Only DJs and admins can now control playback.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="cleardjrole", description="[Admin] Remove the DJ role restriction")
    @guild_admin()
    async def cleardjrole(self, interaction: discord.Interaction):
        await self.bot.settings.set_dj_role(interaction.guild.id, None)
        await interaction.response.send_message(
            "🎧 DJ role cleared. Everyone can control playback again."
        )

    @app_commands.command(
        name="setdefaultvolume", description="[Admin] Set the starting volume for new sessions"
    )
    @app_commands.describe(level="Default volume from 0 to 100")
    @guild_admin()
    async def setdefaultvolume(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
    ):
        await self.bot.settings.set_default_volume(interaction.guild.id, level / 100)
        await interaction.response.send_message(f"🔊 Default volume set to {level}%.")

    # -- bot maintenance (global admins only) -------------------------------

    @app_commands.command(name="sync", description="[Owner] Re-sync the slash command tree")
    @bot_admin()
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(f"🔄 Synced {len(synced)} commands.", ephemeral=True)

    @app_commands.command(name="reload", description="[Owner] Reload a cog")
    @app_commands.describe(cog="Which cog to reload")
    @app_commands.choices(cog=[app_commands.Choice(name=c, value=c) for c in RELOADABLE])
    @bot_admin()
    async def reload(self, interaction: discord.Interaction, cog: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"songkisser.cogs.{cog.value}")
        except commands.ExtensionError as e:
            await interaction.followup.send(f"Reload failed: `{e}`", ephemeral=True)
            return
        await interaction.followup.send(f"♻️ Reloaded **{cog.value}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
