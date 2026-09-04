"""Tiny background-job runner for long, one-at-a-time computations.

Used by the historical replay and the Proven-edge refresh: both take minutes,
so the HTTP handler starts them in a daemon thread and the UI polls
``status()``. One instance = one job slot; a second start while running is
refused rather than queued (these jobs are idempotent, so "run again later"
is the right answer).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")


class BackgroundJob:
    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "name": name, "running": False, "phase": None, "done": 0, "total": 0,
            "detail": None, "started_at": None, "finished_at": None, "elapsed_s": None,
            "result": None, "error": None,
        }
        self._t0: Optional[float] = None

    # ── progress reporting (called from inside the job) ──────────────────────

    def progress(self, phase: Optional[str] = None, done: Optional[int] = None,
                 total: Optional[int] = None, detail: Optional[str] = None) -> None:
        with self._lock:
            if phase is not None:
                self._state["phase"] = phase
            if done is not None:
                self._state["done"] = int(done)
            if total is not None:
                self._state["total"] = int(total)
            if detail is not None:
                self._state["detail"] = detail
            if self._t0 is not None:
                self._state["elapsed_s"] = round(time.monotonic() - self._t0, 1)

    # ── control ──────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            if out["running"] and self._t0 is not None:
                out["elapsed_s"] = round(time.monotonic() - self._t0, 1)
            return out

    def start(self, fn: Callable[..., dict], *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Run ``fn(*args, **kwargs)`` in a daemon thread. Refuses if running."""
        with self._lock:
            if self._state["running"]:
                return {"error": f"{self.name} is already running", "status": dict(self._state)}
            self._state.update({
                "running": True, "phase": "starting", "done": 0, "total": 0, "detail": None,
                "started_at": datetime.now(CAIRO).isoformat(), "finished_at": None,
                "elapsed_s": 0.0, "result": None, "error": None,
            })
            self._t0 = time.monotonic()

        def _runner() -> None:
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    self._state["result"] = result
                    if isinstance(result, dict) and result.get("error"):
                        self._state["error"] = str(result["error"])
            except Exception as exc:  # noqa: BLE001
                logger.exception("%s failed", self.name)
                with self._lock:
                    self._state["error"] = str(exc)
            finally:
                with self._lock:
                    self._state["running"] = False
                    self._state["phase"] = "finished"
                    self._state["finished_at"] = datetime.now(CAIRO).isoformat()
                    if self._t0 is not None:
                        self._state["elapsed_s"] = round(time.monotonic() - self._t0, 1)

        threading.Thread(target=_runner, name=self.name, daemon=True).start()
        return {"started": True, "status": self.status()}

    def run_sync(self, fn: Callable[..., dict], *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Same bookkeeping, but blocking (tests, scheduler)."""
        started = self.start(fn, *args, **kwargs)
        if "error" in started and not started.get("started"):
            return started
        while self.status()["running"]:
            time.sleep(0.05)
        st = self.status()
        return st["result"] if st.get("result") is not None else {"error": st.get("error") or "no result"}
