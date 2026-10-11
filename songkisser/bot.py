"""Bot construction and startup."""
import shutil

import discord
from discord import app_commands
from discord.ext import commands

from . import config
from .db import SettingsStore
from .i18n import Translator, t, user_language

INITIAL_COGS = (
    "songkisser.cogs.music",
    "songkisser.cogs.fun",
    "songkisser.cogs.admin",
    "songkisser.cogs.help",
)


class SongKisser(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = SettingsStore(config.DATABASE_PATH)
        # Command name -> ID, filled on sync; /help uses it for clickable mentions.
        self.command_ids: dict[str, int] = {}
        self.tree.on_error = self._on_app_command_error

    async def setup_hook(self):
        await self.settings.init()
        await self.tree.set_translator(Translator())
        app_info = await self.application_info()
        self.owner_id = app_info.owner.id
        for cog in INITIAL_COGS:
            await self.load_extension(cog)

    async def sync_commands(self) -> int:
        synced = await self.tree.sync()
        self.command_ids = {command.name: command.id for command in synced}
        return len(synced)

    async def on_ready(self):
        await self.sync_commands()
        admins = ", ".join(map(str, config.BOT_ADMINS)) or "(none configured)"
        print(f"Logged in as {self.user} | owner={self.owner_id} | bot admins: {admins}")

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        lang = user_language(interaction)
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or t(lang, "errors.no_permission")
        else:
            print(f"[command] {interaction.command and interaction.command.name}: {error!r}")
            message = t(lang, "errors.generic")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.DiscordException:
            pass


def run() -> None:
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN environment variable is not set.")

    if shutil.which("ffmpeg") is None:
        print(
            "WARNING: ffmpeg was not found on PATH. Audio playback will fail. "
            "Install ffmpeg (the Docker image already includes it)."
        )

    SongKisser().run(config.DISCORD_TOKEN)
