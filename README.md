# TubeForge

> **Download. Convert. Play Anywhere.**

TubeForge is a self-hosted, LAN-friendly YouTube media utility built with Flask and yt-dlp. Paste a single YouTube video URL, inspect its available qualities, choose MP4 video or MP3 audio, and download the result from the browser.

It is intentionally simple: **no accounts, no sign-in flow, no ads, and no subscription UI**.

## Highlights

- MP4 video and MP3 audio output
- Video preview with title, thumbnail, and available video qualities
- Background download jobs with live progress polling
- Aggregate progress for MP4 downloads, so video + audio downloads do not make the progress bar jump back to 0%
- Optional FFmpeg-based merging and audio extraction
- Optional aria2 multi-connection downloading
- Optional YouTube cookie support for bot/sign-in related failures
- YouTube URL allowlisting and filename sanitization
- Temporary per-request download directories with cleanup after the result is delivered
- Designed for access from other devices on the same Wi-Fi/LAN
- Docker and Docker Compose support
- Lightweight in-memory job tracking for a single-process deployment

## Documentation

**Printable install and usage guide:**  
[Download the TubeForge Install & Usage Guide (PDF)](docs/TubeForge-Install-Usage-Guide.pdf)

The PDF covers local Windows setup, Docker setup, configuration, LAN access, cookies, troubleshooting, download behavior, and development notes.

---

## Requirements

### Local development

- Python 3.11 recommended
- FFmpeg available on `PATH`
- Internet access to reach YouTube
- A modern browser

The runtime dependencies currently include Flask 3.0.3, yt-dlp 2026.07.04, and python-dotenv 1.0.1.

### Docker

Docker and Docker Compose are required.

The supplied Docker image installs:

- Python 3.11
- FFmpeg
- aria2

The Compose configuration maps host port `5000` to container port `5000`.

---

## Quick Start — Windows / Local Python

### 1. Create and activate the virtual environment

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install FFmpeg

FFmpeg is required for MP4 merging and MP3 extraction.

Make sure this works:

```bash
ffmpeg -version
```

If Windows cannot find `ffmpeg`, install it and add its `bin` directory to `PATH`.

### 4. Configure the application

Copy:

```text
.env.example
```

to:

```text
.env
```

Then adjust values if needed.

A basic local configuration is:

```env
HOST=0.0.0.0
PORT=5000
DEBUG=False
MAX_DURATION_SECONDS=
COOKIES_FROM_BROWSER=
USE_ARIA2C=False
```

The application defaults to binding on `0.0.0.0`, which is required when other devices on the same Wi-Fi network need to connect.

### 5. Start TubeForge

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

For another device on the same LAN, use the host computer's LAN IP:

```text
http://YOUR-PC-IP:5000
```

Example:

```text
http://192.168.88.4:5000
```

If Windows Firewall prompts for access, allow the application on the appropriate private network.

---

## Quick Start — Docker

Build and start:

```bash
docker compose up -d --build
```

Check the container:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Open:

```text
http://127.0.0.1:5000
```

From another device on the same Wi-Fi:

```text
http://YOUR-PC-IP:5000
```

Stop the service:

```bash
docker compose down
```

The provided Compose configuration uses:

```text
5000:5000
```

and restarts the container automatically unless it is explicitly stopped.

---

## Configuration

Configuration is read from environment variables by `config.py`.

| Variable | Default | Purpose |
|---|---:|---|
| `HOST` | `0.0.0.0` | Network interface Flask binds to |
| `PORT` | `5000` | HTTP port |
| `DEBUG` | `False` | Flask debug mode |
| `MAX_DURATION_SECONDS` | blank | Optional maximum video duration |
| `COOKIES_FROM_BROWSER` | blank | Optional browser cookie source |
| `COOKIES_FILE_PATH` | blank | Optional Netscape-format cookie file |
| `USE_ARIA2C` | `False` | Enable aria2 external downloading |

`MAX_DURATION_SECONDS` may be left blank to allow videos of any length.

`COOKIES_FILE_PATH` takes priority over `COOKIES_FROM_BROWSER` when both are configured.

For Docker, the supplied Compose file enables `USE_ARIA2C=True` and installs aria2 in the image.

---

## Cookies and YouTube sign-in errors

Cookies are **optional**.

Use them only if YouTube begins returning errors such as:

```text
Please sign in
```

or suspected-bot errors.

Two supported approaches are:

### Browser cookies

Set, for example:

```env
COOKIES_FROM_BROWSER=firefox
```

Supported browser names documented by the project include:

```text
chrome
edge
firefox
```

On Windows, Chrome/Edge cookie databases can be locked by background browser processes. A static exported Netscape-format cookie file is therefore often more reliable.

### Cookie file

Set:

```env
COOKIES_FILE_PATH=C:\path\to\cookies.txt
```

or the equivalent path for your environment.

**Never commit cookies to Git.** Keep `cookies.txt` in `.gitignore` and `.dockerignore`.

Treat cookie files like credentials. Do not publish them, upload them to GitHub, or include them in screenshots/logs.

---

## How a download works

TubeForge uses a two-stage browser workflow.

### 1. Check Video

The browser sends the URL to:

```text
POST /formats
```

This is metadata-only. It does not download the media.

The server validates the URL, asks yt-dlp for metadata, and returns:

- title
- thumbnail
- available video heights/qualities

### 2. Start Download

The browser submits:

```text
POST /jobs
```

The server creates a background job and immediately returns a job ID.

The browser then polls:

```text
GET /jobs/<job_id>/progress
```

until the job is complete.

Finally it requests:

```text
GET /jobs/<job_id>/result
```

to receive the generated media file.

### Progress behavior

For MP4, yt-dlp may download video and audio as separate streams. TubeForge combines their byte counts into one aggregate percentage rather than exposing each stream's individual percentage.

For example:

```text
video: 1.97 / 1.97 MiB
audio: 2.16 / 4.33 MiB

overall:
4.13 / 6.30 MiB
= 65.6%
```

This prevents the UI from appearing to restart when the audio stream begins.

---

## Supported formats

### MP4 Video

The downloader prefers separate MP4-compatible video and M4A audio streams and merges them into an MP4 where available.

A requested quality such as 1080p is treated as an upper height limit rather than a guarantee that the source contains an exact 1080p stream.

### MP3 Audio

The application downloads the best available audio and uses FFmpeg to extract MP3 at the configured 192 kbps quality.

---

## URL validation

TubeForge accepts only supported YouTube domains:

```text
youtube.com
www.youtube.com
m.youtube.com
youtu.be
```

A URL must identify a specific video. Playlist-only URLs are rejected.

The validation layer also limits excessively long input and sanitizes downloaded filenames to prevent path traversal and invalid filesystem characters.

---

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Main web interface |
| `GET` | `/health` | Health check |
| `POST` | `/formats` | Fetch video metadata and qualities |
| `POST` | `/jobs` | Create a background download job |
| `GET` | `/jobs/<id>/progress` | Read current job status/progress |
| `GET` | `/jobs/<id>/result` | Fetch the completed media file |

A successful job moves through states such as:

```text
queued
  ↓
downloading
  ↓
converting
  ↓
done
```

Failures use:

```text
error
```

---

## Project structure

```text
youtube-downloader/
├── app.py
├── config.py
├── downloader.py
├── jobs.py
├── utils.py
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
├── tests/
│   ├── test_utils.py
│   └── MANUAL_CHECKLIST.md
├── downloads/
└── docs/
    └── TubeForge-Install-Usage-Guide.pdf
```

### Backend responsibilities

- `app.py` — Flask routes, validation, background job creation, progress/result endpoints
- `downloader.py` — yt-dlp integration, FFmpeg processing, cookie handling, aggregate progress, cleanup
- `jobs.py` — thread-safe in-memory job store
- `config.py` — environment-driven configuration
- `utils.py` — URL validation and filename sanitization

### Frontend responsibilities

- `templates/index.html` — application markup
- `static/css/style.css` — TubeForge visual design and responsive layout
- `static/js/script.js` — URL checking, preview rendering, job creation, progress polling, and result download

---

## Job storage and concurrency

Job state is kept in memory in a thread-safe dictionary guarded by `threading.Lock`.

This is appropriate for the intended single-process, LAN-only deployment.

It is **not** a distributed job system. If the application is later deployed behind multiple worker processes, the job store should move to a shared backend such as Redis.

Finished and errored jobs are pruned after their retention period if the browser never collects them.

---

## Testing

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the automated tests:

```bash
pytest
```

The current development requirements include pytest 8.3.2.

The project also contains a manual checklist under:

```text
tests/MANUAL_CHECKLIST.md
```

---

## Troubleshooting

### The page does not load from another device

1. Confirm TubeForge is running.
2. Confirm Flask is bound to `0.0.0.0`.
3. Find the host computer's LAN IP.
4. Open `http://HOST-IP:5000` from the other device.
5. Check Windows Firewall/private-network permissions.

### `ffmpeg` not found locally

Run:

```bash
ffmpeg -version
```

Install FFmpeg and make sure its `bin` directory is on `PATH`.

Docker already installs FFmpeg in the supplied image.

### YouTube says to sign in / suspected bot

Update yt-dlp first:

```bash
pip install --upgrade yt-dlp
```

If the problem continues, configure a browser cookie source or a static cookie file.

### Download progress appears to reset

The backend is designed to aggregate video/audio byte progress. Make sure the current `downloader.py`, `app.py`, `jobs.py`, and frontend JavaScript are all from the same project version.

### Docker changes do not appear

Rebuild the image:

```bash
docker compose down
docker compose up -d --build
```

Then inspect logs:

```bash
docker compose logs -f
```

### A download fails after reaching 100%

The final stage can include FFmpeg merging/conversion and file preparation. Check the server/Docker logs for the actual error.

---

## Privacy and security notes

TubeForge is intended as a self-hosted personal/LAN utility.

- Do not expose the service directly to the public internet without adding appropriate authentication and security controls.
- Keep `.env` files private.
- Keep cookie files private.
- Do not commit `cookies.txt`.
- Do not expose downloaded media directories unnecessarily.
- Keep Flask debug mode disabled for normal operation.
- The application validates YouTube URLs before passing them to yt-dlp.
- User-provided URLs are not passed through a shell command.

---

## Legal / usage note

Use TubeForge only for media you are authorized to download and in accordance with YouTube's terms, applicable copyright law, and any rights associated with the content.

TubeForge is a self-hosted utility and does not grant rights to download or redistribute copyrighted material.

---

## License

No explicit project license is defined in the supplied project files. Add a `LICENSE` file before distributing the project publicly if you want to specify reuse, modification, and redistribution terms.

---

## Current project behavior

The project is intentionally a small utility rather than a platform:

**Paste URL → Check Video → Choose format/quality → Download → Receive file**

There are no accounts, ads, subscriptions, or unnecessary dashboard features.
