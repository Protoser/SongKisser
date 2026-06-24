"""Configuration loaded from the environment."""
import os

from dotenv import load_dotenv

# Load variables from a local .env file if present (no-op in Docker)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


def _parse_ids(raw: str) -> set[int]:
    """Parse a comma/space separated list of Discord user IDs into a set of ints."""
    ids = set()
    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            print(f"WARNING: ignoring invalid BOT_ADMINS entry: {part!r}")
    return ids


# Global bot administrators (Discord user IDs). These users can run every admin
# command in any server. The application owner is always treated as an admin too.
BOT_ADMINS = _parse_ids(os.getenv("BOT_ADMINS", ""))

# Path to the SQLite database that stores per-guild settings. Under Docker this
# should point at a mounted volume so settings survive container restarts.
DATABASE_PATH = os.getenv("SONGKISSER_DB", "songkisser.db")

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

# ffmpeg audio-filter presets exposed by the /filter command. Each value is an
# ffmpeg `-af` filtergraph; "none" disables filtering.
AUDIO_FILTERS = {
    "none": "",
    "bassboost": "bass=g=15,dynaudnorm=f=200",
    "nightcore": "aresample=48000,asetrate=48000*1.25",
    "vaporwave": "aresample=48000,asetrate=48000*0.8",
    "treble": "treble=g=10",
    "8d": "apulsator=hz=0.09",
}
