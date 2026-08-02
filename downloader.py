"""
downloader.py

Wraps yt-dlp's Python API to download a single YouTube video as either
MP4 (video) or MP3 (audio-only).

Design notes:
- Uses yt_dlp.YoutubeDL directly (never subprocess/shell) -- user input
  never touches a shell command.
- Each call gets its own UUID-named temp subfolder, so concurrent
  requests can never collide or overwrite each other's files.
- Raises specific, custom exceptions so app.py can show tailored,
  friendly error messages instead of leaking raw yt-dlp/library errors.
"""

from dataclasses import dataclass
from pathlib import Path
import logging

import yt_dlp

import config
from utils import generate_request_id, sanitize_filename


# --- Custom exception hierarchy -----------------------------------------

class DownloaderError(Exception):
    """Base class for all download-related errors. Carries a message
    that is safe to show directly to the end user."""


class VideoUnavailableError(DownloaderError):
    """Video is private, removed, or otherwise inaccessible."""


class AgeRestrictedError(DownloaderError):
    """Video is age-restricted and cannot be fetched without auth."""


class RegionBlockedError(DownloaderError):
    """Video is not available in the server's region."""


class LiveStreamNotSupportedError(DownloaderError):
    """Live streams aren't supported by this app."""


class VideoTooLongError(DownloaderError):
    """Video exceeds the configured maximum duration."""


class DownloadFailedError(DownloaderError):
    """Generic catch-all for download/conversion failures."""


@dataclass
class DownloadResult:
    """What a successful download hands back to the Flask route."""
    file_path: Path
    display_filename: str
    request_dir: Path  # so the caller can clean up the whole folder


def _map_ytdlp_error(exc: Exception) -> DownloaderError:
    """
    yt-dlp doesn't expose a rich exception hierarchy for every failure
    mode -- most failures surface as yt_dlp.utils.DownloadError with a
    descriptive message. We pattern-match on that message to produce a
    specific, friendly exception instead of a raw library error.
    """
    message = str(exc).lower()

    if "private video" in message:
        return VideoUnavailableError("This video is private and can't be downloaded.")
    if "video unavailable" in message or "has been removed" in message:
        return VideoUnavailableError("This video is unavailable or has been removed.")
    if "sign in to confirm your age" in message or "age-restricted" in message:
        return AgeRestrictedError("This video is age-restricted and can't be downloaded here.")
    if "confirm you're not a bot" in message or "please sign in" in message:
        return DownloadFailedError(
            "YouTube is blocking this request as a suspected bot. Try again in a bit, "
            "make sure yt-dlp is on the latest version, or configure COOKIES_FROM_BROWSER "
            "in your .env file."
        )
    if "not available in your country" in message or "blocked it in your country" in message:
        return RegionBlockedError("This video is blocked in this server's region.")
    if "this live event" in message or "live stream" in message:
        return LiveStreamNotSupportedError("Live streams aren't supported -- try again after it ends.")
    if "unable to download webpage" in message or "failed to resolve" in message or "network" in message:
        return DownloadFailedError("Network error while reaching YouTube. Check the server's internet connection.")

    return DownloadFailedError("Couldn't download this video. It may be unsupported or temporarily unavailable.")


def list_qualities(url: str) -> list:
    """
    Inspect a video's available formats (metadata only, no download)
    and return the distinct video heights (e.g. [2160, 1080, 720, 480])
    actually available for it, sorted from highest to lowest.
    """
    ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    if config.COOKIES_FROM_BROWSER:
        ydl_options["cookiesfrombrowser"] = (config.COOKIES_FROM_BROWSER,)

    try:
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _map_ytdlp_error(exc)
    except Exception as exc:
        raise DownloadFailedError("Could not fetch video information.") from exc

    if info.get("is_live"):
        raise LiveStreamNotSupportedError(
            "Live streams aren't supported -- try again after the stream ends."
        )

    heights = set()
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if height and vcodec and vcodec != "none":
            heights.add(int(height))

    return sorted(heights, reverse=True)


def _build_ydl_options(output_template: str, media_format: str, quality: int = None) -> dict:
    """
    Build the yt_dlp options dict for the requested format.
    media_format is expected to already be validated as "mp4" or "mp3"
    by the Flask route before this is called.
    """
    common_options = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "concurrent_fragment_downloads": 4,
    }

    if config.COOKIES_FROM_BROWSER:
        common_options["cookiesfrombrowser"] = (config.COOKIES_FROM_BROWSER,)

    if media_format == "mp3":
        return {
            **common_options,
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

    if quality:
        format_string = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
            f"/best[height<={quality}][ext=mp4]/best[height<={quality}]"
        )
    else:
        format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    return {
        **common_options,
        "format": format_string,
        "merge_output_format": "mp4",
    }


def download(url: str, media_format: str, quality: int = None) -> DownloadResult:
    """
    Download `url` in the requested `media_format` ("mp4" or "mp3").
    `quality`, if provided, caps the video height for MP4 downloads.
    """
    request_id = generate_request_id()
    request_dir = config.DOWNLOAD_DIR / request_id
    request_dir.mkdir(parents=True, exist_ok=False)

    output_template = str(request_dir / "%(title)s.%(ext)s")
    ydl_options = _build_ydl_options(output_template, media_format, quality)

    try:
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=False)

            if info.get("is_live"):
                raise LiveStreamNotSupportedError(
                    "Live streams aren't supported -- try again after the stream ends."
                )

            duration = info.get("duration") or 0
            if duration > config.MAX_DURATION_SECONDS:
                raise VideoTooLongError(
                    f"This video is too long (limit: {config.MAX_DURATION_SECONDS // 60} minutes)."
                )

            ydl.process_ie_result(info, download=True)

    except DownloaderError:
        _cleanup_dir(request_dir)
        raise
    except yt_dlp.utils.DownloadError as exc:
        _cleanup_dir(request_dir)
        raise _map_ytdlp_error(exc)
    except Exception as exc:
        _cleanup_dir(request_dir)
        raise DownloadFailedError("An unexpected error occurred while downloading.") from exc

    produced_files = list(request_dir.iterdir())
    if not produced_files:
        _cleanup_dir(request_dir)
        raise DownloadFailedError("Download finished but no file was produced.")

    final_path = produced_files[0]
    safe_display_name = sanitize_filename(final_path.stem) + final_path.suffix

    return DownloadResult(
        file_path=final_path,
        display_filename=safe_display_name,
        request_dir=request_dir,
    )


def _cleanup_dir(directory: Path) -> None:
    """Best-effort recursive delete of a request's temp folder."""
    if not directory.exists():
        return
    for child in directory.iterdir():
        try:
            child.unlink()
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "Could not delete temp file %s: %s", child, exc
            )
    try:
        directory.rmdir()
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Could not remove temp folder %s: %s", directory, exc
        )