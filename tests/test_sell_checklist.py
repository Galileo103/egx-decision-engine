"""Sell checklist + its Guardian integration — synthetic candles, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_sell_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import guardian, leaders, patterns, sell_checklist as SC  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("positions", "snapshots", "guardian_verdicts", "position_fills"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    yield


def _bars(closes, vols=None, start=datetime(2025, 1, 6)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.4,
                    "low": min(o, c) - 0.4, "close": c, "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _seg(a, b, n):
    return [a + (b - a) * i / n for i in range(n)]


def _healthy_uptrend(n=260):
    """Steady rise with shallow pullbacks, volume heavier on up days."""
    closes, px = [], 50.0
    for i in range(n):
        px += 0.25 if i % 6 != 5 else -0.4
        closes.append(px)
    vols = [130_000 if (i and closes[i] > closes[i - 1]) else 80_000 for i in range(n)]
    return _bars(closes, vols)


def _broken_downtrend(n=260):
    """Rise, then a long slide with heavy volume on down days."""
    closes = _seg(50, 90, 150) + _seg(90, 62, 110)
    vols = [90_000] * 150 + [170_000 if (i and closes[i] < closes[i - 1]) else 70_000 for i in range(150, n)]
    return _bars(closes, vols)


def _install(monkeypatch, candles, bench_flat=True, pats=None):
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
    dates = [c["time"] for c in candles]
    if bench_flat:
        series = {d: 100.0 for d in dates}
    else:   # index rising 0.3%/session — a stock must beat that to lead
        series = {d: 100.0 * (1.003 ** i) for i, d in enumerate(dates)}
    monkeypatch.setattr(leaders, "benchmark_series", lambda force=False, range_="1y": {"source": "test", "dates": dates, "series": series})
    if pats is not None:
        monkeypatch.setattr(patterns, "detect", lambda sym, c=None: {"symbol": sym, "patterns": pats, "events": []})


def _pos(**over):
    base = {"id": 1, "symbol": "TST", "qty": 1000, "entry": 80.0, "stop": 74.0, "target1": 95.0, "target2": 105.0,
            "opened_at": "2025-06-02T10:00:00+03:00", "note": "test", "plan": None}
    base.update(over)
    return base


class TestSellChecklist:
    def test_healthy_position_holds_and_cites_levels(self, monkeypatch) -> None:
        c = _healthy_uptrend()
        _install(monkeypatch, c, pats=[])
        px = c[-1]["close"]
        out = SC.sell_checklist("TST", position=_pos(entry=px - 10, stop=px - 14, target1=px + 8, target2=px + 15))
        assert "error" not in out and out["held"] is True
        st = {p["key"]: p["status"] for p in out["pillars"]}
        assert st["thesis"] == "pass" and st["distribution"] == "pass" and st["bearish_events"] == "pass"
        assert out["verdict"] == "hold"
        dl = out["decision_levels"]
        assert dl["exit_below"] == pytest.approx(px - 14) and dl["exit_reason"] == "your stop"
        assert dl["reduce_at"] == pytest.approx(px + 8) and dl["reduce_reason"] == "target 1"
        assert f"{px - 14:.2f}" in out["headline"]            # the verdict cites the exit line
        assert dl["ladder"][0]["step"] == "reduce_at" and dl["ladder"][0]["qty"] == 500

    def test_broken_trend_with_distribution_says_exit(self, monkeypatch) -> None:
        c = _broken_downtrend()
        _install(monkeypatch, c, pats=[])
        px = c[-1]["close"]
        out = SC.sell_checklist("TST", position=_pos(entry=85.0, stop=px - 6, target1=100.0, target2=110.0))
        st = {p["key"]: p["status"] for p in out["pillars"]}
        assert st["thesis"] == "fail" and st["distribution"] == "fail"
        assert st["relative_strength"] == "fail"           # -28% slide vs a flat index
        assert out["verdict"] == "exit" and "Exit:" in out["headline"]
        assert "50-day" in next(p for p in out["pillars"] if p["key"] == "thesis")["text"]

    def test_target_hit_builds_the_ladder(self, monkeypatch) -> None:
        c = _healthy_uptrend()
        _install(monkeypatch, c, pats=[])
        px = c[-1]["close"]
        out = SC.sell_checklist("TST", position=_pos(entry=px - 20, stop=px - 25, target1=px - 1, target2=px + 10))
        assert out["verdict"] == "reduce"
        steps = [s["step"] for s in out["decision_levels"]["ladder"]]
        assert steps == ["reduce_now", "stop_to", "final"]
        assert out["decision_levels"]["ladder"][0]["qty"] == 500
        assert out["decision_levels"]["ladder"][1]["level"] >= px - 20   # never below breakeven
        assert out["decision_levels"]["reduce_at"] == pytest.approx(px + 10)   # next partial = target 2
        assert "take 50% here" in out["headline"]

    def test_fresh_bearish_event_is_reported_with_its_level(self, monkeypatch) -> None:
        c = _healthy_uptrend()
        px = c[-1]["close"]
        bear = {"pattern": "bull_trap", "label": "Bull Trap", "direction": "bearish", "status": "confirmed",
                "category": "price_action", "quality": 70, "neckline": round(px - 1.0, 2), "target": round(px - 6.0, 2),
                "break_date": c[-1]["time"], "event_headline": True, "timeframe": "1D"}
        _install(monkeypatch, c, pats=[bear])
        out = SC.sell_checklist("TST", position=_pos(entry=px - 10, stop=px - 3, target1=px + 8, target2=px + 15))
        st = {p["key"]: p["status"] for p in out["pillars"]}
        assert st["bearish_events"] == "fail"
        assert out["fresh_bearish"] and out["fresh_bearish"][0]["pattern"] == "bull_trap"
        assert out["fresh_bearish"][0]["sessions_ago"] == 0
        assert out["verdict"] == "reduce"     # one pillar against, stop intact

    def test_invalid_targets_are_ignored_like_the_guardian(self, monkeypatch) -> None:
        c = _healthy_uptrend()
        _install(monkeypatch, c, pats=[])
        px = c[-1]["close"]
        out = SC.sell_checklist("TST", position=_pos(entry=px, stop=px - 5, target1=px - 3, target2=px + 9))
        assert out["position"]["target1"] is None and out["position"]["target2"] == px + 9
        assert out["decision_levels"]["reduce_at"] == pytest.approx(px + 9)

    def test_not_held_still_answers(self, monkeypatch) -> None:
        c = _healthy_uptrend()
        _install(monkeypatch, c, pats=[])
        out = SC.sell_checklist("TST", position=None)
        assert out["held"] is False and out["position"] is None
        assert out["decision_levels"]["exit_below"] is not None       # levels-based stop
        assert "ATR" in out["decision_levels"]["exit_reason"] or "support" in out["decision_levels"]["exit_reason"]
        assert out["pillars"][-1]["status"] == "warn" and "Not held" in out["pillars"][-1]["text"]

    def test_thin_history_is_an_error_not_a_crash(self, monkeypatch) -> None:
        _install(monkeypatch, _healthy_uptrend(60), pats=[])
        out = SC.sell_checklist("TST")
        assert "error" in out and SC.compact(out) is None


class TestGuardianIntegration:
    def _row(self, **over):
        base = {"symbol": "TST", "mark": 100.0, "stop": 92.0, "entry": 90.0, "suggested_stop": None,
                "all_verdicts": [], "reasons": ["Stop intact, no target reached, thesis unchanged — nothing to do."],
                "verdict": "HOLD", "severity": "ok"}
        base.update(over)
        return base

    def test_fresh_bearish_event_becomes_a_warning_with_level(self) -> None:
        sc = {"verdict": "reduce", "headline": "h", "against": 1, "pillars": {},
              "decision_levels": {"exit_below": 92.0, "reduce_at": 110.0, "trail_stop_to": None, "ladder": []},
              "fresh_bearish": [{"pattern": "bull_trap", "label": "Bull Trap", "neckline": 99.0, "target": 90.0,
                                 "sessions_ago": 1}]}
        row = guardian.apply_sell_checklist(self._row(), sc)
        assert row["verdict"] == "BEARISH_EVENT" and row["severity"] == "warning"
        assert any("Bull Trap at 99.00" in r and "target 90.00" in r for r in row["reasons"])
        assert any("below your stop" in r for r in row["reasons"])
        assert not any(r.startswith("Stop intact") for r in row["reasons"])
        assert row["exit_below"] == 92.0 and row["reduce_at"] == 110.0

    def test_structure_stop_raises_tighten_stop_with_suggested_level(self) -> None:
        sc = {"verdict": "hold", "headline": "h", "against": 0, "pillars": {},
              "decision_levels": {"exit_below": 92.0, "reduce_at": 110.0, "trail_stop_to": 96.5,
                                  "trail_reason": "just under support 97.20 tested 3x", "ladder": []},
              "fresh_bearish": []}
        row = guardian.apply_sell_checklist(self._row(), sc)
        assert row["verdict"] == "TIGHTEN_STOP" and row["suggested_stop"] == 96.5
        assert any("tested 3x" in r for r in row["reasons"])

    def test_hard_exit_is_never_diluted(self) -> None:
        sc = {"verdict": "exit", "headline": "h", "against": 3, "pillars": {},
              "decision_levels": {"exit_below": 92.0, "reduce_at": None, "trail_stop_to": 96.5, "ladder": []},
              "fresh_bearish": [{"pattern": "upthrust", "label": "Upthrust", "neckline": 99.0, "target": 85.0, "sessions_ago": 0}]}
        row = guardian.apply_sell_checklist(self._row(mark=91.0, all_verdicts=["EXIT_STOP"], verdict="EXIT_STOP",
                                                      severity="critical", reasons=["out"]), sc)
        assert row["verdict"] == "EXIT_STOP" and "BEARISH_EVENT" not in row["all_verdicts"]
        assert row["suggested_stop"] is None

    def test_ladder_is_spelled_out_on_target_hit(self) -> None:
        sc = {"verdict": "reduce", "headline": "h", "against": 0, "pillars": {},
              "decision_levels": {"exit_below": 92.0, "reduce_at": 120.0, "trail_stop_to": None,
                                  "ladder": [{"step": "reduce_now", "pct": 50, "qty": 500, "at": 110.5, "why": "target 1 (110.00) reached"},
                                             {"step": "stop_to", "level": 90.0, "why": "breakeven"},
                                             {"step": "final", "at": 120.0, "why": "target 2"}]},
              "fresh_bearish": []}
        row = guardian.apply_sell_checklist(self._row(mark=110.5, all_verdicts=["TARGET1_HIT"], verdict="TARGET1_HIT",
                                                      severity="action", reasons=["t1"]), sc)
        assert row["verdict"] == "TARGET1_HIT"
        assert any("sell 50% (500 shares) at market ~110.50" in r and "move the stop to 90.00" in r for r in row["reasons"])
        text = guardian._telegram_text({**row, "position_id": 1})
        assert "Levels: exit below 92.00 · reduce at 120.00" in text

    def test_checklist_exit_becomes_a_guardian_warning(self) -> None:
        sc = {"verdict": "exit", "headline": "Exit: 3 of 6 pillars say leave — thesis, weekly, relative strength. The trade ends below 2.93.",
              "against": 3, "pillars": {}, "decision_levels": {"exit_below": 2.93, "reduce_at": 3.1, "trail_stop_to": None, "ladder": []},
              "fresh_bearish": []}
        row = guardian.apply_sell_checklist(self._row(mark=3.0, stop=2.93, entry=3.015), sc)
        assert row["verdict"] == "CHECKLIST_EXIT" and row["severity"] == "warning"
        assert any(r.startswith("Sell checklist says EXIT: 3 of 6") for r in row["reasons"])
        # a "reduce" checklist does not add a verdict on its own
        sc["verdict"] = "reduce"
        row2 = guardian.apply_sell_checklist(self._row(mark=3.0, stop=2.93, entry=3.015), sc)
        assert row2["verdict"] == "HOLD"

    def test_missing_checklist_keeps_row_intact(self) -> None:
        row = guardian.apply_sell_checklist(self._row(), None)
        assert row["verdict"] == "HOLD" and row["sell_checklist"] is None and row["exit_below"] == 92.0

    def test_evaluate_attaches_the_checklist(self, monkeypatch) -> None:
        from app.services import history, portfolio

        c = _healthy_uptrend()
        px = c[-1]["close"]
        db.execute("INSERT INTO positions (symbol, side, qty, entry, stop, target1, target2, opened_at, note, status, initial_stop) "
                   "VALUES ('TST', 'long', 1000, ?, ?, ?, ?, '2025-06-02T10:00:00+03:00', 'test', 'open', ?)",
                   (px - 10, px - 14, px + 8, px + 15, px - 14))
        monkeypatch.setattr(portfolio, "_mark_prices", lambda syms: {s: {"price": px, "source": "test", "as_of": None} for s in syms})
        monkeypatch.setattr(history, "get_history", lambda *a, **k: {"symbol": "TST", "candles": c})
        _install(monkeypatch, c, pats=[])
        out = guardian.evaluate()
        row = out["verdicts"][0]
        assert row["sell_checklist"] and row["sell_checklist"]["verdict"] == "hold"
        assert row["exit_below"] == pytest.approx(px - 14) and row["reduce_at"] == pytest.approx(px + 8)
        assert "sell checklist" in out["basis"]
