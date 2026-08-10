"""
jobs.py

In-memory tracking of background download jobs, so the browser can
poll for REAL progress instead of guessing with a timer.

Design notes:
- A plain dict guarded by a threading.Lock -- intentionally simple,
  appropriate for a single-process, LAN-only tool. If this app ever
  ran as multiple server processes/workers, this would need to move
  to a shared backend (e.g. Redis), since each process would
  otherwise keep its own separate, inconsistent copy of job state.
- Every read AND write goes through the same lock. This matters:
  a job's dict is mutated from the background download thread
  (progress updates) while simultaneously being read from request
  threads (progress polling) -- without a lock, this is a textbook
  race condition that could occasionally read a half-updated,
  inconsistent state.
- Old finished/errored jobs are pruned automatically (best-effort) so
  memory doesn't grow unbounded if a browser tab is closed mid-poll
  and never fetches the result.
"""

import threading
import time
import uuid


class JobStore:
    """Thread-safe in-memory store of background download job states."""

    def __init__(self, max_age_seconds: int = 3600):
        self._jobs = {}
        self._lock = threading.Lock()
        self._max_age_seconds = max_age_seconds

    def create(self) -> str:
        """Register a new job in the 'queued' state and return its ID."""
        job_id = uuid.uuid4().hex
        with self._lock:
            self._prune_expired_locked()
            self._jobs[job_id] = {
                "status": "queued",  # queued -> downloading -> converting -> done -> error
                "percent": 0.0,
                "error": None,
                "result": None,  # becomes a downloader.DownloadResult when done
                "created_at": time.time(),
            }
        return job_id

    def update(self, job_id: str, **fields) -> None:
        """Merge the given fields into an existing job's state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(fields)

    def get(self, job_id: str):
        """Return a COPY of a job's current state, or None if unknown/expired.
        Returning a copy (not the live dict) avoids callers accidentally
        mutating shared state outside the lock."""
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def _prune_expired_locked(self) -> None:
        """Remove old finished/errored jobs nobody ever collected.
        Caller must already hold self._lock."""
        cutoff = time.time() - self._max_age_seconds
        expired = [
            jid for jid, job in self._jobs.items()
            if job["created_at"] < cutoff and job["status"] in ("done", "error")
        ]
        for jid in expired:
            self._jobs.pop(jid, None)


# Single shared instance used across the whole app.
JOB_STORE = JobStore()