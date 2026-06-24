"""Interactive components: the Now Playing controls and the search picker."""
from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Optional

import discord

from .embeds import now_playing_embed, queue_embed
from .permissions import dj_allowed
from .track import Track

if TYPE_CHECKING:
    from .player import MusicManager


class PlayerControls(discord.ui.View):
    """Buttons attached to the live Now Playing message. Buttons and slash
    commands both funnel through the same MusicManager methods."""

    def __init__(self, manager: "MusicManager", guild_id: int, track: Track):
        super().__init__(timeout=None)
        self.manager = manager
        self.guild_id = guild_id

        self.pause_btn = self._button("⏸️", discord.ButtonStyle.primary, self._pause_resume)
        self._button("⏭️", discord.ButtonStyle.secondary, self._skip)
        self._button("⏹️", discord.ButtonStyle.danger, self._stop)
        self.loop_btn = self._button("🔁", discord.ButtonStyle.secondary, self._loop)
        self._button("🔀", discord.ButtonStyle.secondary, self._shuffle)
        self._button("🔉", discord.ButtonStyle.secondary, self._vol_down, row=1)
        self._button("🔊", discord.ButtonStyle.secondary, self._vol_up, row=1)
        self._button("📋", discord.ButtonStyle.secondary, self._queue, label="Queue", row=1)

        if track.url:
            self.add_item(discord.ui.Button(label="Source", url=track.url, row=1))

        self._sync_visuals()

    def _button(self, emoji, style, callback, *, label=None, row=0) -> discord.ui.Button:
        button = discord.ui.Button(emoji=emoji, label=label, style=style, row=row)
        button.callback = callback
        self.add_item(button)
        return button

    def _sync_visuals(self) -> None:
        state = self.manager.state(self.guild_id)
        paused = state.paused_since is not None
        self.pause_btn.emoji = "▶️" if paused else "⏸️"
        self.loop_btn.style = (
            discord.ButtonStyle.success if state.loop else discord.ButtonStyle.secondary
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        voice = interaction.guild.voice_client
        user_voice = interaction.user.voice
        if not (voice and user_voice and user_voice.channel == voice.channel):
            await interaction.response.send_message(
                "Join my voice channel to use the controls.", ephemeral=True
            )
            return False
        # Mirror the slash-command DJ gate: if a DJ role is set, only DJs/admins
        # may drive the live controls.
        if not dj_allowed(interaction):
            await interaction.response.send_message(
                "Only members with the DJ role (or server admins) can use these controls.",
                ephemeral=True,
            )
            return False
        return True

    async def _update_panel(self, interaction: discord.Interaction) -> None:
        state = self.manager.state(self.guild_id)
        if state.current is None:
            await interaction.response.edit_message(view=None)
            return
        self._sync_visuals()
        elapsed = state.elapsed(self.manager.bot.loop.time())
        await interaction.response.edit_message(
            embed=now_playing_embed(state.current, state, elapsed), view=self
        )

    async def _pause_resume(self, interaction: discord.Interaction) -> None:
        self.manager.toggle_pause(self.guild_id)
        await self._update_panel(interaction)

    async def _skip(self, interaction: discord.Interaction) -> None:
        self.manager.skip(self.guild_id)
        await interaction.response.defer()  # the next track posts its own controller

    async def _stop(self, interaction: discord.Interaction) -> None:
        await self.manager.stop(self.guild_id)
        await interaction.response.edit_message(view=None)

    async def _loop(self, interaction: discord.Interaction) -> None:
        self.manager.toggle_loop(self.guild_id)
        await self._update_panel(interaction)

    async def _shuffle(self, interaction: discord.Interaction) -> None:
        self.manager.shuffle(self.guild_id)
        await interaction.response.send_message("🔀 Shuffled the queue.", ephemeral=True)

    async def _vol_down(self, interaction: discord.Interaction) -> None:
        self.manager.volume_down(self.guild_id)
        await self._update_panel(interaction)

    async def _vol_up(self, interaction: discord.Interaction) -> None:
        self.manager.volume_up(self.guild_id)
        await self._update_panel(interaction)

    async def _queue(self, interaction: discord.Interaction) -> None:
        state = self.manager.state(self.guild_id)
        await interaction.response.send_message(embed=queue_embed(state), ephemeral=True)


class SearchView(discord.ui.View):
    """A dropdown of search results (YouTube or radio). The resolver turns the
    chosen candidate into a Track, which is then enqueued."""

    def __init__(
        self,
        manager: "MusicManager",
        candidates: list[dict],
        resolver: Callable[[dict], Awaitable[Optional[Track]]],
    ):
        super().__init__(timeout=30)
        self.manager = manager
        self.candidates = candidates
        self.resolver = resolver

        options = [
            discord.SelectOption(
                label=(c.get("label") or "Unknown")[:100],
                description=(c.get("description") or "")[:100],
                value=str(i),
            )
            for i, c in enumerate(candidates)
        ]
        self.select = discord.ui.Select(placeholder="Pick a result…", options=options)
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

        candidate = self.candidates[int(self.select.values[0])]
        try:
            track = await self.resolver(candidate)
        except Exception as e:
            print(f"[search] resolve failed: {e!r}")
            track = None
        if track is None:
            await interaction.followup.send("Couldn't load that result.", ephemeral=True)
            return

        if await self.manager.ensure_voice(interaction) is None:
            await interaction.followup.send(
                "You're not connected to a voice channel!", ephemeral=True
            )
            return
        await self.manager.enqueue(interaction, track)
        self.stop()
