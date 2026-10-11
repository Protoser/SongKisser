"""Translations. Every user-facing string lives in songkisser/locales/<lang>.json
(one file per language, e.g. en.json, de.json). To add a language, copy en.json
to <code>.json, where <code> is a Discord locale such as "fr" or "es-ES", and
translate the values. Missing keys fall back to English.

Which language is used:
- a server language set by an admin (/setlanguage) wins;
- otherwise replies go out in each user's own Discord language;
- messages everyone sees (Now Playing, announcements) use the server language,
  or the server's Discord locale if none is set.
Command names and descriptions are localized by Discord itself (via the
Translator below), so they always follow each user's Discord language."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANGUAGE = "en"

# language code -> flattened key ("music.skipped") -> text
_strings: dict[str, dict[str, str]] = {}


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


def load() -> None:
    _strings.clear()
    for path in sorted(LOCALES_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            _strings[path.stem] = _flatten(json.load(f))
    if DEFAULT_LANGUAGE not in _strings:
        raise RuntimeError(f"Missing default language file {DEFAULT_LANGUAGE}.json")


load()


def languages() -> list[str]:
    return list(_strings)


def language_name(lang: str) -> str:
    return _strings.get(lang, {}).get("meta.name", lang)


def t(lang: Optional[str], key: str, **kwargs: Any) -> str:
    """Look up `key` in `lang`, falling back to English (and then to the key
    itself), and fill in any {placeholders}."""
    text = _strings.get(lang or DEFAULT_LANGUAGE, {}).get(key)
    if text is None:
        text = _strings[DEFAULT_LANGUAGE].get(key, key)
    return text.format(**kwargs) if kwargs else text


def has(lang: str, key: str) -> bool:
    return key in _strings.get(lang, {}) or key in _strings[DEFAULT_LANGUAGE]


# -- choosing a language ------------------------------------------------------


def from_locale(locale: Any) -> Optional[str]:
    """Map a Discord locale ("de", "en-US", "pt-BR") to a language we have."""
    if locale is None:
        return None
    value = locale.value if isinstance(locale, discord.Locale) else str(locale)
    for candidate in (value, value.split("-")[0]):
        if candidate in _strings:
            return candidate
    return None


def server_override(client: discord.Client, guild: Optional[discord.Guild]) -> Optional[str]:
    """The language an admin set for this server with /setlanguage, if any."""
    settings = getattr(client, "settings", None)
    if settings is None or guild is None:
        return None
    lang = settings.get(guild.id).language
    return lang if lang in _strings else None


def guild_language(client: discord.Client, guild: Optional[discord.Guild]) -> str:
    """Language for messages everyone in the server sees."""
    return (
        server_override(client, guild)
        or from_locale(guild.preferred_locale if guild else None)
        or DEFAULT_LANGUAGE
    )


def user_language(interaction: discord.Interaction) -> str:
    """Language for a reply to this interaction."""
    return (
        server_override(interaction.client, interaction.guild)
        or from_locale(interaction.locale)
        or DEFAULT_LANGUAGE
    )


# -- slash command metadata ---------------------------------------------------


def _text(key: str) -> locale_str:
    """An English string from en.json that Discord translates via Translator."""
    return locale_str(t(DEFAULT_LANGUAGE, key), key=key)


def _options(command: str) -> list[str]:
    prefix = f"commands.{command}.options."
    return sorted(
        {k[len(prefix):].split(".")[0] for k in _strings[DEFAULT_LANGUAGE] if k.startswith(prefix)}
    )


def command(key: str, **kwargs: Any):
    """Like @app_commands.command, but the command's name, description, and its
    options' names and descriptions all come from the language files
    (commands.<key>.* in en.json)."""

    def decorator(func):
        options = _options(key)
        if options:
            func = app_commands.rename(
                **{o: _text(f"commands.{key}.options.{o}.name") for o in options}
            )(func)
            func = app_commands.describe(
                **{o: _text(f"commands.{key}.options.{o}.description") for o in options}
            )(func)
        return app_commands.command(
            name=_text(f"commands.{key}.name"),
            description=_text(f"commands.{key}.description"),
            **kwargs,
        )(func)

    return decorator


def choice(key: str, value: Any) -> app_commands.Choice:
    """An option choice whose label comes from the language files."""
    return app_commands.Choice(name=_text(key), value=value)


class Translator(app_commands.Translator):
    """Hands Discord the translated command names/descriptions for every
    language we have a file for."""

    async def translate(
        self,
        string: locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> Optional[str]:
        key = string.extras.get("key")
        lang = from_locale(locale)
        if key is None or lang is None or lang == DEFAULT_LANGUAGE:
            return None
        return _strings[lang].get(key)
