"""
downloader.py

Wraps yt-dlp's Python API to download a single YouTube video as either
MP4 (video) or MP3 (audio-only).

Progress is calculated across all media streams belonging to the same
download job. This prevents the progress bar from appearing to restart
when yt-dlp moves from the video stream to the audio stream.

Example:

    video: 1.97 MiB / 1.97 MiB
    audio: 2.16 MiB / 4.33 MiB

    overall:
        downloaded = 4.13 MiB
        total      = 6.30 MiB
        progress   = 65.6%

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


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class DownloaderError(Exception):
    """Base class for all download-related errors.

    Carries a message that is safe to show directly to the end user.
    """


class VideoUnavailableError(DownloaderError):
    """Video is private, removed, or otherwise inaccessible."""


class AgeRestrictedError(DownloaderError):
    """Video is age-restricted and cannot be fetched without auth."""


class RegionBlockedError(DownloaderError):
    """Video is not available in the server's region."""


class LiveStreamNotSupportedError(DownloaderError):
    """Live streams aren't supported by this application."""


class VideoTooLongError(DownloaderError):
    """Video exceeds the configured maximum duration."""


class DownloadFailedError(DownloaderError):
    """Generic catch-all for download/conversion failures."""


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

@dataclass
class DownloadResult:
    """What a successful download hands back to the Flask route."""

    file_path: Path
    display_filename: str
    request_dir: Path


# ---------------------------------------------------------------------------
# Cookie configuration
# ---------------------------------------------------------------------------

def _apply_cookie_options(ydl_options: dict) -> None:
    """
    Mutates ydl_options in place to add whichever cookie source is
    configured.

    COOKIES_FILE_PATH takes priority over COOKIES_FROM_BROWSER.
    """

    if config.COOKIES_FILE_PATH:
        ydl_options["cookiefile"] = config.COOKIES_FILE_PATH

    elif config.COOKIES_FROM_BROWSER:
        ydl_options["cookiesfrombrowser"] = (
            config.COOKIES_FROM_BROWSER,
        )


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

def _map_ytdlp_error(exc: Exception) -> DownloaderError:
    """
    Convert yt-dlp errors into friendly application errors.
    """

    message = str(exc).lower()

    if "private video" in message:
        return VideoUnavailableError(
            "This video is private and can't be downloaded."
        )

    if (
        "video unavailable" in message
        or "has been removed" in message
    ):
        return VideoUnavailableError(
            "This video is unavailable or has been removed."
        )

    if (
        "sign in to confirm your age" in message
        or "age-restricted" in message
    ):
        return AgeRestrictedError(
            "This video is age-restricted and can't be downloaded here."
        )

    if (
        "confirm you're not a bot" in message
        or "please sign in" in message
    ):
        return DownloadFailedError(
            "YouTube is blocking this request as a suspected bot. "
            "Try again in a bit, make sure yt-dlp is on the latest "
            "version, or configure COOKIES_FROM_BROWSER in your .env file."
        )

    if (
        "not available in your country" in message
        or "blocked it in your country" in message
    ):
        return RegionBlockedError(
            "This video is blocked in this server's region."
        )

    if (
        "this live event" in message
        or "live stream" in message
    ):
        return LiveStreamNotSupportedError(
            "Live streams aren't supported -- try again after it ends."
        )

    if (
        "unable to download webpage" in message
        or "failed to resolve" in message
        or "network" in message
    ):
        return DownloadFailedError(
            "Network error while reaching YouTube. "
            "Check the server's internet connection."
        )

    return DownloadFailedError(
        "Couldn't download this video. It may be unsupported "
        "or temporarily unavailable."
    )


# ---------------------------------------------------------------------------
# Video preview
# ---------------------------------------------------------------------------

def get_video_preview(url: str) -> dict:
    """
    Inspect a video's metadata without downloading it.

    Returns:

        {
            "title": "...",
            "thumbnail": "...",
            "qualities": [2160, 1080, 720, 480]
        }
    """

    ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    _apply_cookie_options(ydl_options)

    try:
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

    except yt_dlp.utils.DownloadError as exc:
        raise _map_ytdlp_error(exc)

    except Exception as exc:
        raise DownloadFailedError(
            "Could not fetch video information."
        ) from exc

    if info.get("is_live"):
        raise LiveStreamNotSupportedError(
            "Live streams aren't supported -- try again after the stream ends."
        )

    heights = set()

    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")

        if (
            height
            and vcodec
            and vcodec != "none"
        ):
            heights.add(int(height))

    return {
        "title": info.get("title") or "Untitled video",
        "thumbnail": info.get("thumbnail"),
        "qualities": sorted(
            heights,
            reverse=True
        ),
    }


# ---------------------------------------------------------------------------
# yt-dlp options
# ---------------------------------------------------------------------------

def _build_ydl_options(
    output_template: str,
    media_format: str,
    quality: int = None
) -> dict:
    """
    Build the yt-dlp options dict for the requested format.
    """

    common_options = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,

        # Download multiple fragments concurrently where possible.
        "concurrent_fragment_downloads": 4,
    }

    _apply_cookie_options(common_options)

    # Optional aria2c support.
    if config.USE_ARIA2C:
        common_options["external_downloader"] = "aria2c"

        common_options["external_downloader_args"] = {
            "aria2c": [
                "-x",
                "16",
                "-s",
                "16",
                "-k",
                "1M",
            ]
        }

    # -----------------------------------------------------------------------
    # MP3
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # MP4
    # -----------------------------------------------------------------------

    if quality:
        format_string = (
            f"bestvideo[height<={quality}][ext=mp4]"
            f"+bestaudio[ext=m4a]"
            f"/best[height<={quality}][ext=mp4]"
            f"/best[height<={quality}]"
        )

    else:
        format_string = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/best[ext=mp4]/best"
        )

    return {
        **common_options,

        "format": format_string,

        "merge_output_format": "mp4",
    }


# ---------------------------------------------------------------------------
# Aggregate progress calculator
# ---------------------------------------------------------------------------

class AggregateProgress:
    """
    Tracks progress across multiple yt-dlp media streams.

    yt-dlp may download:

        1. video stream
        2. audio stream

    independently.

    Each stream has its own 0-100% progress.

    Instead of exposing those individual percentages, this class combines
    their byte counts into one overall percentage.

    Example:

        video:
            1.97 / 1.97 MiB

        audio:
            2.16 / 4.33 MiB

        overall:
            4.13 / 6.30 MiB = 65.6%
    """

    def __init__(self):
        # Keyed by the stream's filename.
        #
        # Example:
        #
        # {
        #     "/tmp/video.f248.mp4": {
        #         "downloaded": 123456,
        #         "total": 500000
        #     },
        #
        #     "/tmp/video.f140.m4a": {
        #         "downloaded": 123456,
        #         "total": 300000
        #     }
        # }
        self.streams = {}

        # Prevent the progress percentage from moving backwards due to
        # yt-dlp reporting a late/estimated value.
        self.last_percent = 0.0

    def _stream_key(self, data: dict) -> str:
        """
        Determine which media stream this progress event belongs to.

        yt-dlp normally provides `filename` for download progress.
        """

        filename = (
            data.get("filename")
            or data.get("tmpfilename")
            or data.get("filepath")
            or "unknown-stream"
        )

        return str(filename)

    def update(self, data: dict) -> float:
        """
        Update one stream's byte counters and return the aggregate
        percentage across all known streams.
        """

        key = self._stream_key(data)

        downloaded = data.get("downloaded_bytes")

        if downloaded is None:
            downloaded = 0

        total = (
            data.get("total_bytes")
            or data.get("total_bytes_estimate")
            or 0
        )

        downloaded = max(
            0,
            int(downloaded)
        )

        total = max(
            0,
            int(total)
        )

        # Create/update this stream's state.
        self.streams[key] = {
            "downloaded": downloaded,
            "total": total,
        }

        return self.calculate()


    def mark_finished(self, data: dict) -> float:
        """
        Mark a stream as completely downloaded.

        This is important because yt-dlp's `finished` event may arrive
        with byte values that don't exactly match the final total.
        """

        key = self._stream_key(data)

        downloaded = data.get("downloaded_bytes")

        if downloaded is None:
            downloaded = 0

        total = (
            data.get("total_bytes")
            or data.get("total_bytes_estimate")
            or downloaded
        )

        downloaded = max(
            0,
            int(downloaded)
        )

        total = max(
            0,
            int(total)
        )

        # If total is known, consider this stream fully complete.
        if total > 0:
            downloaded = total

        self.streams[key] = {
            "downloaded": downloaded,
            "total": total,
        }

        return self.calculate()


    def calculate(self) -> float:
        """
        Calculate one aggregate percentage from all known streams.
        """

        total_downloaded = 0
        total_size = 0

        for stream in self.streams.values():
            downloaded = stream["downloaded"]
            total = stream["total"]

            total_downloaded += downloaded

            if total > 0:
                total_size += total

        # If we don't know the total size yet, retain the current
        # percentage instead of jumping back to zero.
        if total_size <= 0:
            return self.last_percent

        percent = (
            total_downloaded
            / total_size
            * 100
        )

        percent = max(
            0.0,
            min(100.0, percent)
        )

        # Never make the UI visually move backwards.
        if percent < self.last_percent:
            percent = self.last_percent

        self.last_percent = percent

        return percent


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download(
    url: str,
    media_format: str,
    quality: int = None,
    on_progress=None
) -> DownloadResult:
    """
    Download `url` in the requested media format.

    For MP4 downloads, video and audio may be downloaded as separate
    streams. AggregateProgress combines those streams into one real
    overall percentage.

    `on_progress` receives:

        on_progress(percent: float, status: str)

    where status is:

        "downloading"
        "converting"
    """

    request_id = generate_request_id()

    request_dir = (
        config.DOWNLOAD_DIR
        / request_id
    )

    request_dir.mkdir(
        parents=True,
        exist_ok=False
    )

    output_template = str(
        request_dir
        / "%(title)s.%(ext)s"
    )

    ydl_options = _build_ydl_options(
        output_template,
        media_format,
        quality
    )


    # -----------------------------------------------------------------------
    # Aggregate progress state
    # -----------------------------------------------------------------------

    aggregate_progress = AggregateProgress()


    # -----------------------------------------------------------------------
    # yt-dlp progress hook
    # -----------------------------------------------------------------------

    def _progress_hook(d: dict) -> None:
        """
        Called by yt-dlp while downloading.

        IMPORTANT:

        Do NOT use:

            downloaded / total

        directly as the application's percentage.

        That value belongs only to the current stream.

        Instead, AggregateProgress combines all streams.
        """

        if on_progress is None:
            return

        status = d.get("status")

        # ---------------------------------------------------------------
        # Active download
        # ---------------------------------------------------------------

        if status == "downloading":

            percent = aggregate_progress.update(d)

            on_progress(
                percent,
                "downloading"
            )

            return


        # ---------------------------------------------------------------
        # One stream finished
        # ---------------------------------------------------------------

        if status == "finished":

            percent = aggregate_progress.mark_finished(d)

            on_progress(
                percent,
                "downloading"
            )

            return


    # -----------------------------------------------------------------------
    # Postprocessor / FFmpeg hook
    # -----------------------------------------------------------------------

    def _postprocessor_hook(d: dict) -> None:
        """
        Called during FFmpeg merging/conversion.
        """

        if on_progress is None:
            return

        status = d.get("status")

        # ---------------------------------------------------------------
        # Conversion started
        # ---------------------------------------------------------------

        if status == "started":

            # Keep the progress near the end while FFmpeg is working.
            conversion_percent = max(
                aggregate_progress.last_percent,
                99.0
            )

            on_progress(
                conversion_percent,
                "converting"
            )

            return


        # ---------------------------------------------------------------
        # Conversion finished
        # ---------------------------------------------------------------

        if status == "finished":

            aggregate_progress.last_percent = 100.0

            on_progress(
                100.0,
                "converting"
            )

            return


    # Register hooks.
    ydl_options["progress_hooks"] = [
        _progress_hook
    ]

    ydl_options["postprocessor_hooks"] = [
        _postprocessor_hook
    ]


    # -----------------------------------------------------------------------
    # Execute download
    # -----------------------------------------------------------------------

    try:

        with yt_dlp.YoutubeDL(
            ydl_options
        ) as ydl:

            # ---------------------------------------------------------------
            # Get metadata first.
            # ---------------------------------------------------------------

            info = ydl.extract_info(
                url,
                download=False
            )

            if info.get("is_live"):
                raise LiveStreamNotSupportedError(
                    "Live streams aren't supported -- try again after the stream ends."
                )


            # ---------------------------------------------------------------
            # Duration limit
            # ---------------------------------------------------------------

            if config.MAX_DURATION_SECONDS is not None:

                duration = (
                    info.get("duration")
                    or 0
                )

                if duration > config.MAX_DURATION_SECONDS:

                    raise VideoTooLongError(
                        f"This video is too long "
                        f"(limit: "
                        f"{config.MAX_DURATION_SECONDS // 60} minutes)."
                    )


            # ---------------------------------------------------------------
            # Actual download
            # ---------------------------------------------------------------

            ydl.process_ie_result(
                info,
                download=True
            )


    except DownloaderError:

        _cleanup_dir(
            request_dir
        )

        raise


    except yt_dlp.utils.DownloadError as exc:

        _cleanup_dir(
            request_dir
        )

        raise _map_ytdlp_error(
            exc
        )


    except Exception as exc:

        _cleanup_dir(
            request_dir
        )

        raise DownloadFailedError(
            "An unexpected error occurred while downloading."
        ) from exc


    # -----------------------------------------------------------------------
    # Find final file
    # -----------------------------------------------------------------------

    produced_files = list(
        request_dir.iterdir()
    )

    if not produced_files:

        _cleanup_dir(
            request_dir
        )

        raise DownloadFailedError(
            "Download finished but no file was produced."
        )


    final_path = produced_files[0]

    safe_display_name = (
        sanitize_filename(
            final_path.stem
        )
        + final_path.suffix
    )


    return DownloadResult(
        file_path=final_path,
        display_filename=safe_display_name,
        request_dir=request_dir,
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup_dir(directory: Path) -> None:
    """
    Best-effort recursive delete of a request's temporary folder.
    """

    if not directory.exists():
        return

    for child in directory.iterdir():

        try:
            child.unlink()

        except OSError as exc:

            logging.getLogger(
                __name__
            ).warning(
                "Could not delete temp file %s: %s",
                child,
                exc
            )

    try:

        directory.rmdir()

    except OSError as exc:

        logging.getLogger(
            __name__
        ).warning(
            "Could not remove temp folder %s: %s",
            directory,
            exc
        )