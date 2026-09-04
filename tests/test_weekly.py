"""Weekly context from resampled daily candles — resampling, trend context,
weekly zones, weekly structure rows, and their wiring into the checklist,
levels and patterns. Synthetic, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_wk_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, levels, patterns, weekly  # noqa: E402
from app.services.pattern_catalog import CATALOG  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


def _bars(rows, vols=None, start=datetime(2025, 9, 7)):
    """EGX week: Sunday–Thursday. ``start`` is a Sunday."""
    day = start
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        while day.weekday() in (4, 5):   # skip Fri/Sat
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c,
                    "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _seg(a, b, n):
    return [a + (b - a) * i / n for i in range(n)]


def _uptrend(n=250, start=50.0, step=0.2, wobble=15, amp=3.0):
    """Rising zig-zag: higher highs and higher lows on every timeframe."""
    closes = []
    px = start
    for i in range(n):
        px += step
        closes.append(px + (amp if (i // wobble) % 2 == 0 else -amp))
    return [(c, c + 0.6, c - 0.6, c) for c in closes]


def _downtrend(n=250, start=100.0, step=0.2, wobble=15, amp=3.0):
    closes = []
    px = start
    for i in range(n):
        px -= step
        closes.append(px + (amp if (i // wobble) % 2 == 0 else -amp))
    return [(c, c + 0.6, c - 0.6, c) for c in closes]


def _range_bound(n_cycles=6, lo=90.0, hi=110.0, leg=20):
    closes = []
    for _ in range(n_cycles):
        closes += _seg(lo, hi, leg) + _seg(hi, lo, leg)
    return [(c, c + 0.6, c - 0.6, c) for c in closes]


class TestResample:
    def test_groups_by_iso_week_with_ohlcv(self) -> None:
        rows = [(10, 12, 9, 11), (11, 13, 10, 12), (12, 12.5, 11, 11.5), (11.5, 14, 11, 13), (13, 13.5, 12, 12.5),  # week 1 (Sun–Thu)
                (12.5, 15, 12, 14), (14, 14.5, 13, 13.5)]                                                          # week 2 (Sun, Mon)
        vols = [100, 200, 300, 400, 500, 600, 700]
        wk = weekly.resample(_bars(rows, vols))
        assert len(wk) == 2
        w1, w2 = wk
        assert (w1["open"], w1["high"], w1["low"], w1["close"]) == (10, 14, 9, 12.5)
        assert w1["volume"] == 1500 and w1["sessions"] == 5
        assert w1["time"] == "2025-09-11" and w1["week_start"] == "2025-09-07"   # Thursday / Sunday
        assert w1["partial"] is False
        assert (w2["open"], w2["close"], w2["sessions"]) == (12.5, 13.5, 2)
        assert w2["partial"] is True                                             # ended on a Monday

    def test_newest_weekly_bar_shares_the_daily_as_of(self) -> None:
        daily = _bars(_uptrend(60))
        wk = weekly.resample(daily)
        assert wk[-1]["time"] == daily[-1]["time"]

    def test_skips_bad_rows(self) -> None:
        daily = _bars([(1, 2, 0.5, 1.5)] * 5)
        daily.insert(2, {"time": "garbage", "close": 1.0})
        daily.insert(0, {"time": "2025-09-07", "close": None})
        assert len(weekly.resample(daily)) == 1


class TestContext:
    def test_uptrend_reads_up(self) -> None:
        ctx = weekly.context(_bars(_uptrend()))
        assert "error" not in ctx
        assert ctx["trend"] == "up" and ctx["structure"] == "higher_high_higher_low"
        assert ctx["above_sma10"] and ctx["above_sma40"] and ctx["sma40_rising"]
        assert ctx["text"].startswith("Weekly:") and "larger trend is up" in ctx["text"]
        assert ctx["bars"] >= 40

    def test_downtrend_reads_down(self) -> None:
        ctx = weekly.context(_bars(_downtrend()))
        assert ctx["trend"] == "down" and ctx["structure"] == "lower_high_lower_low"
        assert "counter-trend" in ctx["text"]

    def test_too_few_weeks(self) -> None:
        ctx = weekly.context(_bars(_uptrend(40)))
        assert "error" in ctx


class TestZones:
    def test_range_bound_market_has_weekly_zones_at_both_edges(self) -> None:
        z = weekly.zones(_bars(_range_bound()))
        assert z, "no weekly zones found"
        assert all(x["touches"] >= 2 and x["timeframe"] == "1W" and x["source"] == "weekly swings" for x in z)
        lv = sorted(x["level"] for x in z)
        assert abs(lv[0] - 90.0) < 3.0 and abs(lv[-1] - 110.0) < 3.0

    def test_levels_card_carries_weekly_zones_and_flags(self) -> None:
        lv = levels.compute("RNG", _bars(_range_bound() + [(c, c + 0.6, c - 0.6, c) for c in _seg(90, 95, 8)]))
        assert "error" not in lv
        assert "weekly_supports" in lv and "weekly_resistances" in lv
        assert lv["weekly_supports"] or lv["weekly_resistances"]
        flagged = [l for l in lv["supports"] + lv["resistances"] if l.get("weekly")]
        assert flagged, "a daily level on a weekly zone should be flagged"
        assert all("weekly_touches" in l for l in flagged)
        # Chart zones include weekly ones not already covered by a daily level.
        assert any(k.get("timeframe") == "1W" or k.get("weekly") for k in lv["key_levels"])
        assert "Weekly zones" in lv["basis"]

    def test_daily_ranking_unchanged_by_weekly(self) -> None:
        lv = levels.compute("RNG", _bars(_range_bound() + [(c, c + 0.6, c - 0.6, c) for c in _seg(90, 95, 8)]))
        assert all(l["source"] != "weekly swings" for l in lv["supports"] + lv["resistances"])


class TestStructureRows:
    def test_weekly_rows_are_tagged_and_in_catalog(self) -> None:
        rows = weekly.structure_rows(_bars(_uptrend()))
        assert rows
        keys = {r["pattern"] for r in rows}
        assert "weekly_higher_high_higher_low" in keys
        for r in rows:
            assert r["pattern"].startswith("weekly_") and r["timeframe"] == "1W"
            assert r["pattern"] in CATALOG
            assert r["weekly_bars"] >= 20

    def test_downtrend_gives_lower_lows(self) -> None:
        keys = {r["pattern"] for r in weekly.structure_rows(_bars(_downtrend()))}
        assert "weekly_lower_high_lower_low" in keys

    def test_detect_includes_weekly_rows_with_months_horizon(self) -> None:
        res = patterns.detect("UP", _bars(_uptrend()))
        wk = [r for r in res["patterns"] if r.get("timeframe") == "1W"]
        assert wk
        assert all(r["label"].startswith("Weekly") for r in wk)
        assert all(r["horizon"] in ("weeks", "months") for r in wk)

    def test_weekly_and_daily_structure_are_separate_events(self) -> None:
        res = patterns.detect("UP", _bars(_uptrend()))
        d = next((r for r in res["patterns"] if r["pattern"] == "higher_high_higher_low"), None)
        w = next((r for r in res["patterns"] if r["pattern"] == "weekly_higher_high_higher_low"), None)
        assert d is not None and w is not None
        assert d["event_id"] != w["event_id"]


class TestChecklistWiring:
    def _patch(self, monkeypatch, candles):
        from app.services import leaders, market

        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
        monkeypatch.setattr(market, "median_daily_value", lambda sym, days=20: 50_000_000.0)

    def test_trend_pillar_carries_weekly_sentence(self, monkeypatch) -> None:
        self._patch(monkeypatch, _bars(_uptrend()))
        ck = checklist.checklist("UP")
        trend = next(p for p in ck["pillars"] if p["key"] == "trend")
        assert "Weekly:" in trend["text"]
        assert trend["status"] == "pass"
        assert trend["weekly"]["trend"] == "up"

    def test_daily_bounce_inside_weekly_downtrend_is_a_warning(self, monkeypatch) -> None:
        # Long weekly downtrend, then a 30-session daily bounce (+9%) that lifts
        # price over the 20/50-day averages but not over the 40-week.
        rows = _downtrend(220, start=140.0)
        last = rows[-1][3]
        rows += [(c, c + 0.6, c - 0.6, c) for c in _seg(last, last * 1.09, 30)]
        self._patch(monkeypatch, _bars(rows))
        ck = checklist.checklist("BOUNCE")
        trend = next(p for p in ck["pillars"] if p["key"] == "trend")
        assert trend["weekly"]["trend"] == "down", trend
        assert trend["status"] == "warn"
        assert "counter-trend bounce" in trend["text"]

    def test_weekly_rows_do_not_count_as_price_action_events(self, monkeypatch) -> None:
        self._patch(monkeypatch, _bars(_uptrend()))
        ck = checklist.checklist("UP")
        pa = next(p for p in ck["pillars"] if p["key"] == "price_action")
        assert "Weekly" not in pa["text"]
