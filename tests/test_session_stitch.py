"""Grafting the just-closed session onto the Yahoo candle series — offline.

Yahoo publishes an EGX daily bar about a session late, so the session the user
decides on is missing from every Yahoo-based card. These cover the graft, the
guards that keep a partial or duplicate bar out, and the cache key that used to
let a mid-session fetch shadow the post-close result.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_stitch_"), "t.db")

import pytest  # noqa: E402

from app import calendar_egx, db  # noqa: E402
from app.services import leaders, market  # noqa: E402

CAIRO = calendar_egx.CAIRO

# 2026-09-03 Thu (session), 09-04 Fri + 09-05 Sat (weekend), 09-06 Sun (session).
THU = "2026-09-03"
SUN = "2026-09-06"


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clear_candle_cache():
    leaders._candle_cache.clear()
    yield
    leaders._candle_cache.clear()


def _snapshot(symbol: str, date: str, o, h, low, c, volume=1_000.0) -> None:
    db.execute(
        "INSERT OR REPLACE INTO snapshots "
        "(symbol, date, timeframe, price, volume, open, high, low, created_at) "
        "VALUES (?, ?, '1D', ?, ?, ?, ?, ?, ?)",
        (symbol, date, c, volume, o, h, low, date),
    )


def _yahoo(*dates: str):
    """Stub history payload: one plain candle per date."""
    return {
        "symbol": "X",
        "candles": [
            {"time": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 500.0}
            for d in dates
        ],
    }


class TestLastCompletedSession:
    @pytest.mark.parametrize(
        "when, expected",
        [
            ((2026, 9, 6, 10, 30), THU),   # Sunday mid-session: today is not final yet
            ((2026, 9, 6, 14, 30), SUN),   # the close itself counts
            ((2026, 9, 6, 15, 0), SUN),    # post-close
            ((2026, 9, 5, 12, 0), THU),    # Saturday
            ((2026, 9, 4, 12, 0), THU),    # Friday
            ((2026, 9, 6, 9, 0), THU),     # before the open
        ],
    )
    def test_session_boundaries(self, when, expected) -> None:
        got = calendar_egx.last_completed_session(datetime(*when, tzinfo=CAIRO))
        assert got.strftime("%Y-%m-%d") == expected

    def test_never_returns_a_running_session(self) -> None:
        """The whole point: mid-session, today's OHLC is still moving."""
        mid = datetime(2026, 9, 6, 12, 0, tzinfo=CAIRO)
        assert calendar_egx.last_completed_session(mid) < mid.date()


class TestSessionBar:
    def test_returns_the_snapshot_bar(self, monkeypatch) -> None:
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        _snapshot("AAAA", SUN, 17.7, 17.9, 17.36, 17.45, volume=3_916_803.0)
        bar = market.session_bar("AAAA")
        assert bar == {"time": SUN, "open": 17.7, "high": 17.9, "low": 17.36,
                       "close": 17.45, "volume": 3_916_803.0, "source": "tv_snapshot"}

    def test_accepts_an_exchange_prefixed_symbol(self, monkeypatch) -> None:
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        _snapshot("BBBB", SUN, 5.0, 5.2, 4.9, 5.1)
        assert market.session_bar("EGX:BBBB") is not None

    def test_price_only_row_is_rejected(self, monkeypatch) -> None:
        """The EGX30 index row carries a close and no OHLC — not a candle."""
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        db.execute(
            "INSERT OR REPLACE INTO snapshots (symbol, date, timeframe, price, created_at) "
            "VALUES ('IDX30', ?, '1D', 56676.2, ?)", (SUN, SUN),
        )
        assert market.session_bar("IDX30") is None

    def test_inconsistent_ohlc_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        _snapshot("CCCC", SUN, 10.0, 9.0, 11.0, 10.0)  # high below low
        assert market.session_bar("CCCC") is None
        _snapshot("DDDD", SUN, 10.0, 10.5, 0.0, 10.0)  # non-positive price
        assert market.session_bar("DDDD") is None

    def test_missing_session_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        _snapshot("EEEE", THU, 10.0, 10.5, 9.5, 10.0)  # only the older session
        assert market.session_bar("EEEE") is None


class TestDailyCandlesGraft:
    @pytest.fixture(autouse=True)
    def _freeze_session(self, monkeypatch):
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())

    def _stub_yahoo(self, monkeypatch, payload) -> None:
        from app.services import history

        monkeypatch.setattr(history, "get_history", lambda *a, **k: payload)

    def test_grafts_the_missing_session(self, monkeypatch) -> None:
        self._stub_yahoo(monkeypatch, _yahoo("2026-09-02", THU))
        _snapshot("GRFT", SUN, 17.7, 17.9, 17.36, 17.45)
        candles = leaders.daily_candles("GRFT")
        assert [c["time"] for c in candles] == ["2026-09-02", THU, SUN]
        assert candles[-1]["close"] == 17.45
        assert candles[-1]["source"] == "tv_snapshot"

    def test_no_graft_when_yahoo_already_has_the_session(self, monkeypatch) -> None:
        """Once Yahoo backfills, its own bar is authoritative."""
        self._stub_yahoo(monkeypatch, _yahoo(THU, SUN))
        _snapshot("BOTH", SUN, 17.7, 17.9, 17.36, 17.45)
        candles = leaders.daily_candles("BOTH")
        assert [c["time"] for c in candles] == [THU, SUN]
        assert candles[-1]["close"] == 10.0          # Yahoo's, not the snapshot's
        assert "source" not in candles[-1]

    def test_no_graft_without_a_snapshot(self, monkeypatch) -> None:
        self._stub_yahoo(monkeypatch, _yahoo("2026-09-02", THU))
        candles = leaders.daily_candles("NOSNAP")
        assert [c["time"] for c in candles] == ["2026-09-02", THU]

    def test_dead_yahoo_feed_is_dropped_not_grafted(self, monkeypatch) -> None:
        """ORAS, 2026-09-06: Yahoo had a year of 71.05 / zero volume while the
        stock traded ~850. Grafting one real bar onto that made a fake breakout."""
        payload = {"symbol": "DEAD", "candles": [
            {"time": f"2026-08-{d:02d}", "open": 71.05, "high": 71.05, "low": 71.05,
             "close": 71.05, "volume": 0.0} for d in range(10, 30)]}
        self._stub_yahoo(monkeypatch, payload)
        _snapshot("DEAD", SUN, 850.0, 880.0, 840.0, 874.99, volume=305_475.0)
        assert leaders.daily_candles("DEAD") == []

    def test_flat_closes_with_real_volume_are_not_a_dead_feed(self, monkeypatch) -> None:
        """A thinly traded name can print the same close for days — that is data."""
        payload = {"symbol": "FLAT", "candles": [
            {"time": f"2026-08-{d:02d}", "open": 5.0, "high": 5.0, "low": 5.0,
             "close": 5.0, "volume": 1_000.0} for d in range(10, 30)]}
        self._stub_yahoo(monkeypatch, payload)
        assert len(leaders.daily_candles("FLAT")) == 20

    def test_no_graft_onto_an_empty_series(self, monkeypatch) -> None:
        """One snapshot bar is not history — callers guard on bar count, and a
        1-bar series would sail past an `if candles:` check carrying nothing."""
        self._stub_yahoo(monkeypatch, {"symbol": "EMPTY", "candles": []})
        _snapshot("EMPTY", SUN, 17.7, 17.9, 17.36, 17.45)
        assert leaders.daily_candles("EMPTY") == []

    def test_stale_snapshot_never_overwrites_newer_yahoo(self, monkeypatch) -> None:
        """A snapshot dated at/behind Yahoo's last bar is dropped, not appended."""
        self._stub_yahoo(monkeypatch, _yahoo(THU, SUN, "2026-09-07"))
        _snapshot("STALE", SUN, 1.0, 1.1, 0.9, 1.0)
        candles = leaders.daily_candles("STALE")
        assert [c["time"] for c in candles] == [THU, SUN, "2026-09-07"]
        assert candles[-1]["close"] == 10.0

    def test_null_session_bar_is_dropped_then_grafted(self, monkeypatch) -> None:
        """Yahoo's real shape: the session exists as an all-null row."""
        payload = _yahoo("2026-09-02", THU)
        payload["candles"].append(
            {"time": SUN, "open": None, "high": None, "low": None, "close": None,
             "volume": None}
        )
        self._stub_yahoo(monkeypatch, payload)
        _snapshot("NULLB", SUN, 17.7, 17.9, 17.36, 17.45)
        candles = leaders.daily_candles("NULLB")
        assert [c["time"] for c in candles] == ["2026-09-02", THU, SUN]
        assert candles[-1]["close"] == 17.45

    def test_mid_session_fetch_does_not_shadow_the_post_close_graft(
            self, monkeypatch) -> None:
        """The cache-key regression: the 10-minute intraday job runs while the
        market is open and legitimately sees no bar for today. Under a plain
        symbol|range key that entry served the whole 4-hour TTL, so the
        post-close pipeline recomputed everything one session stale."""
        self._stub_yahoo(monkeypatch, _yahoo("2026-09-02", THU))
        _snapshot("CACHE", SUN, 17.7, 17.9, 17.36, 17.45)

        # Mid-session: nothing to graft, and the result is cached.
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 3).date())
        assert [c["time"] for c in leaders.daily_candles("CACHE")] == ["2026-09-02", THU]

        # After the close the same call must see the new session, not the cache.
        monkeypatch.setattr(calendar_egx, "last_completed_session",
                            lambda *a, **k: datetime(2026, 9, 6).date())
        assert [c["time"] for c in leaders.daily_candles("CACHE")] == ["2026-09-02", THU, SUN]
