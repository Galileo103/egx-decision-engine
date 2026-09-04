"""Support/resistance zones and the six-pillar checklist — synthetic, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_lv_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, levels  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


def _bars(rows, vols=None):
    day = datetime(2025, 9, 1)
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c,
                    "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _seg(a, b, n):
    return [a + (b - a) * i / n for i in range(n)]


def _range_bound(n_cycles=4, lo=90.0, hi=110.0, leg=12):
    """Price bouncing between lo and hi several times — textbook tested zones."""
    closes = []
    for _ in range(n_cycles):
        closes += _seg(lo, hi, leg) + _seg(hi, lo, leg)
    rows = [(c, c + 0.6, c - 0.6, c) for c in closes]
    return rows


class TestLevels:
    def test_tested_zones_are_found_and_ranked(self) -> None:
        rows = _range_bound() + [(c, c + 0.6, c - 0.6, c) for c in _seg(90, 95, 8)]  # end near support
        lv = levels.compute("RNG", _bars(rows))
        assert "error" not in lv
        sup = [s for s in lv["supports"] if s["source"].startswith("swings")]
        res = [r for r in lv["resistances"] if r["source"].startswith("swings")]
        assert sup and abs(sup[0]["level"] - 90.0) < 1.5
        assert res and abs(res[0]["level"] - 110.0) < 1.5
        assert res[0]["touches"] >= 3 and sup[0]["touches"] >= 3
        assert lv["room_up_pct"] > lv["room_down_pct"]
        assert all(k["touches"] >= 2 for k in lv["key_levels"])

    def test_position_labels(self) -> None:
        near_sup = _range_bound() + [(c, c + 0.4, c - 0.4, c) for c in [91.0, 90.6, 90.8, 90.5]]
        assert levels.compute("A", _bars(near_sup))["position"] == "at support"
        near_res = _range_bound() + [(c, c + 0.4, c - 0.4, c) for c in _seg(90, 109.5, 12)] + [(109.4, 109.9, 109.0, 109.5)]
        assert levels.compute("B", _bars(near_res))["position"] == "at resistance"
        breakout = _range_bound() + [(c, c + 0.5, c - 0.5, c) for c in _seg(90, 125, 20)]
        pos = levels.compute("C", _bars(breakout))["position"]
        assert pos in ("breaking out", "mid-range")

    def test_plan_checks_flag_stop_above_support_and_target_at_resistance(self) -> None:
        lv = levels.compute("RNG", _bars(_range_bound() + [(c, c + 0.6, c - 0.6, c) for c in _seg(90, 100, 8)]))
        sup = next(s for s in lv["supports"] if s["source"].startswith("swings"))
        res = next(r for r in lv["resistances"] if r["source"].startswith("swings"))
        msgs = levels.plan_checks(lv, stop=sup["level"] + 0.3, targets=[res["level"] - 0.2, None])
        assert any("just ABOVE a support" in m for m in msgs)
        assert any("right at a resistance" in m for m in msgs)
        assert levels.plan_checks(lv, stop=sup["level"] - 2.0, targets=[None, None]) == []

    def test_too_little_history(self) -> None:
        assert "error" in levels.compute("X", _bars([(100, 101, 99, 100)] * 30))


class TestChecklist:
    def _patch(self, monkeypatch, candles):
        from app.services import leaders, market

        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
        monkeypatch.setattr(market, "median_daily_value", lambda sym, days=20: 50_000_000.0)

    def test_clean_uptrend_on_support_scores_high(self, monkeypatch) -> None:
        # Rising channel: higher highs/lows, then a pullback to the rising support with buyers' volume.
        closes, vols = [], []
        px = 100.0
        for cyc in range(6):
            up = _seg(px, px * 1.10, 15)
            dn = _seg(px * 1.10, px * 1.04, 8)
            closes += up + dn
            vols += [150_000] * 15 + [80_000] * 8
            px = px * 1.04
        # End on the first sessions of a fresh up-leg: buyers back with volume.
        closes += _seg(px, px * 1.03, 5)
        vols += [170_000] * 5
        rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
        self._patch(monkeypatch, _bars(rows, vols))
        ck = checklist.checklist("UP")
        assert "error" not in ck
        st = {p["key"]: p["status"] for p in ck["pillars"]}
        assert st["trend"] == "pass"
        assert st["volume"] == "pass"
        assert st["risk"] in ("pass", "warn")
        assert ck["verdict"] in ("setup", "watch") and ck["score"] >= 3
        assert ck["risk_plan"]["stop"] < ck["price"] < ck["risk_plan"]["target"]

    def test_downtrend_is_no_setup(self, monkeypatch) -> None:
        closes = _seg(150, 90, 150)
        rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
        self._patch(monkeypatch, _bars(rows))
        ck = checklist.checklist("DOWN")
        st = {p["key"]: p["status"] for p in ck["pillars"]}
        assert st["trend"] == "fail"
        assert ck["verdict"] == "no_setup" and "trend" in ck["headline"].lower()

    def test_illiquid_fails_risk(self, monkeypatch) -> None:
        from app.services import leaders, market

        closes = _seg(100, 120, 150)
        rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": _bars(rows, [500] * 150))
        monkeypatch.setattr(market, "median_daily_value", lambda sym, days=20: 40_000.0)
        ck = checklist.checklist("THIN")
        st = {p["key"]: p["status"] for p in ck["pillars"]}
        assert st["risk"] == "fail" and "Illiquid" in next(p["text"] for p in ck["pillars"] if p["key"] == "risk")
        assert ck["verdict"] == "no_setup"

    def test_short_history_errors_cleanly(self, monkeypatch) -> None:
        self._patch(monkeypatch, _bars([(100, 101, 99, 100)] * 50))
        assert "error" in checklist.checklist("SHORT")
