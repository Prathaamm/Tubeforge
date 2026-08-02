"""
app.py

Flask application entry point.

Routes stay intentionally thin: validate input, delegate to
downloader.py for the actual work, translate errors into friendly
JSON responses, and clean up temp files afterward. The heavy lifting
lives in downloader.py (yt-dlp integration) and utils.py (validation /
sanitization helpers).
"""

import logging

from flask import Flask, render_template, request, jsonify, Response

import config
import downloader
from utils import validate_youtube_url, InvalidURLError

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple health check endpoint."""
    return {"status": "ok"}, 200


@app.route("/formats", methods=["POST"])
def formats():
    """
    Given a URL, return the distinct video qualities (heights) actually
    available for it, e.g. {"qualities": [1080, 720, 480, 360]}.
    Read-only / metadata-only -- no file is downloaded here.
    """
    payload = request.get_json(silent=True) or {}
    raw_url = payload.get("url", "")

    try:
        url = validate_youtube_url(raw_url)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        qualities = downloader.list_qualities(url)
    except downloader.DownloaderError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception:
        logger.exception("Unexpected error listing qualities")
        return jsonify({"error": "Could not fetch available qualities."}), 500

    return jsonify({"qualities": qualities}), 200


@app.route("/download", methods=["POST"])
def download():
    """
    Validate the submitted URL/format/quality, run the download, and
    return the resulting file. Always cleans up the temporary
    per-request folder afterward, whether the request succeeded or
    failed.
    """
    payload = request.get_json(silent=True) or {}
    raw_url = payload.get("url", "")
    media_format = payload.get("format", "mp4")
    raw_quality = payload.get("quality")

    if media_format not in ("mp4", "mp3"):
        return jsonify({"error": "Invalid format requested."}), 400

    quality = None
    if raw_quality not in (None, "", "best"):
        try:
            quality = int(raw_quality)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid quality value."}), 400
        if quality < 1 or quality > 4320:
            return jsonify({"error": "Invalid quality value."}), 400

    try:
        url = validate_youtube_url(raw_url)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        result = downloader.download(url, media_format, quality)
    except downloader.DownloaderError as exc:
        logger.info("Download failed (%s): %s", type(exc).__name__, exc)
        return jsonify({"error": str(exc)}), 422
    except Exception:
        logger.exception("Unexpected error during download")
        return jsonify({"error": "An unexpected server error occurred."}), 500

    try:
        file_bytes = result.file_path.read_bytes()
    except Exception:
        logger.exception("Failed to read downloaded file from disk")
        downloader._cleanup_dir(result.request_dir)
        return jsonify({"error": "Failed to prepare the downloaded file."}), 500

    downloader._cleanup_dir(result.request_dir)

    mimetype = "video/mp4" if media_format == "mp4" else "audio/mpeg"
    response = Response(file_bytes, mimetype=mimetype)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{result.display_filename}"'
    )
    response.headers["Content-Length"] = str(len(file_bytes))
    return response


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)