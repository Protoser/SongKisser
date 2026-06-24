# SongKisser

A Discord music bot that plays YouTube audio and internet radio stations in voice
channels, with a live "Now Playing" panel, artwork, and interactive buttons.

## Commands

| Command | Description |
| --- | --- |
| `/play <link or search>` | Play a YouTube link, or search and pick from a dropdown |
| `/playnext <link or search>` | Add a song to the **front** of the queue |
| `/search <station_name>` | Search internet radio and pick a station from a dropdown |
| `/queue` | Show the queue |
| `/nowplaying` | Show the current track with a progress bar |
| `/skip` | Skip the current song/stream |
| `/pause` · `/resume` | Pause or resume playback |
| `/seek <time>` | Jump to a position in the current track (e.g. `1:30` or `90`) |
| `/shuffle` | Shuffle the queue |
| `/move <from> <to>` | Reorder a track within the queue |
| `/remove <position>` | Remove a track from the queue |
| `/clear` | Clear the queue (keeps the current track) |
| `/volume <0-100>` | Set the playback volume |
| `/filter <preset>` | Apply an audio effect (bassboost, nightcore, vaporwave, treble, 8d, none) |
| `/loop` | Toggle looping of the current track |
| `/lyrics [query]` | Show lyrics for the current song (or a given `Artist - Title`) |
| `/stop` · `/leave` | Stop and disconnect |

The **Now Playing** message updates live with a progress bar and carries buttons
(pause/resume, skip, stop, loop, shuffle, queue, and a link to the source) so you
can control playback without typing commands.

### Admin commands

Available to **global bot admins** (see `BOT_ADMINS`) and anyone with Discord's
**Manage Server** permission:

| Command | Description |
| --- | --- |
| `/join [channel]` | Make the bot join a specific voice channel (or yours) |
| `/forceskip` · `/forcestop` | Override playback regardless of who's in voice |
| `/config` | Show this server's settings |
| `/setdjrole <role>` · `/cleardjrole` | Restrict playback control to a DJ role |
| `/setdefaultvolume <0-100>` | Set the starting volume for new sessions |

**Maintenance** (global bot admins / application owner only):

| Command | Description |
| --- | --- |
| `/sync` | Re-sync the slash command tree |
| `/reload <cog>` | Hot-reload a cog without restarting the bot |

When a **DJ role** is configured, only members with that role (and admins) can use
the playback-control commands and the Now Playing buttons; `/play`, `/search`,
`/queue`, `/nowplaying`, and `/lyrics` stay open to everyone. With no DJ role set,
everything is open — the default behaviour.

## Running with Docker Compose

The bot is published as a container image to GitHub Container Registry (GHCR).

1. **Create a Discord bot** at the [Discord Developer Portal](https://discord.com/developers/applications) and copy its token. Enable the **Message Content** and **Server Members** / voice intents.

2. **Grab the compose file and environment template:**

   ```bash
   curl -O https://raw.githubusercontent.com/Protoser/SongKisser/main/docker-compose.yml
   curl -o .env https://raw.githubusercontent.com/Protoser/SongKisser/main/.env.example
   ```

3. **Fill in `.env`** — your Discord token, and the (lowercase) repo for the image tag:

   ```env
   DISCORD_TOKEN=your-discord-bot-token-here
   GITHUB_REPOSITORY=protoser/songkisser
   ```

   Compose reads these from `.env` automatically: `GITHUB_REPOSITORY` selects the
   `ghcr.io/<repo>:latest` image, and `DISCORD_TOKEN` is passed into the container.

4. **Authenticate to GHCR** (the package is private, so a GitHub token with `read:packages` is required):

   ```bash
   echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
   ```

5. **Start the bot:**

   ```bash
   docker compose up -d
   ```

   View logs with `docker compose logs -f`, and stop with `docker compose down`.

## Building locally

If you'd rather build the image yourself, edit `docker-compose.yml` to comment out the `image:` line and uncomment `build: .`, then run:

```bash
docker compose up -d --build
```

## Running without Docker (development)

This is the quickest way to test changes. Requires Python 3.13+ and `ffmpeg`
installed and on your `PATH`.

The helper scripts create a virtualenv (first run only), install dependencies,
and start the bot:

```bash
run.bat        # Windows (double-click or run from a terminal)
./run.sh       # macOS / Linux
```

Or do it by hand:

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The bot loads your token from a `.env` file automatically (copy `.env.example`
to `.env` and set `DISCORD_TOKEN`), so there's nothing else to export.

## Configuration

| Variable | Description |
| --- | --- |
| `DISCORD_TOKEN` | **Required.** Your Discord bot token. |
| `BOT_ADMINS` | Optional. Comma-separated Discord user IDs granted global admin access. The application owner is always an admin. |
| `SONGKISSER_DB` | Optional. Path to the SQLite file storing per-guild settings (default `songkisser.db`). Mount this as a volume under Docker for persistence. |
