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
import threading

from flask import Flask, render_template, request, jsonify, Response

import config
import downloader
import jobs
from utils import validate_youtube_url, InvalidURLError

app = Flask(__name__)

# Log to the console. In Docker this is exactly what you want --
# `docker compose logs` will surface these lines. We never send this
# level of detail back to the client, only to server-side logs.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")


@app.route("/health")
def health():
    """
    Simple health check endpoint.

    Useful for confirming the server is up -- e.g. when testing from
    another device on the network, or later for Docker's healthcheck.
    """
    return {"status": "ok"}, 200


@app.route("/formats", methods=["POST"])
def formats():
    """
    Given a URL, return a preview of the video: title, thumbnail URL,
    and the distinct video qualities (heights) actually available for
    it, e.g. {"title": "...", "thumbnail": "...", "qualities": [1080, 720]}.

    Read-only / metadata-only -- no file is downloaded here. Used by
    the frontend to show a video preview card and populate the quality
    dropdown before the user commits to an actual download.
    """
    payload = request.get_json(silent=True) or {}
    raw_url = payload.get("url", "")

    try:
        url = validate_youtube_url(raw_url)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        preview = downloader.get_video_preview(url)
    except downloader.DownloaderError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception:
        logger.exception("Unexpected error fetching video preview")
        return jsonify({"error": "Could not fetch video information."}), 500

    return jsonify(preview), 200


def _run_download_job(job_id: str, url: str, media_format: str, quality) -> None:
    """
    Runs in a background thread. Performs the actual download and
    updates the shared job store as progress happens, so
    /jobs/<id>/progress can report real, live status to the browser.
    """
    def on_progress(percent, status):
        jobs.JOB_STORE.update(job_id, percent=percent, status=status)

    jobs.JOB_STORE.update(job_id, status="downloading", percent=0.0)

    try:
        result = downloader.download(url, media_format, quality, on_progress=on_progress)
    except downloader.DownloaderError as exc:
        logger.info("Download job failed (%s): %s", type(exc).__name__, exc)
        jobs.JOB_STORE.update(job_id, status="error", error=str(exc))
        return
    except Exception:
        logger.exception("Unexpected error during background download job")
        jobs.JOB_STORE.update(job_id, status="error", error="An unexpected server error occurred.")
        return

    jobs.JOB_STORE.update(
        job_id, status="done", percent=100.0, result=result, media_format=media_format
    )


@app.route("/jobs", methods=["POST"])
def create_job():
    """
    Validate the submitted URL/format/quality, then START a background
    download job and return immediately with a job_id. The browser
    polls /jobs/<job_id>/progress for real progress, then fetches
    /jobs/<job_id>/result once done.

    This replaces the old synchronous /download endpoint -- the old
    approach blocked the whole request until the download finished,
    which meant the browser had no way to know real progress.
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

    job_id = jobs.JOB_STORE.create()

    # daemon=True: if the main process exits, this thread won't block
    # shutdown. The download itself may still be interrupted mid-way,
    # which is an acceptable trade-off for a personal LAN tool -- a
    # graceful "finish in-flight downloads on shutdown" mechanism would
    # add real complexity for a marginal benefit here.
    thread = threading.Thread(
        target=_run_download_job,
        args=(job_id, url, media_format, quality),
        daemon=True,
    )
    thread.start()

    # 202 Accepted: the request is valid and processing has started,
    # but isn't finished -- exactly what this status code means.
    return jsonify({"job_id": job_id}), 202


@app.route("/jobs/<job_id>/progress")
def job_progress(job_id):
    """Poll endpoint: returns the current status/percent of a job."""
    job = jobs.JOB_STORE.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown or expired job."}), 404

    response_data = {
        "status": job["status"],
        "percent": round(job["percent"], 1),
    }
    if job["status"] == "error":
        response_data["error"] = job["error"]
    return jsonify(response_data), 200


@app.route("/jobs/<job_id>/result")
def job_result(job_id):
    """
    Fetch the finished file for a completed job. Reads it into memory,
    deletes the temp folder immediately, then removes the job from the
    store -- mirroring the same deterministic cleanup approach we used
    for the old synchronous /download endpoint.
    """
    job = jobs.JOB_STORE.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown or expired job."}), 404

    if job["status"] == "error":
        return jsonify({"error": job["error"]}), 422

    if job["status"] != "done":
        # 425 Too Early: the client asked for a result before the job
        # actually finished -- shouldn't normally happen since the
        # frontend only calls this after seeing status="done", but
        # guards against a race or a misbehaving client.
        return jsonify({"error": "Job is not finished yet."}), 425

    result = job["result"]

    try:
        file_bytes = result.file_path.read_bytes()
    except Exception:
        logger.exception("Failed to read downloaded file from disk")
        downloader._cleanup_dir(result.request_dir)
        jobs.JOB_STORE.delete(job_id)
        return jsonify({"error": "Failed to prepare the downloaded file."}), 500

    downloader._cleanup_dir(result.request_dir)
    jobs.JOB_STORE.delete(job_id)

    mimetype = "video/mp4" if job.get("media_format") == "mp4" else "audio/mpeg"
    response = Response(file_bytes, mimetype=mimetype)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{result.display_filename}"'
    )
    response.headers["Content-Length"] = str(len(file_bytes))
    return response


if __name__ == "__main__":
    # host=0.0.0.0 is required so other devices on the same Wi-Fi
    # network can reach this server -- 127.0.0.1 would only be
    # reachable from this machine.
    #
    # threaded=True is CRITICAL now: downloads run in a background
    # thread (see /jobs), and the browser polls /jobs/<id>/progress
    # WHILE that download is still running. Without threaded=True,
    # Werkzeug's dev server handles one request at a time -- a
    # progress-poll request would simply queue up and wait until the
    # download finished, defeating the entire point of polling.
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)