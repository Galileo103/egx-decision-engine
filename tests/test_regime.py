"""Market regime + longer grading horizons — synthetic candles, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_regime_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app import symbols as symbols_mod  # noqa: E402
from app.services import checklist, edge, leaders, regime, scorecard  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("scanner_hits", "signal_outcomes", "proven_edge", "regime_daily"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    regime.invalidate()
    scorecard.invalidate_weights()
    yield


# ── synthetic market ─────────────────────────────────────────────────────────


def _bars(closes, start=datetime(2023, 1, 2)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.3,
                    "low": min(o, c) - 0.3, "close": c, "volume": 100_000})
        day += timedelta(days=1)
    return out


def _trend(n, start, step):
    return [start + step * i for i in range(n)]


def _index_bull_then_bear(n_up=200, n_down=120):
    """Index rises steadily, then falls steadily."""
    up = _trend(n_up, 1000.0, 2.0)
    down = _trend(n_down, up[-1], -3.0)
    return _bars(up + down)


def _bench_from(candles):
    return {"source": "test", "dates": [c["time"] for c in candles],
            "series": {c["time"]: float(c["close"]) for c in candles}}


def _install(monkeypatch, index_candles, table):
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym.upper(), []))
    monkeypatch.setattr(leaders, "benchmark_series",
                        lambda force=False, range_="1y": _bench_from(index_candles))
    monkeypatch.setattr(symbols_mod, "universe", lambda name: [s for s in table if s != "^CASE30"])


# ── classification ───────────────────────────────────────────────────────────


class TestClassify:
    def test_states(self) -> None:
        # rising 50d, price above, broad participation
        assert regime.classify(110, 100, 95, 60) == "bull"
        # rising 50d, price above, but narrow participation -> not a bull
        assert regime.classify(110, 100, 95, 40) == "neutral"
        # falling 50d, price below -> bear regardless of breadth
        assert regime.classify(90, 100, 105, 70) == "bear"
        # index flat-ish but almost nothing above its average -> bear
        assert regime.classify(101, 100, 100, 20) == "bear"
        # index in an uptrend with thin breadth stays neutral, not bear
        assert regime.classify(110, 100, 95, 20) == "neutral"
        # unknown breadth: the index alone decides, and an uptrend is bull
        assert regime.classify(110, 100, 95, None) == "bull"
        assert regime.classify(None, None, None, 50) is None

    def test_sentence_mentions_state_and_breadth(self) -> None:
        txt = regime.sentence({"state": "bear", "index_close": 1000, "sma50": 1100, "sma200": 1050, "breadth_pct": 22})
        assert txt.startswith("Bear tape") and "22%" in txt and "below" in txt
        assert regime.sentence({}).startswith("Market regime unknown")


class TestSeries:
    def test_at_uses_latest_row_on_or_before_within_gap(self) -> None:
        rs = regime.RegimeSeries([{"date": "2024-01-02", "state": "bull"}, {"date": "2024-01-10", "state": "bear"}])
        assert rs.at("2024-01-02") == "bull"
        assert rs.at("2024-01-09") == "bull"
        assert rs.at("2024-01-10") == "bear"
        assert rs.at("2024-01-15") == "bear"
        assert rs.at("2023-12-31") is None
        assert rs.at("2024-03-01") is None      # too far past the last row
        assert regime.RegimeSeries([]).at("2024-01-01") is None


# ── compute / persist ────────────────────────────────────────────────────────


class TestCompute:
    def test_compute_persists_bull_then_bear(self, monkeypatch) -> None:
        idx = _index_bull_then_bear()
        # two members that follow the index: above their SMA50 while it rises, below after
        members = {"AAA": _bars([c["close"] * 0.01 for c in idx]), "BBB": _bars([c["close"] * 0.02 for c in idx])}
        _install(monkeypatch, idx, members)
        out = regime.compute("5y", persist=True)
        assert "error" not in out and out["rows"] > 200
        assert out["counts"]["bull"] > 50 and out["counts"]["bear"] > 30
        rows = db.query("SELECT date, state, breadth_pct FROM regime_daily ORDER BY date")
        assert rows[100]["state"] == "bull" and rows[100]["breadth_pct"] is None   # < MIN_BREADTH_MEMBERS members
        assert rows[-1]["state"] == "bear"
        cur = regime.current()
        assert cur["state"] == "bear" and cur["measured"] is True and "Bear tape" in cur["text"]
        assert regime.state_at(rows[100]["date"]) == "bull"

    def test_breadth_counts_members_above_sma50(self, monkeypatch) -> None:
        idx = _index_bull_then_bear()
        rising = {f"R{i}": _bars(_trend(len(idx), 10.0 + i, 0.05)) for i in range(15)}
        falling = {f"F{i}": _bars(_trend(len(idx), 100.0 + i, -0.2)) for i in range(10)}
        _install(monkeypatch, idx, {**rising, **falling})
        out = regime.compute("5y", persist=True)
        assert "error" not in out
        last = out["latest"]
        assert last["breadth_pct"] == pytest.approx(60.0)      # 15 of 25 above
        # a rising index with only 60% breadth is bull; the index turned down -> bear
        assert last["state"] == "bear"
        mid = db.query("SELECT state, breadth_pct FROM regime_daily ORDER BY date")[120]
        assert mid["state"] == "bull" and mid["breadth_pct"] == pytest.approx(60.0)

    def test_short_index_history_is_an_error_not_a_crash(self, monkeypatch) -> None:
        _install(monkeypatch, _bars(_trend(30, 100.0, 1.0)), {})
        out = regime.compute("1y")
        assert "error" in out
        assert regime.current()["state"] is None


# ── grading: horizons + regime stamp ─────────────────────────────────────────


class TestGrading:
    def test_grade_hit_fills_40_60_and_regime(self) -> None:
        candles = _bars([100.0 + i for i in range(80)])
        bench = {"dates": [c["time"] for c in candles], "series": {c["time"]: 1000.0 for c in candles}}
        regimes = regime.RegimeSeries([{"date": candles[0]["time"], "state": "bull"}])
        hit = {"hit_id": 1, "date": candles[3]["time"], "scanner": "squeeze", "symbol": "AAA"}
        out = scorecard.grade_hit(hit, candles, bench, regimes)
        assert out["ret_40"] == pytest.approx(40 / 103 * 100, abs=1e-3)
        assert out["ret_60"] == pytest.approx(60 / 103 * 100, abs=1e-3)
        assert out["excess_60"] == pytest.approx(out["ret_60"])
        assert out["regime"] == "bull"
        # a dict also works as the regime source; None leaves the stamp empty
        assert scorecard.grade_hit(hit, candles, bench, {candles[3]["time"]: "bear"})["regime"] == "bear"
        assert scorecard.grade_hit(hit, candles, bench)["regime"] is None

    def test_regrade_fills_missing_columns_without_new_detection(self, monkeypatch) -> None:
        idx = _index_bull_then_bear()
        stock = _bars([50.0 + 0.1 * i for i in range(len(idx))])
        _install(monkeypatch, idx, {"AAA": stock})
        # an old-style outcome row: 10-session columns only, no regime, no 40/60
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES (?, 'range_breakout', 'AAA', '{}', 'x', 'replay')", (stock[60]["time"],))
        hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
        db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, ret_10, "
                   "bench_10, excess_10, graded_at, source) VALUES (?, ?, 'range_breakout', 'AAA', ?, 56, 1, 0, 1, 'x', 'replay')",
                   (hid, stock[60]["time"], stock[60]["time"]))
        out = scorecard.regrade(only_incomplete=True, range_="5y")
        assert "error" not in out and out["regraded"] == 1 and out["with_regime"] == 1
        row = db.query("SELECT * FROM signal_outcomes")[0]
        assert row["ret_40"] is not None and row["ret_60"] is not None and row["regime"] == "bull"
        assert db.query("SELECT COUNT(*) AS n FROM scanner_hits")[0]["n"] == 1     # no new hits
        # a second incomplete-only pass finds nothing to do
        assert scorecard.regrade(only_incomplete=True, range_="5y")["regraded"] == 0

    def test_scorecard_splits_by_regime_and_weights_follow_todays_tape(self) -> None:
        # baseline yardsticks: all-weather 44%, bull 55%, bear 30%
        import json
        db.execute("INSERT INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, metric_label, "
                   "verdict, verdict_text, extra_json, universe, computed_at) VALUES ('baseline', 'random_entry_10d', "
                   "'', '5y', 1000, 44, 0.4, '', 'baseline', '', ?, 'T', 'x')",
                   (json.dumps({"beat_rate": 44.0, "under_rate": 56.0, "avg_excess": 0.4,
                                "by_regime": {"bull": {"beat_rate": 55.0, "under_rate": 45.0, "avg_excess": 1.0, "sessions": 500},
                                              "bear": {"beat_rate": 30.0, "under_rate": 70.0, "avg_excess": -1.0, "sessions": 500}}}),))
        # 30 bull-tape hits all right, 30 bear-tape hits all wrong
        for i in range(60):
            state = "bull" if i < 30 else "bear"
            exc = 3.0 if state == "bull" else -3.0
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                       "VALUES (?, 'momentum_3', ?, '{}', 'x', 'replay')", (f"2024-01-{(i % 28) + 1:02d}", f"S{i}"))
            hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
            db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, ret_10, "
                       "bench_10, excess_10, graded_at, source, regime) VALUES (?, '2024-01-01', 'momentum_3', ?, "
                       "'2024-01-01', 10, ?, 0, ?, 'x', 'replay', ?)", (hid, f"S{i}", exc, exc, state))
        card = scorecard.scorecard()
        sc = card["scanners"]["momentum_3"]
        assert sc["horizons"]["10"]["n"] == 60 and sc["horizons"]["10"]["beat_rate"] == 50.0
        assert sc["by_regime"]["bull"]["10"]["beat_rate"] == 100.0
        assert sc["by_regime"]["bear"]["10"]["beat_rate"] == 0.0
        # bull: judged against the bull yardstick (55%), bear against 30%
        assert sc["by_regime"]["bull"]["10"]["beat_vs_random_pp"] == pytest.approx(45.0)
        assert sc["by_regime"]["bear"]["10"]["beat_vs_random_pp"] == pytest.approx(-30.0)
        assert card["regime_weights"]["bull"]["momentum_3"] == scorecard._WEIGHT_CAP
        assert card["regime_weights"]["bear"]["momentum_3"] == scorecard._WEIGHT_FLOOR
        # all-weather weight: 50% vs 44% -> 1.12
        assert card["weights"]["momentum_3"] == pytest.approx(1.12)
        assert scorecard.signal_weights()["momentum_3"] == pytest.approx(1.12)
        assert scorecard.signal_weights("bull")["momentum_3"] == scorecard._WEIGHT_CAP
        assert scorecard.signal_weights("bear")["momentum_3"] == scorecard._WEIGHT_FLOOR
        assert scorecard.signal_weights("neutral")["momentum_3"] == pytest.approx(1.12)   # no neutral sample
        # the live proxy inherits the regime weight too
        assert card["regime_weights"]["bear"]["momentum"] == scorecard._WEIGHT_FLOOR


# ── edge table: reference horizons + regime split ────────────────────────────


class TestEdgeHorizons:
    def test_reference_horizon_by_kind(self) -> None:
        assert edge.reference_horizon("momentum_3") == 10
        assert edge.reference_horizon("checklist_setup") == 10
        assert edge.reference_horizon("pattern_hammer") == 10            # candlestick
        assert edge.reference_horizon("pattern_bull_trap") == 20         # price action
        assert edge.reference_horizon("pattern_triple_top") == 40        # reversal
        assert edge.reference_horizon("pattern_ascending_triangle") == 40

    def test_scorecard_rows_judge_patterns_at_their_horizon(self) -> None:
        # a cup & handle that is +0.3% at 10 sessions (coin flip) but +5% at 40: edge at its reference horizon
        for i in range(25):
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                       "VALUES (?, 'pattern_cup_handle', ?, '{}', 'x', 'replay')", (f"2024-02-{(i % 28) + 1:02d}", f"C{i}"))
            hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
            db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, "
                       "ret_10, bench_10, excess_10, ret_40, bench_40, excess_40, graded_at, source, regime) "
                       "VALUES (?, '2024-02-01', 'pattern_cup_handle', ?, '2024-02-01', 10, 0.3, 0, 0.3, 5.0, 0, 5.0, 'x', "
                       "'replay', 'bull')", (hid, f"C{i}"))
        rows = edge._scorecard_rows()
        row = next(r for r in rows if r["name"] == "pattern_cup_handle")
        assert row["extra"]["horizon"] == 40 and row["verdict"] == "edge" and row["edge_metric"] == 5.0
        assert row["extra"]["horizons"]["10"]["verdict"] == "marginal"
        assert row["extra"]["by_regime"]["bull"]["n"] == 25 and row["extra"]["by_regime"]["bull"]["verdict"] == "edge"
        assert "40 sessions" in row["metric_label"]
        block = edge._regime_block(rows)
        assert block["measured"] is True and block["counts"]["bull"]["edge"] == 1


# ── checklist: the market gate ───────────────────────────────────────────────


class TestChecklistGate:
    def test_bear_tape_turns_setup_into_watch_only(self) -> None:
        v, h, m = checklist._market_gate("setup", "Setup: 6 of 6.", "bear")
        assert v == "watch" and h.startswith("Market against it") and m["applied"] is True and m["raw_verdict"] == "setup"
        v, _, m = checklist._market_gate("watch", "x", "bear")
        assert v == "watch" and m["applied"] is False
        v, _, m = checklist._market_gate("no_setup", "x", "bull")
        assert v == "no_setup" and m["state"] == "bull" and "Bull tape" in m["text"]
        v, _, m = checklist._market_gate("setup", "x", "bull")
        assert v == "setup"
        v, _, m = checklist._market_gate("setup", "x", "unknown")
        assert v == "setup" and m["state"] is None and "unknown" in m["text"]

    def test_live_checklist_reads_stored_regime(self, monkeypatch) -> None:
        idx = _index_bull_then_bear()
        # a stock in a clean uptrend on every pillar-friendly measure
        stock = _bars([20.0 + 0.05 * i + (0.2 if i % 7 == 0 else 0.0) for i in range(len(idx))])
        _install(monkeypatch, idx, {"AAA": stock})
        regime.compute("5y", persist=True)
        assert regime.current_state() == "bear"
        out = checklist.checklist("AAA")
        assert "error" not in out
        assert out["market"]["state"] == "bear"
        assert out["verdict"] != "setup"                       # a bear tape never lets a SETUP through
        # the replay passes the regime of the window's own last session
        out_bull = checklist.checklist("AAA", candles=stock, regime_state="bull")
        assert out_bull["market"]["state"] == "bull" and out_bull["market"]["applied"] is False
