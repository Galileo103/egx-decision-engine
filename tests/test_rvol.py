"""Task 4 — relative volume (volume / 20-day median) as a first-class number."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_rvol_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, edge, leaders, pattern_common, patterns, regime, replay, scorecard  # noqa: E402
from app.services import rule_scanner, rules_backtest as RB, screeners  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("scanner_hits", "signal_outcomes", "proven_edge", "snapshots", "regime_daily"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    scorecard.invalidate_weights()
    regime.invalidate()
    yield


def _bars(closes, vols, start=datetime(2025, 1, 2)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.3,
                    "low": min(o, c) - 0.3, "close": c, "volume": vols[i]})
        day += timedelta(days=1)
    return out


class TestRvolMath:
    def test_median_based_and_robust_to_one_block_trade(self) -> None:
        vols = [100.0] * 20 + [300.0]
        c = _bars([10.0] * 21, vols)
        assert pattern_common.rvol(c) == 3.0
        # one 20x block trade inside the window barely moves the MEDIAN (a mean would double)
        vols2 = [100.0] * 10 + [2000.0] + [100.0] * 9 + [300.0]
        assert pattern_common.rvol(_bars([10.0] * 21, vols2)) == 3.0
        # needs 10 prior bars with volume
        assert pattern_common.rvol(_bars([10.0] * 6, [100.0] * 6)) is None
        # index form and buckets
        assert pattern_common.rvol(c, 20) == 3.0 and pattern_common.rvol(c, -1) == 3.0
        assert pattern_common.rvol_bucket(0.9) == "lt1" and pattern_common.rvol_bucket(1.2) == "1_1.5"
        assert pattern_common.rvol_bucket(1.5) == "ge1.5" and pattern_common.rvol_bucket(None) is None

    def test_ind_series_matches_helper(self) -> None:
        vols = [100.0 + (i % 3) * 10 for i in range(40)]
        vols[-1] = 250.0
        c = _bars([10.0 + 0.1 * i for i in range(40)], vols)
        x = RB.Ind(c)
        assert x.rvol[-1] == pattern_common.rvol(c)
        assert x.rvol[0] is None and x.rvol[5] is None and x.rvol[15] is not None


class TestStamps:
    def test_rule_scanner_and_replay_stamp_rvol(self) -> None:
        # a 20-day-high breakout on 3x volume
        closes = [10.0 + 0.02 * i for i in range(160)] + [14.0]
        vols = [100.0] * 160 + [300.0]
        c = _bars(closes, vols)
        live = rule_scanner.rule_hits_last_bar("AAA", c)
        assert live and all(h["rvol"] == 3.0 for h in live)
        hist = replay.rule_hits("AAA", c)
        last = [h for h in hist if h["date"] == c[-1]["time"]]
        assert last and all(h["payload"]["rvol"] == 3.0 for h in last)

    def test_pattern_rows_carry_rvol(self, monkeypatch) -> None:
        from app.services import pattern_action, pattern_candles, pattern_geometry, weekly

        closes = [10.0 + 0.01 * i for i in range(120)]
        vols = [100.0] * 119 + [200.0]
        c = _bars(closes, vols)
        brk_day = c[-3]["time"]
        monkeypatch.setattr(pattern_candles, "detect", lambda cc, atr: [
            {"pattern": "marubozu", "status": "confirmed", "quality": 60, "direction": "bullish",
             "neckline": None, "target": None, "start_date": cc[-2]["time"], "break_date": brk_day},
            {"pattern": "hammer", "status": "forming", "quality": 55, "direction": "bullish",
             "neckline": None, "target": None, "start_date": cc[-2]["time"]}])
        monkeypatch.setattr(pattern_action, "detect", lambda cc, atr: [])
        monkeypatch.setattr(pattern_geometry, "detect", lambda cc, atr: [])
        monkeypatch.setattr(weekly, "structure_rows", lambda cc: [])
        out = patterns.detect("AAA", c, view="all")
        by = {r["pattern"]: r for r in out["patterns"]}
        assert by["marubozu"]["rvol"] == 1.0        # break day traded the median
        assert by["hammer"]["rvol"] == 2.0          # forming: last bar

    def test_checklist_volume_pillar_leads_with_todays_rvol(self, monkeypatch) -> None:
        monkeypatch.setattr(regime, "current_state", lambda: "bull")
        monkeypatch.setattr(patterns, "detect", lambda sym, cc=None, view="all": {"patterns": []})
        closes = [10.0 + 0.02 * i for i in range(200)]
        vols = [100.0] * 199 + [220.0]
        out = checklist.checklist("AAA", candles=_bars(closes, vols), regime_state="bull")
        vol = next(p for p in out["pillars"] if p["key"] == "volume")
        assert vol["status"] == "pass" and vol["rvol"] == 2.2 and "2.2×" in vol["text"] and "surge" in vol["text"]
        assert out["rvol"] == 2.2
        # heavy volume on a DOWN day fails the pillar
        closes2 = closes[:-1] + [closes[-2] - 0.5]
        out2 = checklist.checklist("AAA", candles=_bars(closes2, vols), regime_state="bull")
        vol2 = next(p for p in out2["pillars"] if p["key"] == "volume")
        assert vol2["status"] == "fail" and "DOWN day" in vol2["text"]


class TestScorecardSplit:
    def _hit(self, i: int, rv: float, exc: float, scanner: str = "range_breakout") -> None:
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES (?, ?, ?, ?, 'x', 'replay')",
                   (f"2024-03-{(i % 28) + 1:02d}", scanner, f"S{i}", json.dumps({"rvol": rv})))
        hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
        db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, ret_10, "
                   "bench_10, excess_10, graded_at, source) VALUES (?, '2024-03-01', ?, ?, '2024-03-01', 10, ?, 0, ?, "
                   "'x', 'replay')", (hid, scanner, f"S{i}", exc, exc))

    def test_by_rvol_and_multipliers(self) -> None:
        # heavy-volume hits: 80% right; quiet hits: 20% right
        for i in range(25):
            self._hit(i, 2.0, 3.0 if i % 5 else -1.0)
        for i in range(25, 50):
            self._hit(i, 0.6, 3.0 if i % 5 == 0 else -1.0)
        card = scorecard.scorecard()
        sc = card["scanners"]["range_breakout"]
        assert sc["by_rvol"]["ge1.5"]["10"]["beat_rate"] == 80.0
        assert sc["by_rvol"]["lt1"]["10"]["beat_rate"] == 20.0
        assert sc["horizons"]["10"]["beat_rate"] == 50.0
        # multipliers = bucket beat rate / overall, clamped to [0.7, 1.3]
        assert card["rvol_multipliers"]["ge1.5"]["range_breakout"] == 1.3
        assert card["rvol_multipliers"]["lt1"]["range_breakout"] == 0.7
        assert card["outcomes_with_rvol"] == 50
        base = scorecard.signal_weights()["range_breakout"]
        assert scorecard.signal_weights(None, "ge1.5")["range_breakout"] == pytest.approx(round(base * 1.3, 3))
        assert scorecard.signal_weights(None, "lt1")["range_breakout"] == pytest.approx(round(base * 0.7, 3))
        assert scorecard.signal_weights(None, "1_1.5")["range_breakout"] == base   # unmeasured bucket
        # the live proxy inherits the multiplier
        assert card["rvol_multipliers"]["ge1.5"]["volume_breakout"] == 1.3

    def test_edge_rows_and_volume_block(self, monkeypatch) -> None:
        for i in range(25):
            self._hit(i, 2.0, 3.0)
        for i in range(25, 50):
            self._hit(i, 0.6, 0.0)
        rows = edge._scorecard_rows()
        row = next(r for r in rows if r["name"] == "range_breakout")
        assert row["extra"]["by_rvol"]["ge1.5"]["n"] == 25 and row["extra"]["by_rvol"]["ge1.5"]["verdict"] == "edge"
        assert row["extra"]["by_rvol"]["lt1"]["verdict"] in ("marginal", "negative")
        block = edge._volume_block(rows)
        assert block["measured"] is True
        assert [m["name"] for m in block["volume_matters"]] == ["range_breakout"]

    def test_regrade_backfills_payload_rvol(self, monkeypatch) -> None:
        closes = [10.0 + 0.01 * i for i in range(300)]
        vols = [100.0] * 300
        vols[200] = 250.0
        c = _bars(closes, vols)
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": c)
        monkeypatch.setattr(leaders, "benchmark_series", lambda force=False, range_="1y":
                            {"source": "t", "dates": [b["time"] for b in c], "series": {b["time"]: 100.0 for b in c}})
        monkeypatch.setattr(regime, "backfill", lambda range_="5y", progress=None: {"rows": 0})
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES (?, 'momentum_3', 'AAA', '{}', 'x', 'replay')", (c[200]["time"],))
        out = scorecard.regrade(only_incomplete=True, range_="5y")
        assert "error" not in out and out["regraded"] == 1 and out["rvol_stamped"] == 1
        payload = json.loads(db.query("SELECT payload_json FROM scanner_hits")[0]["payload_json"])
        assert payload["rvol"] == 2.5


class TestCandidatesUseVolume:
    def test_latest_candidates_carry_rvol_and_bucket_weights(self, monkeypatch) -> None:
        monkeypatch.setattr(screeners, "_current_regime", lambda: None)
        monkeypatch.setattr(screeners, "_rvol_for", lambda sym: None)
        weights_by = {None: {"range_breakout": 1.0}, "ge1.5": {"range_breakout": 1.3}, "lt1": {"range_breakout": 0.7},
                      "1_1.5": {"range_breakout": 1.0}}
        monkeypatch.setattr(screeners, "_signal_weights", lambda regime=None, rvol_bucket=None: dict(weights_by[rvol_bucket]))
        for sym, rv in (("HEAVY", 2.1), ("QUIET", 0.5)):
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                       "VALUES ('2026-09-06', 'range_breakout', ?, ?, 'x', 'live')", (sym, json.dumps({"price": 10, "rvol": rv})))
        out = screeners.latest_candidates()
        by = {c["symbol"]: c for c in out["candidates"]}
        assert by["HEAVY"]["rvol"] == 2.1 and by["QUIET"]["rvol"] == 0.5
        assert by["HEAVY"]["evidence_weight"] == 1.3 and by["QUIET"]["evidence_weight"] == 0.7
        assert [c["symbol"] for c in out["candidates"]] == ["HEAVY", "QUIET"]
