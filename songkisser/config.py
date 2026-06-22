"""Configuration loaded from the environment."""
import os

from dotenv import load_dotenv

# Load variables from a local .env file if present (no-op in Docker)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# yt-dlp extraction options
YTDL_FORMAT_OPTIONS = {
    "format": "bestaudio/best",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

# Default playback volume (0.0 - 1.0)
DEFAULT_VOLUME = 0.5

# How often (seconds) the live "Now Playing" progress bar is edited
UPDATE_INTERVAL = 10

# Volume step (0.0 - 1.0) applied by the dashboard 🔉/🔊 buttons
VOLUME_STEP = 0.10

# How many results to offer in the search picker
SEARCH_RESULTS = 5
