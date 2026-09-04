"""Chart-pattern detector — synthetic shapes, offline.

Each test draws a shape with an explicit swing structure, then checks the
detector names it, classifies FORMING vs CONFIRMED correctly, and that noise
or stale shapes are NOT reported.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_pat_"), "test_pat.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import patterns  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("pattern_hits", "scanner_hits"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    yield


def _candles(closes: list[float], spread: float = 1.0, vols: list[float] | None = None) -> list[dict]:
    day = datetime(2026, 1, 5)
    out = []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": c, "high": c + spread / 2,
                    "low": c - spread / 2, "close": c, "volume": (vols[i] if vols else 100_000)})
        day += timedelta(days=1)
    return out


def _seg(a: float, b: float, n: int) -> list[float]:
    """n points moving linearly from a towards b (b excluded)."""
    return [a + (b - a) * i / n for i in range(n)]


def _double_bottom_closes(confirm: bool) -> list[float]:
    base = [100.0] * 40                    # quiet lead-in for ATR
    down1 = _seg(100, 80, 15)              # fall to first low
    up1 = _seg(80, 95, 15)                 # bounce to neckline ~95
    down2 = _seg(95, 80.5, 15)             # second low ≈ first
    up2 = _seg(80.5, 94, 15)               # back toward neckline
    tail = _seg(94, 99, 6) if confirm else [93.0, 93.5, 92.8, 93.2, 93.0, 93.4]
    return base + down1 + up1 + down2 + up2 + tail


class TestDoubleBottom:
    def test_forming_then_confirmed(self) -> None:
        forming = patterns.detect("TEST", _candles(_double_bottom_closes(False)))
        names = [p["pattern"] for p in forming["patterns"]]
        assert "double_bottom" in names, names
        row = next(p for p in forming["patterns"] if p["pattern"] == "double_bottom")
        assert row["status"] == "forming" and row["direction"] == "bullish"
        assert row["neckline"] == pytest.approx(95.0, abs=1.5)
        assert row["target"] > row["neckline"] > row["stop_hint"]
        assert 0 <= row["quality"] <= 100

        vols = [100_000] * 100 + [300_000] * 6  # volume surge on the last 6 bars (the break)
        confirmed = patterns.detect("TEST", _candles(_double_bottom_closes(True), vols=vols))
        row = next(p for p in confirmed["patterns"] if p["pattern"] == "double_bottom")
        assert row["status"] == "confirmed"
        assert row["break_date"] is not None
        assert row["break_volume_ratio"] and row["break_volume_ratio"] > 1.5
        assert row["quality"] > 50

    def test_random_walk_has_no_pattern(self) -> None:
        import random

        rnd = random.Random(7)
        closes, c = [], 100.0
        for _ in range(160):
            c *= 1 + rnd.uniform(-0.004, 0.004)
            closes.append(c)
        res = patterns.detect("NOISE", _candles(closes, spread=0.3))
        # Tiny wiggles never reach the 2-ATR depth requirement for chart shapes
        # (candlestick / price-action events may still fire — they are bar-level).
        assert [p for p in res["patterns"] if p["category"] == "reversal"] == []

    def test_stale_break_is_not_reported(self) -> None:
        closes = _double_bottom_closes(True) + [100.0 + i * 0.1 for i in range(40)]  # broke out 40 bars ago
        res = patterns.detect("OLD", _candles(closes))
        assert all(p["pattern"] != "double_bottom" for p in res["patterns"])

    def test_too_little_history(self) -> None:
        res = patterns.detect("X", _candles([100.0] * 30))
        assert res["patterns"] == [] and "error" in res


class TestHeadShoulders:
    def test_bearish_head_and_shoulders_confirmed(self) -> None:
        closes = ([100.0] * 40 + _seg(100, 115, 12) + _seg(115, 104, 12)      # left shoulder 115, neck 104
                  + _seg(104, 125, 12) + _seg(125, 104, 12)                    # head 125, neck 104
                  + _seg(104, 115.5, 12) + _seg(115.5, 104, 10)                # right shoulder 115.5
                  + _seg(104, 98, 5))                                          # break below neckline
        res = patterns.detect("HS", _candles(closes))
        row = next((p for p in res["patterns"] if p["pattern"] == "head_shoulders"), None)
        assert row is not None, [p["pattern"] for p in res["patterns"]]
        assert row["direction"] == "bearish" and row["status"] == "confirmed"
        assert row["neckline"] == pytest.approx(104.0, abs=2.0)
        assert row["target"] < row["neckline"]
        labels = [pt["label"] for pt in row["points"]]
        assert labels == ["left shoulder", "neck", "head", "neck", "right shoulder"]

    def test_inverse_head_and_shoulders_forming(self) -> None:
        closes = ([100.0] * 40 + _seg(100, 85, 12) + _seg(85, 96, 12)
                  + _seg(96, 75, 12) + _seg(75, 96, 12)
                  + _seg(96, 85.5, 12) + _seg(85.5, 94, 10) + [94.5, 94.0, 94.8, 94.2, 94.6])
        res = patterns.detect("IHS", _candles(closes))
        row = next((p for p in res["patterns"] if p["pattern"] == "inverse_head_shoulders"), None)
        assert row is not None, [p["pattern"] for p in res["patterns"]]
        assert row["direction"] == "bullish" and row["status"] == "forming"
        assert row["target"] > row["neckline"]


class TestTripleAndTops:
    def test_triple_bottom_replaces_double(self) -> None:
        closes = ([100.0] * 40 + _seg(100, 80, 12) + _seg(80, 94, 12) + _seg(94, 80.3, 12)
                  + _seg(80.3, 94.5, 12) + _seg(94.5, 80.6, 12) + _seg(80.6, 93, 10) + _seg(93, 99, 5))
        res = patterns.detect("TB", _candles(closes))
        names = [p["pattern"] for p in res["patterns"]]
        assert "triple_bottom" in names and "double_bottom" not in names
        row = next(p for p in res["patterns"] if p["pattern"] == "triple_bottom")
        assert row["status"] == "confirmed" and len([pt for pt in row["points"] if pt["label"].startswith("low")]) == 3

    def test_double_top_forming(self) -> None:
        closes = ([100.0] * 40 + _seg(100, 120, 15) + _seg(120, 106, 15) + _seg(106, 119.6, 15)
                  + _seg(119.6, 109, 15) + [108.5, 109.0, 108.8, 109.2, 108.9, 109.1])
        res = patterns.detect("DT", _candles(closes))
        row = next((p for p in res["patterns"] if p["pattern"] == "double_top"), None)
        assert row is not None, [p["pattern"] for p in res["patterns"]]
        assert row["direction"] == "bearish" and row["status"] == "forming"
        assert row["neckline"] == pytest.approx(106.0, abs=1.5) and row["target"] < row["neckline"]


class TestCupHandle:
    def test_cup_with_handle(self) -> None:
        # Rounded cup: 60 bars down-and-up 20% deep, rims equal, then a 10-bar shallow handle.
        import math

        cup = [100.0 - 20.0 * math.sin(math.pi * i / 60) for i in range(61)]
        handle = _seg(100, 96, 6) + _seg(96, 99.5, 6)
        # Quiet base, a rise INTO the left rim (so the rim is a swing high), the cup, the handle.
        closes = [90.0] * 40 + _seg(90, 100, 10) + cup + handle
        res = patterns.detect("CUP", _candles(closes))
        row = next((p for p in res["patterns"] if p["pattern"] == "cup_handle"), None)
        assert row is not None, [p["pattern"] for p in res["patterns"]]
        assert row["direction"] == "bullish"
        assert 12 <= row["depth_pct"] <= 50 and row["handle_bars"] >= 5


class TestScanPersistence:
    def test_compute_persists_and_journals_confirmed_hits(self, monkeypatch) -> None:
        from app.services import leaders

        table = {"DB": _candles(_double_bottom_closes(True)), "FLAT": _candles([100.0] * 160)}
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym, []))
        monkeypatch.setattr(patterns, "universe_symbols", lambda name: ["DB", "FLAT", "MISSING"])
        monkeypatch.setattr(patterns, "_FETCH_PAUSE", 0.0)
        out = patterns.compute("EGX30", persist=True)
        assert "error" not in out
        assert out["scanned"] == 3 and out["skipped_no_data"] == 1
        assert out["found"] >= 1 and out["confirmed"] >= 1
        stored = patterns.latest("EGX30")
        assert stored["stored"] is True and stored["rows"][0]["symbol"] == "DB"
        assert patterns.latest("EGX30", status="forming")["rows"] == [] or all(
            r["status"] == "forming" for r in patterns.latest("EGX30", status="forming")["rows"])
        hits = db.query("SELECT scanner, symbol FROM scanner_hits")
        assert {(h["scanner"], h["symbol"]) for h in hits} >= {("pattern_double_bottom", "DB")}
        # Re-running the same day does not duplicate the scanner hit.
        patterns.compute("EGX30", persist=True)
        assert len(db.query("SELECT 1 FROM scanner_hits WHERE scanner = 'pattern_double_bottom'")) == 1

    def test_latest_empty_before_first_scan(self) -> None:
        assert patterns.latest("EGX70") == {"rows": [], "universe": "EGX70", "date": None, "stored": False}


class TestPlayedOut:
    def test_pattern_past_its_target_is_not_reported(self) -> None:
        # Double bottom that broke out and already ran far beyond the measured target.
        closes = _double_bottom_closes(True) + _seg(99, 125, 8)
        res = patterns.detect("DONE", _candles(closes))
        assert all(p["pattern"] != "double_bottom" for p in res["patterns"])

    def test_confirmed_pattern_reports_move_progress(self) -> None:
        res = patterns.detect("TEST", _candles(_double_bottom_closes(True)))
        row = next(p for p in res["patterns"] if p["pattern"] == "double_bottom")
        assert row["status"] == "confirmed"
        assert row["move_progress_pct"] is not None and 0 <= row["move_progress_pct"] < 100
        forming = patterns.detect("TEST", _candles(_double_bottom_closes(False)))
        assert next(p for p in forming["patterns"] if p["pattern"] == "double_bottom")["move_progress_pct"] is None


class TestNecklineSanity:
    def test_steep_neckline_head_and_shoulders_is_rejected(self) -> None:
        # Shoulders ~85, head 75, but the two neck points sit at 96 and 104:
        # extrapolated forward that "neckline" lands far above price. Reject.
        closes = ([100.0] * 40 + _seg(100, 85, 12) + _seg(85, 96, 12)
                  + _seg(96, 75, 12) + _seg(75, 104, 12)
                  + _seg(104, 85.5, 12) + _seg(85.5, 94, 10) + [94.5, 94.0, 94.8, 94.2, 94.6])
        res = patterns.detect("STEEP", _candles(closes))
        assert all(p["pattern"] != "inverse_head_shoulders" for p in res["patterns"])
