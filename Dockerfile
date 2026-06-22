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

# Run as a non-root user
RUN useradd --create-home --uid 1000 appuser
USER appuser

CMD ["python", "-u", "main.py"]
