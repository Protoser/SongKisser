"""The /help command: an overview of every command, in the user's language."""
import re

import discord
from discord.ext import commands

from .. import i18n
from ..embeds import help_embed
from ..i18n import t, user_language
from ..permissions import is_global_admin, is_guild_admin

# Help sections (keys under help.sections in the language files) and the
# commands they list, in order. "admin" is only shown to server admins and
# "maintenance" only to bot admins.
SECTIONS = {
    "playback": (
        "play", "search", "playnext", "radio", "pause", "resume", "skip",
        "seek", "stop", "leave", "nowplaying", "lyrics",
    ),
    "queue": ("queue", "shuffle", "move", "remove", "clear", "loop", "volume", "filter"),
    "sleep": ("sleep_timer", "st"),
    "other": ("help", "fuck"),
    "admin": (
        "join", "forceskip", "forcestop", "config", "setdjrole", "cleardjrole",
        "setdefaultvolume", "setlanguage",
    ),
    "maintenance": ("sync", "reload"),
}

# "[Admin] ..." prefixes in descriptions are redundant inside their own section.
_ROLE_PREFIX = re.compile(r"^\[[^\]]+\]\s*")


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _line(self, key: str, lang: str) -> str:
        command = self.bot.tree.get_command(key)
        command_id = getattr(self.bot, "command_ids", {}).get(key)
        # A command mention is clickable and Discord shows it in the reader's
        # own language; fall back to plain text until commands are synced.
        if command_id:
            label = f"</{key}:{command_id}>"
        else:
            label = f"`/{t(lang, f'commands.{key}.name')}`"

        usage = ""
        for param in command.parameters if command else []:
            name = t(lang, f"commands.{key}.options.{param.name}.name")
            usage += f" `<{name}>`" if param.required else f" `[{name}]`"

        help_key = f"commands.{key}.help"
        text = t(lang, help_key) if i18n.has(lang, help_key) else t(lang, f"commands.{key}.description")
        return f"{label}{usage}: {_ROLE_PREFIX.sub('', text)}"

    @i18n.command("help")
    async def help(self, interaction: discord.Interaction):
        lang = user_language(interaction)
        visible = [
            name
            for name in SECTIONS
            if (name != "admin" or is_guild_admin(interaction))
            and (name != "maintenance" or is_global_admin(self.bot, interaction.user.id))
        ]
        sections = [
            (t(lang, f"help.sections.{name}"), [self._line(key, lang) for key in SECTIONS[name]])
            for name in visible
        ]
        footer = t(lang, "help.footer", language=i18n.language_name(lang))
        await interaction.response.send_message(
            embed=help_embed(lang, sections, footer), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
