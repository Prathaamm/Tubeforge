"""
config.py

Centralized configuration for the YouTube Downloader app.
All environment-dependent or reused constants live here so the
rest of the codebase never hardcodes them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file (if present) into the environment.
# In Docker, environment variables are usually injected directly by
# docker-compose.yml instead, so this is mainly for local development.
load_dotenv()

# --- Paths -------------------------------------------------------------

# Absolute path to the project root (folder containing this file).
BASE_DIR = Path(__file__).resolve().parent

# Where downloaded files are temporarily stored before being sent
# to the user and then deleted. Kept inside the project so Docker
# volumes / .gitignore can target it easily.
DOWNLOAD_DIR = BASE_DIR / "downloads"

# --- Server settings -----------------------------------------------------

# Host MUST be 0.0.0.0 so devices on the same Wi-Fi network can connect.
# Overridable via .env, but defaults to the correct value for this project.
HOST = os.getenv("HOST", "0.0.0.0")

# Port the Flask app listens on.
PORT = int(os.getenv("PORT", 5000))

# Debug mode should be OFF by default. Only enable explicitly in local
# development via .env (DEBUG=True) -- never in the Docker image.
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# --- Download / validation settings --------------------------------------

# Only these domains are considered valid YouTube URLs.
# Anything else is rejected before it ever reaches yt-dlp.
ALLOWED_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}

# Maximum allowed video duration in seconds (safety limit to avoid someone
# accidentally -- or maliciously -- triggering a multi-hour download on
# your home network). 3 hours as a sane default; adjust via .env.
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", 3 * 60 * 60))

# Optional: name of a browser to pull YouTube session cookies from
# (e.g. "chrome", "edge", "firefox"). Leave unset/empty to disable.
#
# Why this exists: YouTube sometimes responds with a bot-detection
# "Please sign in" error, especially for repeated requests from the
# same home IP. Reusing cookies from a browser where you're already
# logged into YouTube proves to YouTube this is a real session. This
# only uses cookies already on YOUR machine, for YOUR own account --
# it does not access anyone else's account or bypass DRM.
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "").strip() or None

# Ensure the download directory exists at startup.
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)