"""Bot construction and startup."""
import shutil

import discord
from discord.ext import commands

from . import config

INITIAL_COGS = ("songkisser.cogs.music", "songkisser.cogs.fun")


class SongKisser(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        for cog in INITIAL_COGS:
            await self.load_extension(cog)

    async def on_ready(self):
        await self.tree.sync()
        print(f"Logged in as {self.user}")


def run() -> None:
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN environment variable is not set.")

    if shutil.which("ffmpeg") is None:
        print(
            "WARNING: ffmpeg was not found on PATH. Audio playback will fail. "
            "Install ffmpeg (the Docker image already includes it)."
        )

    SongKisser().run(config.DISCORD_TOKEN)
