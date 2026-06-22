# SongKisser

A Discord music bot that plays YouTube audio and internet radio stations in voice channels.

## Commands

| Command | Description |
| --- | --- |
| `/play <url>` | Queue and play a YouTube song |
| `/search <station_name>` | Search and play an internet radio station |
| `/skip` | Skip the current song/stream |
| `/stop` | Stop playback and clear the queue |

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

## Running without Docker

Requires Python 3.13+ and `ffmpeg` installed on your system.

```bash
pip install -r requirements.txt
export DISCORD_TOKEN=your-discord-bot-token-here   # Windows: set DISCORD_TOKEN=...
python main.py
```

## Configuration

| Variable | Description |
| --- | --- |
| `DISCORD_TOKEN` | **Required.** Your Discord bot token. |
