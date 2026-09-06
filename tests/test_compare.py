"""Compare service — collaborators stubbed, offline."""
from __future__ import annotations

import os
import tempfile

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_cmp_"), "t.db")
# This module sorts first alphabetically, so it is the one that loads settings for the
# whole session: pin the same account/risk values the guardrail tests assume.
os.environ["ACCOUNT_SIZE"] = "100000"
os.environ["RISK_PCT"] = "1.0"
os.environ["FEE_PCT_PER_SIDE"] = "0.25"

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, compare, leaders, portfolio, scorecard, sell_checklist  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("scanner_hits", "signal_outcomes", "proven_edge", "positions", "position_fills"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    scorecard.invalidate_weights()
    yield


def _ck(sym, verdict, score, fails=(), rr=2.4, price=100.0):
    pillars = {k: "pass" for k in checklist.PILLARS}
    for f in fails:
        pillars[f] = "fail"
    return {"symbol": sym, "price": price, "verdict": verdict, "score": score, "headline": f"{verdict} {sym}",
            "pillars": [{"key": k, "label": k, "status": v, "text": "t"} for k, v in pillars.items()],
            "risk_plan": {"entry": price, "stop": price * 0.95, "target": price * (1 + 0.05 * rr), "rr": rr,
                          "stop_pct": 5.0, "shares_at_risk_pct": 100, "liquid": True},
            "levels_position": "mid-range", "as_of": "2026-09-03"}


def _install(monkeypatch, cks, rs=None, sectors=None):
    monkeypatch.setattr(checklist, "checklist", lambda sym, candles=None: cks[sym])
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": [])
    monkeypatch.setattr(leaders, "benchmark_series", lambda force=False, range_="1y": {"dates": [], "series": {}})
    monkeypatch.setattr(leaders, "_symbol_metrics", lambda sym, bench: (rs or {}).get(sym))
    monkeypatch.setattr(portfolio, "_sector_of", lambda sym: (sectors or {}).get(sym))
    monkeypatch.setattr(sell_checklist, "sell_checklist", lambda sym, position=None, candles=None, mark=None: {
        "verdict": "hold", "headline": "h", "against": 0, "pillars": [{"key": "thesis", "status": "pass"}],
        "decision_levels": {"exit_below": 90.0, "reduce_at": 110.0, "trail_stop_to": None, "ladder": []}, "fresh_bearish": []})


class TestCompare:
    def test_needs_two_symbols_and_caps_at_four(self, monkeypatch) -> None:
        assert "error" in compare.compare(["GSSC"])
        cks = {s: _ck(s, "watch", 3) for s in ("A", "B", "C", "D", "E")}
        _install(monkeypatch, cks)
        out = compare.compare(["A", "B", "C", "D", "E", "a"])
        assert out["symbols"] == ["A", "B", "C", "D"] and out["truncated"] == ["E"]

    def test_clean_setup_beats_failing_risk_plan(self, monkeypatch) -> None:
        cks = {"GSSC": _ck("GSSC", "setup", 5, rr=2.4), "COMI": _ck("COMI", "no_setup", 2, fails=("risk",), rr=0.8)}
        _install(monkeypatch, cks, rs={"GSSC": {"excess_1m": 12.0, "excess_3m": 20.0, "pct_from_52w_high": -3.0,
                                              "new_high": False, "median_value_20d": 40e6}})
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES ('2026-09-03', 'range_breakout', 'GSSC', '{}', 'x', 'live')")
        db.execute("INSERT INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, metric_label, verdict, verdict_text, "
                   "extra_json, universe, computed_at) VALUES ('scanner', 'range_breakout', 'x', 'h', 4015, 46.3, 2.01, 'm', 'edge', 't', "
                   "'{\"excess_vs_random\": 1.59}', 'EGX100', 'x')")
        out = compare.compare(["COMI", "GSSC"])
        assert out["winner"] == "GSSC" and out["ranking"] == ["GSSC", "COMI"]
        assert "GSSC first" in out["headline"] and "COMI waits: risk against it" in out["headline"]
        g = next(c for c in out["columns"] if c["symbol"] == "GSSC")
        assert g["signals"][0]["name"] == "range_breakout" and g["signals"][0]["edge"]["verdict"] == "edge"
        assert g["strongest_signal"]["name"] == "range_breakout" and g["evidence_weight"] == 1.0
        # patterns are listed but never summed into the evidence weight
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES ('2026-09-03', 'pattern_bull_flag', 'GSSC', '{}', 'x', 'live')")
        g2 = next(c for c in compare.compare(["COMI", "GSSC"])["columns"] if c["symbol"] == "GSSC")
        assert {s["name"] for s in g2["signals"]} == {"range_breakout", "pattern_bull_flag"} and g2["evidence_weight"] == 1.0
        assert g["fails"] == [] and g["fatal_fail"] is False
        c = next(c for c in out["columns"] if c["symbol"] == "COMI")
        assert c["fatal_fail"] is True and c["rank"] == 2

    def test_same_verdict_ranks_by_reward_to_risk_then_evidence(self, monkeypatch) -> None:
        cks = {"A": _ck("A", "watch", 4, rr=1.5), "B": _ck("B", "watch", 4, rr=3.0)}
        _install(monkeypatch, cks)
        out = compare.compare(["A", "B"])
        assert out["winner"] == "B" and "less room" in out["headline"]

    def test_held_symbol_carries_sell_check_and_heat(self, monkeypatch) -> None:
        cks = {"X": _ck("X", "setup", 5), "Y": _ck("Y", "setup", 5)}
        _install(monkeypatch, cks, sectors={"X": "banks", "Y": "banks"})
        db.execute("INSERT INTO positions (symbol, side, qty, entry, stop, target1, target2, opened_at, note, status) "
                   "VALUES ('X', 'long', 100, 100, 95, 110, 120, '2026-09-01T10:00:00+03:00', 'n', 'open')")
        out = compare.compare(["X", "Y"])
        x = next(c for c in out["columns"] if c["symbol"] == "X")
        y = next(c for c in out["columns"] if c["symbol"] == "Y")
        assert x["held"] is True and x["sell"]["verdict"] == "hold" and x["sell"]["decision_levels"]["exit_below"] == 90.0
        assert y["held"] is False and y["sell"] is None
        assert x["held_in_sector"] == 1 and y["held_in_sector"] == 1        # one bank already held
        assert out["open_heat_pct"] is not None and y["heat_after_pct"] > out["open_heat_pct"]

    def test_symbol_without_data_ranks_last_but_does_not_break(self, monkeypatch) -> None:
        cks = {"A": _ck("A", "watch", 3), "Z": {"symbol": "Z", "error": "not enough daily history (12 bars)"}}
        _install(monkeypatch, cks)
        out = compare.compare(["Z", "A"])
        assert out["winner"] == "A" and out["ranking"] == ["A", "Z"]
        assert "Z: no data" in out["headline"]
