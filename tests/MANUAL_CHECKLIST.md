\# Phase 9 Manual Testing Checklist



Run all of these against the DOCKER deployment (`docker compose up --build`),

not the local `python app.py` -- this is what actually ships.



\## Setup

\- \[ ] `docker compose up --build` succeeds with no errors

\- \[ ] `http://localhost:5000` loads the UI

\- \[ ] `http://<your-PC-IP>:5000` loads from your phone (same Wi-Fi)



\## Core functionality

\- \[ ] MP4 download at "Best available" quality succeeds

\- \[ ] MP4 download at a specific chosen quality (e.g. 720p) succeeds

&#x20;     and produces a visibly smaller/faster file than "Best available"

\- \[ ] MP3 download succeeds (confirms ffmpeg works inside the container)

\- \[ ] `downloads/` folder is empty after each successful download

\- \[ ] Quality dropdown shows "N qualities found" for a normal video



\## URL validation (should show a friendly red error, not crash)

\- \[ ] Empty URL field

\- \[ ] Non-YouTube URL (e.g. google.com)

\- \[ ] Malformed text ("asdf1234")

\- \[ ] Bare playlist page (youtube.com/playlist?list=PL...)



\## URL edge cases (should be ACCEPTED, not rejected)

\- \[ ] Standard watch URL (youtube.com/watch?v=...)

\- \[ ] youtu.be short link

\- \[ ] Watch URL with playlist context (?v=...\&list=...)

\- \[ ] youtu.be short link with playlist context (?list=...)

\- \[ ] youtu.be short link with Mix/Radio playlist (?list=RD...)

&#x20;     -- should NOT hang, should return quickly



\## yt-dlp-level error handling (should show friendly messages)

\- \[ ] Private video URL

\- \[ ] Deleted/removed video URL

\- \[ ] Age-restricted video (if you have one handy to test)



\## Concurrency

\- \[ ] Two different videos submitted from two browser tabs within a

&#x20;     few seconds of each other both complete successfully

\- \[ ] `downloads/` folder is empty after both finish



\## Input tampering (backend should reject, not crash)

\- \[ ] Send `format: "exe"` via browser dev tools/curl -> expect 400

\- \[ ] Send `quality: "99999999"` -> expect 400

\- \[ ] Send `quality: "not-a-number"` -> expect 400

\- \[ ] Send malformed JSON body -> expect 400, not a 500 traceback



\## Mobile

\- \[ ] UI renders correctly on a phone screen

\- \[ ] Download completes and saves correctly on phone browser



\## Automated (run locally, no Docker needed)

\- \[ ] `pytest tests/ -v` -- all tests pass

