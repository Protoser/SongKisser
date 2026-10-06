FROM python:3.13-slim

# ffmpeg is required by discord.py for audio playback; libopus0 for voice encoding
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY songkisser ./songkisser
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# The bot runs as a non-root user. The entrypoint starts as root only to make
# the database directory writable (volumes are created owned by root), then
# drops to appuser.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

# Keep the settings database on /data so it can be mounted as a volume
ENV SONGKISSER_DB=/data/songkisser.db
VOLUME /data

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-u", "main.py"]
