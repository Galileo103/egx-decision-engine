"""On-demand stock refresh and the frozen-feed chart flag — offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_refresh_"), "t.db")

import pytest  # noqa: E402

from app import calendar_egx, db  # noqa: E402
from app.services import history, leaders, market  # noqa: E402
from app.symbols import tv_to_yahoo  # noqa: E402

SUN = "2026-09-06"
IND = {"open": 17.7, "high": 17.9, "low": 17.36, "close": 17.45, "volume": 3_916_803, "RSI": 50.5}


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture
def closed_session(monkeypatch):
    monkeypatch.setattr(calendar_egx, "is_market_open", lambda *a, **k: False)
    monkeypatch.setattr(calendar_egx, "last_completed_session",
                        lambda *a, **k: datetime(2026, 9, 6).date())
    monkeypatch.setattr(market, "_fetch_universe_indicators",
                        lambda syms, tf: ({syms[0]: dict(IND)}, 0))
    monkeypatch.setattr(market, "compute_metrics",
                        lambda ind: {"price": ind["close"], "change": -1.41, "bbw": 0.06,
                                     "rating": 1, "signal": "NEUTRAL"})
    monkeypatch.setattr(market, "compute_stock_score",
                        lambda ind, change_pct_rank=None, currency="EGP":
                        {"score": 50, "grade": "Hold", "trend_state": "up", "breakdown": {},
                         "signals": [], "penalties": []})


class TestSnapshotSymbol:
    def test_refuses_while_session_is_open(self, closed_session, monkeypatch) -> None:
        monkeypatch.setattr(calendar_egx, "is_market_open", lambda *a, **k: True)
        out = market.snapshot_symbol("OPEN")
        assert "skipped" in out
        assert not db.query("SELECT 1 FROM snapshots WHERE symbol='OPEN'")

    def test_inserts_a_full_row_when_none_exists(self, closed_session) -> None:
        out = market.snapshot_symbol("EGX:NEWS")
        assert out["action"] == "inserted" and out["date"] == SUN and out["ohlc_complete"]
        row = db.query("SELECT * FROM snapshots WHERE symbol='NEWS' AND date=?", (SUN,))[0]
        assert (row["price"], row["open"], row["high"], row["low"]) == (17.45, 17.7, 17.9, 17.36)
        assert row["score"] == 50
        # …and the graft can now see it.
        assert market.session_bar("NEWS")["close"] == 17.45

    def test_existing_row_keeps_its_score(self, closed_session) -> None:
        """The nightly universe score is cross-sectional; a one-symbol refresh
        must not overwrite it with a rank-less recomputation."""
        db.execute("INSERT INTO snapshots (symbol, date, timeframe, price, score, created_at) "
                   "VALUES ('KEEP', ?, '1D', 17.7, 77, ?)", (SUN, SUN))
        out = market.snapshot_symbol("KEEP")
        assert out["action"] == "updated"
        row = db.query("SELECT * FROM snapshots WHERE symbol='KEEP' AND date=?", (SUN,))[0]
        assert row["score"] == 77
        assert (row["price"], row["open"], row["high"], row["low"]) == (17.45, 17.7, 17.9, 17.36)
        assert len(db.query("SELECT 1 FROM snapshots WHERE symbol='KEEP'")) == 1

    def test_no_tradingview_data_is_an_error_not_a_row(self, closed_session, monkeypatch) -> None:
        monkeypatch.setattr(market, "_fetch_universe_indicators", lambda syms, tf: ({}, 1))
        out = market.snapshot_symbol("GONE")
        assert "error" in out
        assert not db.query("SELECT 1 FROM snapshots WHERE symbol='GONE'")


class TestInvalidate:
    def test_leaders_drops_only_that_symbol(self) -> None:
        leaders._candle_cache.clear()
        leaders._candle_cache["TST|1y|2026-09-06"] = (0.0, [])
        leaders._candle_cache["TST|5y|2026-09-06"] = (0.0, [])
        leaders._candle_cache["OTHER|1y|2026-09-06"] = (0.0, [])
        assert leaders.invalidate("tst") == 2
        assert list(leaders._candle_cache) == ["OTHER|1y|2026-09-06"]

    def test_history_drops_good_and_failed_entries(self) -> None:
        key = (tv_to_yahoo("TST"), "1y", "1d")
        history._cache[key] = (0.0, {"candles": []})
        history._neg_cache[(tv_to_yahoo("TST"), "5d", "1d")] = (0.0, {"error": "x"})
        history._cache[(tv_to_yahoo("OTHER"), "1y", "1d")] = (0.0, {"candles": []})
        assert history.invalidate("TST") == 2
        assert (tv_to_yahoo("OTHER"), "1y", "1d") in history._cache


class TestRoutes:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_history_flags_a_frozen_yahoo_feed(self, client, monkeypatch) -> None:
        leaders._candle_cache.clear()
        flat = {"symbol": "DEAD", "candles": [
            {"time": f"2026-08-{d:02d}", "open": 71.05, "high": 71.05, "low": 71.05,
             "close": 71.05, "volume": 0.0} for d in range(10, 30)]}
        monkeypatch.setattr(history, "get_history", lambda *a, **k: dict(flat))
        r = client.get("/api/stocks/DEAD/history?range=1y&interval=1d").json()
        assert r["dead_feed"] is True
        assert r["frozen_close"] == 71.05 and r["frozen_since"] == "2026-08-10"
        assert len(r["candles"]) == 20            # the raw line is still returned

    def test_history_has_no_flag_for_a_live_series(self, client, monkeypatch) -> None:
        leaders._candle_cache.clear()
        live = {"symbol": "LIVE", "candles": [
            {"time": f"2026-08-{d:02d}", "open": 10, "high": 11, "low": 9, "close": 10 + d / 100,
             "volume": 1000.0} for d in range(10, 30)]}
        monkeypatch.setattr(history, "get_history", lambda *a, **k: dict(live))
        r = client.get("/api/stocks/LIVE/history?range=1y&interval=1d").json()
        assert "dead_feed" not in r

    def test_refresh_reports_snapshot_and_cleared_caches(self, client, monkeypatch) -> None:
        monkeypatch.setattr(market, "snapshot_symbol",
                            lambda sym, timeframe="1D": {"symbol": "TST", "date": SUN,
                                                          "action": "inserted", "price": 17.45})
        leaders._candle_cache["TST|1y|2026-09-06"] = (0.0, [])
        r = client.post("/api/stocks/tst/refresh").json()
        assert r["symbol"] == "TST"
        assert r["snapshot"]["action"] == "inserted"
        assert r["caches_cleared"] >= 1
        assert "TST|1y|2026-09-06" not in leaders._candle_cache
