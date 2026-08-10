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

# Maximum allowed video duration in seconds. Leave unset/empty (the
# default) for NO LIMIT -- videos of any length are allowed. Set a
# number here only if you specifically want to cap download length
# (e.g. to protect a slow connection or limited disk space).
_raw_max_duration = os.getenv("MAX_DURATION_SECONDS", "").strip()
MAX_DURATION_SECONDS = int(_raw_max_duration) if _raw_max_duration else None

# Use aria2c as yt-dlp's external downloader for faster, multi-connection
# downloads. Requires the aria2c binary to be installed and on PATH --
# it's installed automatically inside the Docker image, but NOT on a
# local Windows install unless you add it yourself. Leave False if
# aria2c isn't installed locally.
USE_ARIA2C = os.getenv("USE_ARIA2C", "False").strip().lower() == "true"

# Optional: name of a browser to pull YouTube session cookies from
# (e.g. "chrome", "edge", "firefox"). Leave unset/empty to disable.
#
# Why this exists: YouTube sometimes responds with a bot-detection
# "Please sign in" error, especially for repeated requests from the
# same home IP. Reusing cookies from a browser where you're already
# logged into YouTube proves to YouTube this is a real session. This
# only uses cookies already on YOUR machine, for YOUR own account --
# it does not access anyone else's account or bypass DRM.
#
# KNOWN ISSUE on Windows with Chrome/Edge: these browsers lock their
# cookie database file, even after the window is closed (background
# processes keep it open), which makes this option unreliable. If you
# hit "Could not copy Chrome cookie database", either try "firefox"
# instead (doesn't lock its DB the same way), or use COOKIES_FILE_PATH
# below instead, which is more reliable.
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "").strip() or None

# Optional: path to a cookies.txt file (Netscape format), exported via
# a browser extension like "Get cookies.txt LOCALLY". More reliable
# than COOKIES_FROM_BROWSER on Windows, since it reads a static
# snapshot rather than fighting the browser for a lock on its live
# database. Takes priority over COOKIES_FROM_BROWSER if both are set.
COOKIES_FILE_PATH = os.getenv("COOKIES_FILE_PATH", "").strip() or None

# Ensure the download directory exists at startup.
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)