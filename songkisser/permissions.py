"""Permission helpers and app-command check decorators.

Admin model (see plan): "global admins" are the IDs in config.BOT_ADMINS plus the
application owner — they can do everything, in every server. "Guild admins" are
global admins or anyone with Discord's Manage Server permission. The DJ gate
restricts disruptive playback commands to a configured role (if any)."""
from __future__ import annotations

import discord
from discord import app_commands

from . import config
from .i18n import t, user_language


def is_global_admin(client: discord.Client, user_id: int) -> bool:
    owner_id = getattr(client, "owner_id", None)
    return user_id in config.BOT_ADMINS or (owner_id is not None and user_id == owner_id)


def is_guild_admin(interaction: discord.Interaction) -> bool:
    if is_global_admin(interaction.client, interaction.user.id):
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.manage_guild or perms.administrator))


def dj_allowed(interaction: discord.Interaction) -> bool:
    if is_guild_admin(interaction):
        return True
    settings = getattr(interaction.client, "settings", None)
    if settings is None or interaction.guild is None:
        return True
    dj_role_id = settings.get(interaction.guild.id).dj_role_id
    if dj_role_id is None:
        return True  # no DJ role configured -> everyone may control playback
    roles = getattr(interaction.user, "roles", [])
    return any(role.id == dj_role_id for role in roles)


def bot_admin():
    """Global bot admins / application owner only (maintenance commands)."""
    def predicate(interaction: discord.Interaction) -> bool:
        if is_global_admin(interaction.client, interaction.user.id):
            return True
        raise app_commands.CheckFailure(t(user_language(interaction), "errors.bot_admin_only"))

    return app_commands.check(predicate)


def guild_admin():
    """Global admins or members with Manage Server."""
    def predicate(interaction: discord.Interaction) -> bool:
        if is_guild_admin(interaction):
            return True
        raise app_commands.CheckFailure(
            t(user_language(interaction), "errors.manage_server_required")
        )

    return app_commands.check(predicate)


def dj_or_admin():
    """Anyone, unless a DJ role is configured — then only DJs/admins."""
    def predicate(interaction: discord.Interaction) -> bool:
        if dj_allowed(interaction):
            return True
        raise app_commands.CheckFailure(t(user_language(interaction), "errors.dj_only"))

    return app_commands.check(predicate)
