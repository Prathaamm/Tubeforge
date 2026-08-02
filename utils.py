"""
utils.py

Pure, stateless helper functions used by the download route:
- URL validation (allowlist-based, structural checks)
- Filename sanitization (defense against path traversal / odd characters)

None of these functions perform network calls or touch the filesystem
beyond what's explicitly asked -- keeping them easy to reason about
and test in isolation.
"""

import re
import uuid
from urllib.parse import urlparse

import config


class InvalidURLError(ValueError):
    """Raised when a submitted URL is not a supported YouTube URL."""


def validate_youtube_url(url: str) -> str:
    """
    Validate that `url` is a well-formed, supported YouTube video URL.

    This is the app's primary defense against garbage/malicious input
    reaching yt-dlp. It intentionally uses an ALLOWLIST of domains
    (config.ALLOWED_DOMAINS) rather than trying to blocklist bad input,
    since allowlists fail safe -- anything not explicitly recognized
    is rejected by default.

    Returns the original URL if valid (unchanged -- we don't rewrite it).
    Raises InvalidURLError with a human-readable reason otherwise.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("Please provide a URL.")

    url = url.strip()

    # Basic length sanity check -- absurdly long input is never a real
    # video URL and isn't worth passing further down the pipeline.
    if len(url) > 2048:
        raise InvalidURLError("That URL is too long to be valid.")

    try:
        parsed = urlparse(url)
    except ValueError:
        raise InvalidURLError("That doesn't look like a valid URL.")

    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError("URL must start with http:// or https://.")

    hostname = (parsed.hostname or "").lower()
    if hostname not in config.ALLOWED_DOMAINS:
        raise InvalidURLError("Only YouTube URLs are supported.")

    # Must contain either a video ID (?v=...) or be a youtu.be short link
    # with a path segment. This rejects bare domain URLs like
    # "https://youtube.com" with nothing to actually download.
    has_watch_id = "v" in _parse_query(parsed.query)
    is_short_link = hostname == "youtu.be" and len(parsed.path.strip("/")) > 0

    if not has_watch_id and not is_short_link:
        raise InvalidURLError("Couldn't find a video in that URL.")

    # Explicitly reject playlist URLs (a URL that points at a playlist
    # rather than a single video). Support requirement: playlists are
    # out of scope for this app and should fail with a clear message
    # rather than silently downloading the first video or hanging.
    #
    # IMPORTANT: only reject when we truly can't identify a specific
    # video. A youtu.be short link carries its video ID in the PATH,
    # not a "v" query param (e.g. youtu.be/abc123?list=PLxyz) -- that
    # is a valid single-video link that happens to also carry playlist
    # context (common when copying a link while watching inside a
    # playlist), and must NOT be rejected just because "list" is present.
    query = _parse_query(parsed.query)
    if "list" in query and not has_watch_id and not is_short_link:
        raise InvalidURLError("Playlist URLs aren't supported -- paste a single video link.")

    return url


def _parse_query(query_string: str) -> dict:
    """Small local helper to parse a query string into a dict without
    pulling in extra imports at module scope for a one-line need."""
    from urllib.parse import parse_qs
    return {k: v for k, v in parse_qs(query_string).items()}


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """
    Turn an arbitrary string (e.g. a video title from YouTube metadata)
    into a filesystem-safe filename.

    Defends against:
    - Path traversal (../../etc/passwd style tricks)
    - Reserved/illegal filesystem characters
    - Excessively long names
    - Leading/trailing whitespace or dots (problematic on Windows)
    """
    if not name:
        name = "download"

    # Strip any directory components -- if a title somehow contains
    # slashes, we only ever keep it as a flat filename, never a path.
    name = name.replace("/", "_").replace("\\", "_")

    # Remove characters that are illegal or risky across Windows/macOS/Linux.
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name)

    # Collapse repeated whitespace and strip leading/trailing whitespace/dots
    # (Windows treats trailing dots/spaces specially and can misbehave).
    name = re.sub(r"\s+", " ", name).strip(" .")

    if not name:
        name = "download"

    return name[:max_length]


def generate_request_id() -> str:
    """
    Generate a UUID4 string used to namespace each download request's
    temporary folder, guaranteeing no collisions between concurrent
    users even if they submit the exact same video at the same moment.
    """
    return uuid.uuid4().hex