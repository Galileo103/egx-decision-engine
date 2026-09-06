"""Task 8 — corporate actions: Yahoo events parsing, manual entries, suspect pattern
tagging, checklist and Guardian warnings. Offline."""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_ca_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import corporate_actions as CA  # noqa: E402
from app.services import checklist, guardian, history, leaders, patterns, regime  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("corporate_actions", "positions", "rs_leaders"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    yield


def _bars(closes, start=datetime(2026, 6, 1)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.2,
                    "low": min(o, c) - 0.2, "close": c, "volume": 100_000})
        day += timedelta(days=1)
    return out


class TestYahooEvents:
    def test_parse_chart_keeps_dividends_and_splits(self) -> None:
        payload = {"chart": {"result": [{
            "timestamp": [1_700_000_000 + 86400 * i for i in range(3)],
            "indicators": {"quote": [{"open": [10, 10, 10], "high": [11, 11, 11], "low": [9, 9, 9], "close": [10, 10, 10],
                                      "volume": [100, 100, 100]}]},
            "events": {"dividends": {"1700086400": {"amount": 0.5, "date": 1700086400}},
                       "splits": {"1700172800": {"numerator": 3, "denominator": 1, "splitRatio": "3:1", "date": 1700172800}}},
        }]}}
        out = history._parse_chart(payload, "COMI", "1d")
        assert "error" not in out and len(out["candles"]) == 3
        ev = out["events"]
        assert ev[0]["type"] == "dividend" and ev[0]["amount"] == 0.5 and ev[0]["date"] == "2023-11-15"
        assert ev[1]["type"] == "split" and ev[1]["ratio"] == 3.0 and ev[1]["note"] == "3:1"
        # no events block -> no key
        payload["chart"]["result"][0].pop("events")
        assert "events" not in history._parse_chart(payload, "COMI", "1d")

    def test_record_yahoo_upserts_and_daily_candles_books_them(self, monkeypatch) -> None:
        n = CA.record_yahoo("COMI", [{"type": "dividend", "date": "2026-05-10", "amount": 1.25},
                                     {"type": "split", "date": "2026-02-01", "ratio": 2.0},
                                     {"type": "bogus", "date": "2026-01-01"}])
        assert n == 2
        assert CA.record_yahoo("COMI", [{"type": "dividend", "date": "2026-05-10", "amount": 1.25}]) == 1   # idempotent
        rows = CA.for_symbol("COMI")
        assert [r["type"] for r in rows] == ["split", "dividend"] and rows[1]["label"] == "ex-dividend"
        # a fresh fetch through daily_candles records the payload's events
        payload = {"symbol": "ADIB", "candles": _bars([10.0] * 30), "events": [{"type": "dividend", "date": "2026-06-10", "amount": 0.3}]}
        monkeypatch.setattr(history, "get_history", lambda sym, rng="1y", interval="1d": payload)
        assert len(leaders.daily_candles("ADIB")) >= 30
        assert CA.for_symbol("ADIB")[0]["amount"] == 0.3 and CA.for_symbol("ADIB")[0]["source"] == "yahoo"


class TestManual:
    def test_add_list_upcoming_delete(self) -> None:
        today = date(2026, 9, 6)
        res = CA.add("skpc", "rights", "2026-09-09", ratio=0.5, note="1 new per 2, EGX notice")
        assert res["ok"] is True and res["symbol"] == "SKPC" and res["source"] == "manual"
        assert CA.add("SKPC", "nonsense", "2026-09-09")["error"].startswith("type must be")
        assert CA.add("SKPC", "dividend", "soon")["error"].startswith("ex_date")
        CA.add("COMI", "dividend", "2026-10-20", amount=2.0)
        CA.add("COMI", "dividend", "2026-03-01", amount=1.0)          # past
        up = CA.upcoming(None, 30, today)
        assert [(u["symbol"], u["days_until"]) for u in up] == [("SKPC", 3)]
        up60 = CA.upcoming(["COMI", "SKPC"], 60, today)
        assert [(u["symbol"], u["type"]) for u in up60] == [("SKPC", "rights"), ("COMI", "dividend")]
        nxt = CA.next_for("SKPC", 5, today)
        assert nxt["type"] == "rights" and "Rights issue in 3 day(s) (2026-09-09) (ratio 0.5)" in CA.warning_text(nxt)
        assert CA.next_for("COMI", 5, today) is None
        assert CA.warning_text(None) == ""
        deleted = CA.delete(res["id"])
        assert deleted["ok"] is True and CA.upcoming(None, 30, today) == []
        assert "not found" in CA.delete(res["id"])["error"]
        # yahoo rows cannot be deleted
        CA.record_yahoo("COMI", [{"type": "dividend", "date": "2026-05-10", "amount": 1.25}])
        yid = [r for r in CA.for_symbol("COMI") if r["source"] == "yahoo"][0]["id"]
        assert "not found" in CA.delete(yid)["error"]


class TestSuspectPatterns:
    def test_trigger_on_ex_date_is_tagged_and_ignored_by_checklist(self, monkeypatch) -> None:
        candles = _bars([20.0 + 0.02 * i for i in range(220)])
        brk = candles[-3]["time"]
        CA.add("AAA", "dividend", brk, amount=1.5)
        rows = [{"pattern": "bear_trap", "break_date": brk, "status": "confirmed"},
                {"pattern": "double_bottom", "break_date": candles[-40]["time"], "status": "confirmed"},
                {"pattern": "hammer", "status": "forming"}]
        assert CA.tag_suspect("AAA", rows) == 1
        assert "ex-dividend on " + brk in rows[0]["suspect"] and rows[0]["suspect_event"]["amount"] == 1.5
        assert "suspect" not in rows[1] and "suspect" not in rows[2]
        assert CA.events_near("AAA", brk) and CA.events_near("AAA", candles[-40]["time"]) == []
        # through detect(): the tag rides on the row; the checklist's pillars skip it
        from app.services import pattern_action, pattern_candles, pattern_geometry, weekly

        monkeypatch.setattr(pattern_candles, "detect", lambda cc, atr: [])
        monkeypatch.setattr(pattern_geometry, "detect", lambda cc, atr: [])
        monkeypatch.setattr(pattern_action, "detect", lambda cc, atr: [
            {"pattern": "bull_trap", "status": "confirmed", "quality": 70, "direction": "bearish", "neckline": 24.0,
             "target": 22.0, "start_date": candles[-6]["time"], "break_date": brk}])
        monkeypatch.setattr(weekly, "structure_rows", lambda cc: [])
        out = patterns.detect("AAA", candles, view="all")
        assert out["patterns"][0]["suspect"]
        monkeypatch.setattr(regime, "current_state", lambda: "bull")
        monkeypatch.setattr(leaders, "sector_context", lambda sym, universe="EGX100": None)
        ck = checklist.checklist("AAA", candles=candles, regime_state="bull")
        pa = next(p for p in ck["pillars"] if p["key"] == "price_action")
        assert pa["status"] == "warn" and "No decisive" in pa["text"]         # the bull trap did not FAIL the pillar


class TestWarnings:
    def test_checklist_risk_pillar_warns_live_only(self, monkeypatch) -> None:
        candles = _bars([20.0 + 0.02 * i for i in range(220)])
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
        monkeypatch.setattr(leaders, "sector_context", lambda sym, universe="EGX100": None)
        monkeypatch.setattr(patterns, "detect", lambda sym, cc=None, view="all": {"patterns": []})
        monkeypatch.setattr(regime, "current_state", lambda: "bull")
        ex = (datetime.now(CA.CAIRO).date() + timedelta(days=2)).isoformat()
        CA.add("BBB", "dividend", ex, amount=0.8)
        live = checklist.checklist("BBB")
        risk = next(p for p in live["pillars"] if p["key"] == "risk")
        assert "Ex-dividend in 2 day(s)" in risk["text"] and risk["event"]["ex_date"] == ex and risk["status"] != "pass"
        past = checklist.checklist("BBB", candles=candles, regime_state="bull")
        risk2 = next(p for p in past["pillars"] if p["key"] == "risk")
        assert "Ex-dividend" not in risk2["text"] and "event" not in risk2

    def test_guardian_ex_date_soon_is_advice_and_never_outranks(self) -> None:
        row = {"symbol": "CCC", "all_verdicts": [], "reasons": [], "verdict": "HOLD", "severity": "ok"}
        ev = {"type": "dividend", "ex_date": "2026-09-08", "amount": 0.5, "days_until": 2}
        out = guardian.apply_corporate_actions(dict(row), ev)
        assert out["verdict"] == "EX_DATE_SOON" and out["severity"] == "advice"
        assert any("Ex-dividend in 2 day(s)" in r for r in out["reasons"])
        crit = {"symbol": "CCC", "all_verdicts": ["EXIT_STOP"], "reasons": ["out"], "verdict": "EXIT_STOP", "severity": "critical"}
        out2 = guardian.apply_corporate_actions(dict(crit), ev)
        assert out2["verdict"] == "EXIT_STOP" and "EX_DATE_SOON" in out2["all_verdicts"]
        # no event -> untouched
        out3 = guardian.apply_corporate_actions(dict(row), None)
        assert out3["verdict"] == "HOLD" and out3["corporate_action"] is None
        assert guardian.SEVERITY["EX_DATE_SOON"] == "advice" and "EX_DATE_SOON" in guardian._RANK
