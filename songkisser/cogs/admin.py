"""Admin and operator commands.

Guild admins (Manage Server, or a global bot admin) can force the bot into a
channel, configure the server, and override playback. Global bot admins / the
application owner additionally get maintenance commands (sync, reload)."""
import discord
from discord import app_commands
from discord.ext import commands

from .. import i18n
from ..embeds import config_embed
from ..i18n import t, user_language
from ..permissions import bot_admin, guild_admin

# Cogs that /reload is allowed to target.
RELOADABLE = ("music", "fun", "admin", "help")


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def manager(self):
        """Share the Music cog's MusicManager so overrides act on live state."""
        music = self.bot.get_cog("Music")
        return music.manager if music else None

    # -- channel / playback overrides ---------------------------------------

    @i18n.command("join")
    @guild_admin()
    async def join(
        self, interaction: discord.Interaction, channel: discord.VoiceChannel | None = None
    ):
        lang = user_language(interaction)
        if channel is None:
            user_voice = interaction.user.voice
            channel = user_voice.channel if user_voice else None
        if channel is None:
            await interaction.response.send_message(
                t(lang, "admin.join_pick_channel"), ephemeral=True
            )
            return
        manager = self.manager
        if manager is None:
            await interaction.response.send_message(
                t(lang, "admin.engine_unavailable"), ephemeral=True
            )
            return
        try:
            await manager.connect_to(channel)
        except discord.DiscordException as e:
            await interaction.response.send_message(
                t(lang, "admin.join_failed", error=e), ephemeral=True
            )
            return
        manager.state(interaction.guild.id).text_channel = interaction.channel
        await interaction.response.send_message(t(lang, "admin.joined", channel=channel.name))

    @i18n.command("forceskip")
    @guild_admin()
    async def forceskip(self, interaction: discord.Interaction):
        lang = user_language(interaction)
        if self.manager and self.manager.skip(interaction.guild.id):
            await interaction.response.send_message(t(lang, "admin.force_skipped"))
        else:
            await interaction.response.send_message(t(lang, "music.nothing_playing"))

    @i18n.command("forcestop")
    @guild_admin()
    async def forcestop(self, interaction: discord.Interaction):
        if self.manager:
            await self.manager.stop(interaction.guild.id)
        await interaction.response.send_message(
            t(user_language(interaction), "admin.force_stopped")
        )

    # -- per-guild configuration --------------------------------------------

    @i18n.command("config")
    @guild_admin()
    async def config(self, interaction: discord.Interaction):
        settings = self.bot.settings.get(interaction.guild.id)
        await interaction.response.send_message(
            embed=config_embed(interaction.guild, settings, user_language(interaction)),
            ephemeral=True,
        )

    @i18n.command("setdjrole")
    @guild_admin()
    async def setdjrole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.settings.set_dj_role(interaction.guild.id, role.id)
        await interaction.response.send_message(
            t(user_language(interaction), "admin.dj_role_set", role=role.mention),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @i18n.command("cleardjrole")
    @guild_admin()
    async def cleardjrole(self, interaction: discord.Interaction):
        await self.bot.settings.set_dj_role(interaction.guild.id, None)
        await interaction.response.send_message(
            t(user_language(interaction), "admin.dj_role_cleared")
        )

    @i18n.command("setdefaultvolume")
    @guild_admin()
    async def setdefaultvolume(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
    ):
        await self.bot.settings.set_default_volume(interaction.guild.id, level / 100)
        await interaction.response.send_message(
            t(user_language(interaction), "admin.default_volume_set", level=level)
        )

    @i18n.command("setlanguage")
    @app_commands.choices(
        language=[i18n.choice("admin.language_option_auto", "auto")]
        + [app_commands.Choice(name=i18n.language_name(lang), value=lang) for lang in i18n.languages()]
    )
    @guild_admin()
    async def setlanguage(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ):
        value = None if language.value == "auto" else language.value
        await self.bot.settings.set_language(interaction.guild.id, value)
        # Reply in the newly chosen language (or the user's own, for automatic).
        lang = user_language(interaction)
        if value is None:
            await interaction.response.send_message(t(lang, "admin.language_cleared"))
        else:
            await interaction.response.send_message(
                t(lang, "admin.language_set", language=i18n.language_name(value))
            )

    # -- bot maintenance (global admins only) -------------------------------

    @i18n.command("sync")
    @bot_admin()
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self.bot.sync_commands()
        await interaction.followup.send(
            t(user_language(interaction), "admin.synced", count=count), ephemeral=True
        )

    @i18n.command("reload")
    @app_commands.choices(cog=[app_commands.Choice(name=c, value=c) for c in RELOADABLE])
    @bot_admin()
    async def reload(self, interaction: discord.Interaction, cog: app_commands.Choice[str]):
        lang = user_language(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"songkisser.cogs.{cog.value}")
        except commands.ExtensionError as e:
            await interaction.followup.send(t(lang, "admin.reload_failed", error=e), ephemeral=True)
            return
        await interaction.followup.send(t(lang, "admin.reloaded", cog=cog.value), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
