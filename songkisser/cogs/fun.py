"""Novelty commands."""
import asyncio

import discord
from discord.ext import commands

from .. import i18n
from ..i18n import t, user_language


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @i18n.command("fuck")
    async def fuck(self, interaction: discord.Interaction):
        lang = user_language(interaction)
        await interaction.response.send_message(t(lang, "fun.line1"))
        await asyncio.sleep(5)
        await interaction.followup.send(t(lang, "fun.line2"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
