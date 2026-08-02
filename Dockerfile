# syntax=docker/dockerfile:1

# --- Base image ---------------------------------------------------------
# python:3.11-slim: matches our local dev Python version (Phase 3) and
# is a Debian-based minimal image -- small, but still has apt-get
# available for installing ffmpeg.
FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffering stdout/stderr --
# the latter matters so `docker compose logs` shows output immediately
# instead of holding it in a buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- System dependencies -------------------------------------------------
# ffmpeg is required by yt-dlp for audio extraction (MP3) and merging
# separate video/audio streams into a single MP4. Installed via apt-get
# since it's a system binary, not a Python package.
#
# This layer is placed BEFORE copying application code so Docker can
# cache it -- rebuilding after an app.py change won't reinstall ffmpeg.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies --------------------------------------------------
# Copy ONLY requirements.txt first (not the whole project) so this layer
# is cached and skipped on rebuilds unless dependencies actually change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ------------------------------------------------------
# Copied last, since this changes most frequently during development --
# keeps earlier (slower) layers cached across rebuilds.
COPY . .

# --- Non-root user ---------------------------------------------------------
# Running as root inside a container is unnecessary risk. Even for a
# LAN-only tool, this is a baseline container security practice.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Document which port the container listens on. This is informational
# for anyone reading the Dockerfile -- docker-compose.yml still needs
# its own explicit port mapping to actually expose it.
EXPOSE 5000

CMD ["python", "app.py"]