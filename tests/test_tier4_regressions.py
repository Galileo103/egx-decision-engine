"""Regression tests for the defects found in the Tier 4 adversarial review.

Each test pins a specific confirmed bug:
- history.py: neg-cache hit path deadlocked (lock re-entry) and re-stamped the
  entry (sliding expiry that never let Yahoo be retried under polling);
- scheduler.py: catch-up runs recorded ok=1 when every post-close stage failed;
  the EGX30 index row satisfied the catch-up presence check on its own; the
  post-close pipeline could run twice concurrently; failure pings repeated
  27x/day during a standing outage.
All offline — no network.
"""
from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime
from types import SimpleNamespace

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="egx_t4_"), "test_t4.db"
)

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean_state():
    for table in ("snapshots", "job_runs", "alerts_fired"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed literals
    from app.services import history

    with history._cache_lock:
        history._cache.clear()
        history._neg_cache.clear()
        history._throttled_until = 0.0
    yield


class _FailingClient:
    """httpx.Client stand-in whose every request raises."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, *args, **kwargs):
        raise ConnectionError("simulated outage")


# ── history.py cache state machine ───────────────────────────────────────────

class TestHistoryNegativeCache:
    def test_neg_cache_hit_returns_and_does_not_slide(self, monkeypatch) -> None:
        """First failure is negative-cached; a second call within the TTL must
        RETURN (the old code re-acquired the non-reentrant lock → deadlock)
        and must NOT refresh the entry's timestamp (sliding expiry)."""
        from app.services import history

        monkeypatch.setattr(history, "_RETRIES", 1)
        monkeypatch.setattr(history, "httpx", SimpleNamespace(Client=_FailingClient))

        r1 = history.get_history("COMI", "1y", "1d")
        assert "error" in r1

        key = ("COMI.CA", "1y", "1d")
        with history._cache_lock:
            assert key in history._neg_cache
            ts0 = history._neg_cache[key][0]

        r2 = history.get_history("COMI", "1y", "1d")  # would hang pre-fix
        assert "error" in r2
        with history._cache_lock:
            assert history._neg_cache[key][0] == ts0, "neg-cache TTL must be fixed, not sliding"

    def test_stale_while_error_serves_tagged_copy(self, monkeypatch) -> None:
        from app.services import history

        monkeypatch.setattr(history, "_RETRIES", 1)
        monkeypatch.setattr(history, "httpx", SimpleNamespace(Client=_FailingClient))

        key = ("COMI.CA", "1y", "1d")
        good = {"symbol": "COMI", "candles": [{"time": "2026-08-27", "close": 10.0}]}
        with history._cache_lock:
            # Expired for the fresh path (TTL 600s) but within _STALE_MAX.
            history._cache[key] = (time.monotonic() - 700, good)

        r = history.get_history("COMI", "1y", "1d")
        assert r.get("stale") is True and r["candles"], r
        assert "stale_age_s" in r

    def test_fresh_hit_returns_a_copy(self) -> None:
        """Mutating a returned payload must not poison the cache."""
        from app.services import history

        key = ("COMI.CA", "1y", "1d")
        good = {"symbol": "COMI", "candles": [{"time": "2026-08-27", "close": 10.0}]}
        with history._cache_lock:
            history._cache[key] = (time.monotonic(), good)

        r = history.get_history("COMI", "1y", "1d")
        r["symbol"] = "MUTATED"
        with history._cache_lock:
            assert history._cache[key][1]["symbol"] == "COMI"


# ── scheduler catch-up job ───────────────────────────────────────────────────

def _fake_now(monkeypatch, hour: int, minute: int = 0):
    """Pin scheduler wall-clock to Monday 2026-08-31 (a trading day)."""
    from app import scheduler

    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            return datetime(2026, 8, 31, hour, minute, tzinfo=scheduler.CAIRO)

    monkeypatch.setattr(scheduler, "datetime", _FakeDT)


class TestCatchupJob:
    def test_egx30_row_alone_does_not_satisfy_the_check(self, monkeypatch) -> None:
        """A day where TradingView failed but the Yahoo index row landed must
        still be backfilled — the index row is from a different pipeline."""
        from app import scheduler

        _fake_now(monkeypatch, 16)
        db.execute(
            "INSERT OR REPLACE INTO snapshots (symbol, date, timeframe, price) "
            "VALUES ('EGX30', '2026-08-31', '1D', 54000.0)"
        )
        called = {"n": 0}
        monkeypatch.setattr(scheduler, "_job_post_close",
                            lambda: called.update(n=called["n"] + 1) or {"snapshot": {"saved": 100}})
        result = scheduler._job_catchup()
        assert called["n"] == 1, result
        assert result.get("caught_up_session") == "2026-08-31"

    def test_real_snapshot_skips_backfill(self, monkeypatch) -> None:
        from app import scheduler

        _fake_now(monkeypatch, 16)
        rows = [(f"SYM{i:03d}", "2026-08-31", "1D", 10.0) for i in range(25)]
        db.executemany(
            "INSERT OR REPLACE INTO snapshots (symbol, date, timeframe, price) VALUES (?, ?, ?, ?)",
            rows,
        )
        monkeypatch.setattr(scheduler, "_job_post_close",
                            lambda: pytest.fail("must not run post_close"))
        result = scheduler._job_catchup()
        assert "skipped" in result and "already present" in result["skipped"]

    def test_failed_backfill_is_recorded_as_a_failure(self, monkeypatch) -> None:
        """Stage errors inside the nested post_close result sit one level too
        deep for _result_failed — the catch-up must lift them to the top."""
        from app import scheduler

        _fake_now(monkeypatch, 16)
        monkeypatch.setattr(
            scheduler, "_job_post_close",
            lambda: {"snapshot": {"error": "upstream down"}, "candidates": {"count": 0}},
        )
        result = scheduler._job_catchup()
        assert scheduler._result_failed(result), result

    def test_before_post_close_window_skips(self, monkeypatch) -> None:
        from app import scheduler

        _fake_now(monkeypatch, 12)
        assert "skipped" in scheduler._job_catchup()


class TestPostCloseSerialization:
    def test_second_concurrent_run_is_skipped(self, monkeypatch) -> None:
        from app import scheduler

        monkeypatch.setattr(scheduler, "_skip_non_trading", lambda: None)
        assert scheduler._post_close_lock.acquire(blocking=False)
        try:
            result = scheduler._job_post_close()
            assert "skipped" in result and "already running" in result["skipped"]
        finally:
            scheduler._post_close_lock.release()


class TestFailureNotificationDedupe:
    def _record_run(self, job: str, ok: int) -> None:
        db.execute(
            "INSERT INTO job_runs (job, started_at, finished_at, ok, detail) "
            "VALUES (?, '2026-08-31T15:00:00+03:00', '2026-08-31T15:01:00+03:00', ?, '')",
            (job, ok),
        )

    def test_repeat_failure_is_suppressed(self, monkeypatch) -> None:
        from app import scheduler
        from app.services import alerts

        sent: list[str] = []
        monkeypatch.setattr(alerts, "send_telegram", lambda text: sent.append(text) or True)

        # First failure: previous run was ok -> ping.
        self._record_run("intraday", 1)
        self._record_run("intraday", 0)  # the current failing run's own row
        scheduler._notify_failure("intraday", "boom")
        assert len(sent) == 1

        # Second consecutive failure: previous run failed too -> suppressed.
        self._record_run("intraday", 0)
        scheduler._notify_failure("intraday", "boom again")
        assert len(sent) == 1
