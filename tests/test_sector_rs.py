"""Task 7 — sector relative strength: equal-weight sector indices, rank in sector,
stored context for the checklist and Compare. Offline (candles + sector map stubbed)."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_sector_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import leaders  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    db.execute("DELETE FROM rs_leaders")
    db.execute("DELETE FROM snapshots")
    with leaders._lock:
        leaders._candle_cache.clear()
    yield


def _bars(closes, start=datetime(2025, 9, 1)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.2,
                    "low": min(o, c) - 0.2, "close": c, "volume": 200_000})
        day += timedelta(days=1)
    return out


def _trend(n, start, daily_pct):
    out, px = [], start
    for _ in range(n):
        out.append(px)
        px *= 1.0 + daily_pct
    return out


SECTOR = {"B1": "banks", "B2": "banks", "R1": "real_estate", "R2": "real_estate", "R3": "real_estate", "X1": None}


def _install(monkeypatch, table):
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym.upper(), []))
    dates = [c["time"] for c in next(iter(table.values()))]
    flat = {d: 1000.0 for d in dates}
    monkeypatch.setattr(leaders, "benchmark_series", lambda force=False, range_="1y":
                        {"source": "test", "dates": dates, "series": flat, "bars": len(dates)})
    monkeypatch.setattr(leaders, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(leaders, "sector_of", lambda sym: SECTOR.get(sym.upper()))
    monkeypatch.setattr(leaders, "sector_label", lambda k: {"banks": "Banks", "real_estate": "Real Estate"}.get(k, k))
    monkeypatch.setattr(leaders, "_FETCH_PAUSE", 0.0)


class TestSectorStrength:
    def test_sector_indices_rank_and_stock_rank_in_sector(self, monkeypatch) -> None:
        n = 260
        table = {
            "B1": _bars(_trend(n, 10.0, 0.004)),    # banks rising ~0.4%/day
            "B2": _bars(_trend(n, 20.0, 0.003)),
            "R1": _bars(_trend(n, 5.0, -0.001)),    # real estate drifting down
            "R2": _bars(_trend(n, 8.0, -0.002)),
            "R3": _bars(_trend(n, 3.0, 0.0005)),
            "X1": _bars(_trend(n, 50.0, 0.002)),    # unclassified
        }
        _install(monkeypatch, table)
        out = leaders.compute("TEST", limit=10, persist=True, include_illiquid=True)
        assert "error" not in out
        secs = {s["sector"]: s for s in out["sectors"]}
        assert set(secs) == {"banks", "real_estate"}
        assert secs["banks"]["rank"] == 1 and secs["real_estate"]["rank"] == 2
        assert secs["banks"]["members"] == 2 and secs["real_estate"]["members"] == 3
        assert secs["banks"]["ret_1m"] > 0 > secs["real_estate"]["ret_1m"]
        assert secs["banks"]["excess_3m"] == pytest.approx(secs["banks"]["ret_3m"], abs=0.01)   # flat benchmark
        rows = {r["symbol"]: r for r in out["rows"]}
        assert rows["B1"]["sector_rank"] == 1 and rows["B1"]["sector_count"] == 2
        assert rows["B1"]["rank_in_sector"] == 1 and rows["B2"]["rank_in_sector"] == 2 and rows["B1"]["sector_size"] == 2
        assert rows["R3"]["rank_in_sector"] == 1 and rows["R2"]["rank_in_sector"] == 3
        assert rows["B1"]["rs_vs_sector_1m"] > 0 > rows["B2"]["rs_vs_sector_1m"]
        assert rows["X1"]["sector"] is None and rows["X1"]["sector_rank"] is None and rows["X1"]["rank_in_sector"] is None
        assert rows["B1"]["sector_label"] == "Banks"
        # persisted: stock rows + sector rows under the reserved prefix, read back split apart
        stored = leaders.latest("TEST", limit=50)
        assert stored["stored"] and len(stored["sectors"]) == 2 and stored["ranked"] == 6
        assert all(not str(r["symbol"]).startswith("SECTOR:") for r in stored["rows"])
        only_re = leaders.latest("TEST", limit=50, sector="real_estate")
        assert sorted(r["symbol"] for r in only_re["rows"]) == ["R1", "R2", "R3"] and only_re["sector"] == "real_estate"
        # context for the checklist / Compare
        ctx = leaders.sector_context("B2", "TEST")
        assert ctx["sector"] == "banks" and ctx["sector_rank"] == 1 and ctx["rank_in_sector"] == 2 and ctx["sector_size"] == 2
        assert ctx["sector_excess_3m"] == secs["banks"]["excess_3m"]
        sent = leaders.sector_sentence(ctx)
        assert sent.startswith("Sector: Banks ranks 1 of 2 sectors") and "#2 of 2" in sent and "leading sector" in sent
        lag = leaders.sector_sentence(leaders.sector_context("R1", "TEST"))
        assert "lagging sector" in lag
        assert leaders.sector_context("X1", "TEST") == {"sector": None, "date": stored["date"]}
        assert leaders.sector_context("NOPE", "TEST") is None and leaders.sector_sentence(None) == ""

    def test_single_member_sector_gets_no_index(self, monkeypatch) -> None:
        n = 200
        table = {"B1": _bars(_trend(n, 10.0, 0.003)), "R1": _bars(_trend(n, 5.0, -0.001)), "R2": _bars(_trend(n, 8.0, 0.001))}
        _install(monkeypatch, table)
        out = leaders.compute("TEST", limit=10, persist=False, include_illiquid=True)
        assert [s["sector"] for s in out["sectors"]] == ["real_estate"]
        rows = {r["symbol"]: r for r in out["rows"]}
        assert rows["B1"]["sector"] == "banks" and rows["B1"]["sector_rank"] is None   # no index for a 1-member sector
        assert rows["B1"]["rank_in_sector"] == 1 and rows["B1"]["sector_size"] == 1
        assert leaders.sector_context("B1", "TEST") is None                          # nothing persisted


class TestChecklistUsesSector:
    def test_trend_pillar_carries_the_sector_sentence_live_only(self, monkeypatch) -> None:
        from app.services import checklist, patterns, regime

        monkeypatch.setattr(regime, "current_state", lambda: "bull")
        monkeypatch.setattr(patterns, "detect", lambda sym, cc=None, view="all": {"patterns": []})
        candles = _bars(_trend(220, 20.0, 0.002))
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
        ctx = {"sector": "banks", "sector_label": "Banks", "sector_rank": 1, "sector_count": 8, "rank_in_sector": 3,
               "sector_size": 9, "rs_vs_sector_1m": 1.4}
        monkeypatch.setattr(leaders, "sector_context", lambda sym, universe="EGX100": ctx)
        live = checklist.checklist("COMI")
        trend = next(p for p in live["pillars"] if p["key"] == "trend")
        assert "Sector: Banks ranks 1 of 8 sectors" in trend["text"] and trend["sector"] == ctx
        # the replay hands in candles: today's sector ranking would be look-ahead, so no sentence
        past = checklist.checklist("COMI", candles=candles, regime_state="bull")
        trend2 = next(p for p in past["pillars"] if p["key"] == "trend")
        assert "Sector:" not in trend2["text"] and "sector" not in trend2
