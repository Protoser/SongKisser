import discord
from discord.ext import commands
from discord import app_commands
from radio_browser import RadioBrowser
import yt_dlp
import asyncio
from collections import defaultdict, deque
import os
from dotenv import load_dotenv

# Load variables from a local .env file if present (no-op in Docker)
load_dotenv()

# Configure the bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Suppress yt_dlp errors
yt_dlp.utils.bug_reports_message = lambda: ''

# Audio options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '-',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data)

# Queue storage
queues = defaultdict(deque)

async def play_next(ctx):
    guild_id = ctx.guild.id
    if queues[guild_id]:
        next_song = queues[guild_id].popleft()
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client is None or not voice_client.is_connected():
            voice_client = await ctx.author.voice.channel.connect()
        voice_client.play(next_song, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        duration = f"{int(next_song.duration // 60)}:{str(int(next_song.duration % 60)).zfill(2)}" if next_song.duration else "Live"
        await ctx.send(f'**Now playing:** {next_song.title} **({duration})**')
    else:
        await ctx.send('Queue ended.')
        await ctx.guild.voice_client.disconnect()

class DummyCtx:
    def __init__(self, guild, author, interaction):
        self.guild = guild
        self.author = author
        self.interaction = interaction

    async def send(self, content=None, **kwargs):
        await self.interaction.followup.send(content=content, **kwargs)

@bot.tree.command(name="play", description="Play a YouTube song")
@app_commands.describe(url="The YouTube link")
async def play(interaction: discord.Interaction, url: str):
    user = interaction.user
    voice_state = user.voice

    if not voice_state or not voice_state.channel:
        await interaction.response.send_message(
            f"{user.mention}, you're not connected to a voice channel!",
            ephemeral=True
        )
        return

    voice_channel = voice_state.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if not voice_client or not voice_client.is_connected():
        voice_client = await voice_channel.connect()

    await interaction.response.defer()

    try:
        player = await YTDLSource.from_url(url, loop=bot.loop)
        queues[interaction.guild.id].append(player)
        msg = f"**Added to queue:** {player.title}"
        await interaction.followup.send(msg)

        if not (voice_client.is_playing() or voice_client.is_paused()):
            dummy_ctx = DummyCtx(interaction.guild, interaction.user, interaction)
            await play_next(dummy_ctx)

    except Exception as e:
        print(e)
        await interaction.followup.send("Couldn't play the song!")

@bot.tree.command(name="search", description="Search and play a radio station by name")
@app_commands.describe(station_name="The name of the radio station to search")
async def search(interaction: discord.Interaction, station_name: str):
    await interaction.response.defer()
    stations = RadioBrowser().search_radio(name=station_name)
    if not stations:
        await interaction.followup.send("No station found with that name.")
        return

    station = stations[0]
    stream_url = station.get("url")
    name = station.get("name")
    
    user = interaction.user
    voice_state = user.voice
    if not voice_state or not voice_state.channel:
        await interaction.followup.send("You're not connected to a voice channel!")
        return

    voice_channel = voice_state.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice_client or not voice_client.is_connected():
        voice_client = await voice_channel.connect()

    source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
    player = YTDLSource(source, data={'title': name, 'url': stream_url, 'duration': 0})
    queues[interaction.guild.id].append(player)
    await interaction.followup.send(f"🎶 **Added stream:** {name}")

    if not (voice_client.is_playing() or voice_client.is_paused()):
        dummy_ctx = DummyCtx(interaction.guild, user, interaction)
        await play_next(dummy_ctx)

@bot.tree.command(name="skip", description="Skip the current song or stream")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped.")
    else:
        await interaction.response.send_message("Nothing is playing.")

@bot.tree.command(name="stop", description="Stop and clear the queue")
async def stop(interaction: discord.Interaction):
    queues[interaction.guild.id].clear()
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await interaction.response.send_message("Stopped and cleared the queue.")
    else:
        await interaction.response.send_message("Bot is not connected.")

@bot.tree.command(name="fuck", description="Get weird with the bot")
async def fuck(interaction: discord.Interaction):
    await interaction.response.send_message("Y- Y- You wanna ... fuck? *blushes*.")
    await asyncio.sleep(5)
    await interaction.followup.send("I wasn't expecting that. *leans in for a kiss*.")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')


if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN environment variable is not set.")

bot.run(DISCORD_TOKEN)
