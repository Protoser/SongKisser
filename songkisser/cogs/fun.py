"""Novelty commands."""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="fuck", description="Get weird with the bot")
    async def fuck(self, interaction: discord.Interaction):
        await interaction.response.send_message("Y- Y- You wanna ... fuck? *blushes*.")
        await asyncio.sleep(5)
        await interaction.followup.send("I wasn't expecting that. *leans in for a kiss*.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
