"""Position Guardian — offline tests for the exit-verdict logic and the run path.

`assess_position` is pure (no I/O) so every verdict is pinned with synthetic
candles; `evaluate` is exercised against a temp DB with the mark/history
fetchers monkeypatched — no network.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_guard_"), "test_guard.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import guardian  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean_state():
    for table in ("positions", "snapshots", "guardian_verdicts", "position_fills"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed literals
    yield


# ── synthetic data ───────────────────────────────────────────────────────────

ENTRY_DATE = "2026-08-01"


def _pos(**over) -> dict:
    base = {
        "id": 1, "symbol": "COMI", "qty": 100, "entry": 100.0, "stop": 95.0,
        "target1": 110.0, "target2": 120.0, "opened_at": ENTRY_DATE + "T10:30:00+03:00",
        "note": "squeeze breakout", "plan": None,
    }
    base.update(over)
    return base


def _candles(closes: list[float], spread: float = 1.0, n_pre: int = 20) -> list[dict]:
    """Daily bars with a constant high-low range so ATR14 == spread.

    The first ``n_pre`` bars are dated before ENTRY_DATE (ending 07-31); the
    rest start on 08-02, i.e. strictly after the entry session.
    """
    out = []
    pre_start = datetime.fromisoformat(ENTRY_DATE) - timedelta(days=n_pre)
    for i, c in enumerate(closes):
        if i < n_pre:
            day = pre_start + timedelta(days=i)
        else:
            day = datetime.fromisoformat(ENTRY_DATE) + timedelta(days=1 + i - n_pre)
        out.append({
            "time": day.strftime("%Y-%m-%d"), "open": c, "high": c + spread / 2,
            "low": c - spread / 2, "close": c, "volume": 1000,
        })
    return out


def _split(candles: list[dict]) -> tuple[list[dict], list[dict]]:
    return candles, [c for c in candles if c["time"] > ENTRY_DATE]


def _assess(pos, price, closes, snap=None, entry_score=None, **kw):
    candles, since = _split(_candles(closes, **kw))
    mark = None if price is None else {"price": price, "source": "test", "as_of": "2026-09-01"}
    return guardian.assess_position(pos, mark, candles, since, snap, entry_score,
                                    "test" if entry_score is not None else "unknown")


# ── verdicts ─────────────────────────────────────────────────────────────────

class TestVerdicts:
    def test_hold_when_nothing_applies(self) -> None:
        # 20 bars before entry, 3 after — flat around entry, stop intact.
        r = _assess(_pos(), 101.0, [100.0] * 20 + [100.5, 101.0, 101.0])
        assert r["verdict"] == "HOLD"
        assert r["severity"] == "ok"
        assert r["r_now"] == pytest.approx(0.2)
        assert r["bars_held"] == 3

    def test_exit_stop_is_critical_and_wins_over_everything(self) -> None:
        snap = {"date": "2026-09-01", "score": 20, "signal": "STRONG_SELL"}
        r = _assess(_pos(), 94.0, [100.0] * 20 + [99.0, 96.0, 94.0], snap=snap, entry_score=80)
        assert r["verdict"] == "EXIT_STOP"
        assert r["severity"] == "critical"
        assert "THESIS_BROKEN" in r["all_verdicts"]  # still listed as a reason
        assert r["r_now"] == pytest.approx(-1.2)

    def test_stop_touched_when_low_pierces_but_close_recovers(self) -> None:
        # spread 12 → last low = 97 - 6 = 91 < stop 95, close 97 > stop.
        r = _assess(_pos(), 97.0, [100.0] * 20 + [99.0, 97.0], spread=12.0)
        assert r["verdict"] == "STOP_TOUCHED"
        assert r["severity"] == "warning"

    def test_target_hits(self) -> None:
        r1 = _assess(_pos(), 111.0, [100.0] * 20 + [104.0, 108.0, 111.0])
        assert r1["verdict"] == "TARGET1_HIT"
        r2 = _assess(_pos(), 121.0, [100.0] * 20 + [110.0, 118.0, 121.0])
        assert r2["verdict"] == "TARGET2_HIT"
        assert r2["severity"] == "action"

    def test_tighten_stop_after_one_r(self) -> None:
        # High 107 = mark → chandelier = 107 - 2.5 x ATR14 (ATR includes the
        # gap true-ranges, so it is ~1.39 here, not the 1.0 bar spread).
        r = _assess(_pos(target1=None, target2=None), 107.0, [100.0] * 20 + [103.0, 105.0, 107.0])
        assert r["verdict"] == "TIGHTEN_STOP"
        assert r["atr14"] == pytest.approx(19.5 / 14, abs=1e-3)
        assert r["suggested_stop"] == pytest.approx(round(107.0 - 2.5 * r["atr14"], 2))
        assert 95.0 < r["suggested_stop"] < 107.0
        assert r["peak_r"] == pytest.approx(1.4)

    def test_tighten_stop_floors_at_breakeven(self) -> None:
        # Wide bars (ATR 4): chandelier = 106 - 10 = 96 < entry → suggest breakeven 100.
        r = _assess(_pos(target1=None, target2=None), 105.0,
                    [100.0] * 20 + [104.0, 106.0, 105.0], spread=4.0)
        assert r["verdict"] == "TIGHTEN_STOP"
        assert r["suggested_stop"] == pytest.approx(100.0)

    def test_trail_exit_when_price_gives_back_more_than_atr_mult(self) -> None:
        # Ran to 110 (2R), now 104. ATR14 = (10x1 + 5.5 + 5.5 + 2.5 + 4.5)/14 = 2.0,
        # chandelier = 110 - 5.0 = 105 >= mark 104 → trailing exit.
        r = _assess(_pos(target1=None, target2=None), 104.0,
                    [100.0] * 20 + [105.0, 110.0, 108.0, 104.0])
        assert r["verdict"] == "TRAIL_EXIT"
        assert r["severity"] == "action"

    def test_no_trailing_logic_before_one_r(self) -> None:
        # Peak 0.8R only → no tighten/trail advice even after a pullback.
        r = _assess(_pos(target1=None, target2=None), 102.0,
                    [100.0] * 20 + [103.0, 104.0, 102.0])
        assert r["verdict"] == "HOLD"
        assert r["suggested_stop"] is None

    def test_thesis_broken_on_sell_signal(self) -> None:
        snap = {"date": "2026-09-01", "score": 70, "signal": "SELL"}
        r = _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=snap, entry_score=72)
        assert r["verdict"] == "THESIS_BROKEN"
        assert "SELL" in r["reasons"][0]

    def test_thesis_broken_on_score_drop(self) -> None:
        snap = {"date": "2026-09-01", "score": 55, "signal": "NEUTRAL"}
        r = _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=snap, entry_score=75)
        assert r["verdict"] == "THESIS_BROKEN"
        # A smaller drop is not a broken thesis.
        snap2 = {"date": "2026-09-01", "score": 65, "signal": "NEUTRAL"}
        assert _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=snap2,
                       entry_score=75)["verdict"] == "HOLD"

    def test_time_stop_for_dead_money(self) -> None:
        r = _assess(_pos(), 100.5, [100.0] * 20 + [100.0] * 16)
        assert r["verdict"] == "TIME_STOP"
        assert r["bars_held"] == 16
        # A trade that is working is never a time-stop.
        r2 = _assess(_pos(target1=None, target2=None), 103.0, [100.0] * 20 + [103.0] * 16)
        assert r2["verdict"] != "TIME_STOP"

    def test_no_price_yields_hold_with_explanation(self) -> None:
        r = _assess(_pos(), None, [100.0] * 20)
        assert r["verdict"] == "HOLD"
        assert r["mark"] is None
        assert "No price available" in r["reasons"][0]

    def test_history_error_is_surfaced_not_fatal(self) -> None:
        r = guardian.assess_position(_pos(), {"price": 101.0, "source": "t", "as_of": None},
                                     [], [], None, None, "unknown", history_error="429")
        assert r["verdict"] == "HOLD"
        assert any("history unavailable" in x for x in r["reasons"])


# ── run path: persistence + notification dedupe ───────────────────────────────

class TestEvaluate:
    def _open(self, symbol="COMI", entry=100.0, stop=95.0) -> int:
        return db.execute(
            "INSERT INTO positions (symbol, side, qty, entry, stop, target1, target2, opened_at, "
            "note, status) VALUES (?, 'long', 100, ?, ?, 110, 120, ?, 'test', 'open')",
            (symbol, entry, stop, ENTRY_DATE + "T10:30:00+03:00"),
        )

    def test_empty_portfolio(self) -> None:
        out = guardian.evaluate()
        assert out["verdicts"] == []
        assert out["summary"]["open"] == 0

    def test_persist_and_notify_once_per_day(self, monkeypatch) -> None:
        from app.services import portfolio, history

        pid = self._open()
        monkeypatch.setattr(portfolio, "_mark_prices",
                            lambda syms: {s: {"price": 94.0, "source": "test", "as_of": None}
                                          for s in syms})
        monkeypatch.setattr(history, "get_history",
                            lambda *a, **k: {"symbol": "COMI",
                                             "candles": _candles([100.0] * 20 + [96.0, 94.0])})
        sent: list[str] = []
        from app.services import alerts
        monkeypatch.setattr(alerts, "send_telegram", lambda text: sent.append(text) or True)

        out = guardian.evaluate(persist=True, notify=True)
        assert "error" not in out
        assert out["verdicts"][0]["verdict"] == "EXIT_STOP"
        assert out["summary"]["needs_action"] == 1
        assert out["summary"]["notified"] == 1
        assert len(sent) == 1 and "EXIT_STOP" in sent[0] and "COMI" in sent[0]

        rows = db.query("SELECT * FROM guardian_verdicts WHERE position_id = ?", (pid,))
        assert len(rows) == 1 and rows[0]["verdict"] == "EXIT_STOP" and rows[0]["notified"] == 1

        # Same day, same verdict: no second ping, still one row (REPLACE).
        out2 = guardian.evaluate(persist=True, notify=True)
        assert out2["summary"]["notified"] == 0
        assert len(sent) == 1
        assert len(db.query("SELECT * FROM guardian_verdicts WHERE position_id = ?", (pid,))) == 1

        hist = guardian.history(position_id=pid)
        assert hist and hist[0]["reasons"] and "stop" in hist[0]["reasons"][0].lower()

    def test_hold_is_not_pushed(self, monkeypatch) -> None:
        from app.services import portfolio, history, alerts

        self._open()
        monkeypatch.setattr(portfolio, "_mark_prices",
                            lambda syms: {s: {"price": 101.0, "source": "test", "as_of": None}
                                          for s in syms})
        monkeypatch.setattr(history, "get_history",
                            lambda *a, **k: {"symbol": "COMI",
                                             "candles": _candles([100.0] * 20 + [101.0])})
        monkeypatch.setattr(alerts, "send_telegram", lambda text: pytest.fail("must not ping"))
        out = guardian.evaluate(persist=True, notify=True)
        assert out["verdicts"][0]["verdict"] == "HOLD"
        assert out["summary"]["notified"] == 0

    def test_entry_score_falls_back_to_snapshot(self, monkeypatch) -> None:
        from app.services import portfolio, history

        self._open()
        db.execute(
            "INSERT INTO snapshots (symbol, date, timeframe, price, score, signal, created_at) "
            "VALUES ('COMI', '2026-07-31', '1D', 99.0, 80, 'BUY', 'x')"
        )
        db.execute(
            "INSERT INTO snapshots (symbol, date, timeframe, price, score, signal, created_at) "
            "VALUES ('COMI', '2026-09-01', '1D', 101.0, 60, 'NEUTRAL', 'x')"
        )
        monkeypatch.setattr(portfolio, "_mark_prices",
                            lambda syms: {s: {"price": 101.0, "source": "test", "as_of": None}
                                          for s in syms})
        monkeypatch.setattr(history, "get_history",
                            lambda *a, **k: {"symbol": "COMI",
                                             "candles": _candles([100.0] * 20 + [101.0])})
        out = guardian.evaluate()
        row = out["verdicts"][0]
        assert row["score_at_entry"] == 80 and row["score_at_entry_source"] == "snapshot 2026-07-31"
        assert row["score_now"] == 60
        assert row["verdict"] == "THESIS_BROKEN"


# ── initial_stop / raised stops / stop updates ───────────────────────────────

class TestStopManagement:
    def test_open_rejects_stop_above_entry_unless_raised_stop(self) -> None:
        from app.services import portfolio

        bad = portfolio.open_position("ISPH", 10, 11.65, 12.50, note="winner")
        assert "error" in bad and "raised_stop" in bad["error"]
        ok = portfolio.open_position("ISPH", 10, 11.65, 12.50, note="winner", raised_stop=True)
        assert "error" not in ok
        assert ok["stop"] == 12.50 and ok["initial_stop"] is None
        assert any("R multiples" in w for w in ok.get("risk_warnings", []))

    def test_initial_stop_recorded_and_r_anchored_to_it(self) -> None:
        from app.services import portfolio

        pos = portfolio.open_position("COMI", 100, 100.0, 95.0, note="test")
        assert pos["initial_stop"] == 95.0
        # Raise the stop above entry (act on TIGHTEN_STOP) ...
        upd = portfolio.update_position(pos["id"], stop=104.0)
        assert "error" not in upd and upd["stop"] == 104.0 and upd["initial_stop"] == 95.0
        assert any("risk-free" in w for w in upd.get("risk_warnings", []))
        # ... and R at close still measures against the ORIGINAL 5.00 risk.
        closed = portfolio.close_position(pos["id"], 110.0)
        fees = closed["fees"]
        expected_r = ((110.0 - 100.0) * 100 - fees) / 100 / 5.0
        assert closed["r_multiple"] == pytest.approx(round(expected_r, 2))

    def test_update_position_validation_and_lowered_stop_warning(self) -> None:
        from app.services import portfolio

        pos = portfolio.open_position("COMI", 100, 100.0, 95.0, note="test")
        assert "error" in portfolio.update_position(pos["id"])
        assert "error" in portfolio.update_position(pos["id"], stop=0)
        assert "error" in portfolio.update_position(999999, stop=90.0)
        lowered = portfolio.update_position(pos["id"], stop=90.0, target1=120.0)
        assert lowered["stop"] == 90.0 and lowered["target1"] == 120.0
        assert any("LOWERED" in w for w in lowered.get("risk_warnings", []))
        portfolio.close_position(pos["id"], 100.0)
        assert "error" in portfolio.update_position(pos["id"], stop=91.0)

    def test_guardian_uses_initial_stop_for_r_and_current_stop_for_exit(self) -> None:
        pos = _pos(stop=104.0, initial_stop=95.0, target1=None, target2=None)
        # Mark 103 is below the RAISED stop 104 → EXIT_STOP, and R is +0.6
        # against the initial 5.00 risk (not negative against the raised stop).
        r = _assess(pos, 103.0, [100.0] * 20 + [106.0, 105.0, 103.0])
        assert r["verdict"] == "EXIT_STOP"
        assert r["r_now"] == pytest.approx(0.6)

    def test_guardian_raised_stop_without_initial_gives_no_r(self) -> None:
        pos = _pos(stop=12.5, initial_stop=None, entry=11.65, target1=13.05, target2=13.55)
        r = _assess(pos, 12.95, [11.0] * 20 + [12.5, 12.9, 12.95], spread=0.4)  # low 12.75 > stop
        assert r["r_now"] is None and r["peak_r"] is None
        assert r["verdict"] == "HOLD"


# ── plan defaults: stop / targets / note come from the engine's trade plan ───

def _fake_detail(stop=95.0, t1=110.0, t2=120.0, score=71.0, atr=2.0):
    def detail(symbol, timeframe="1D"):
        return {
            "symbol": symbol,
            "analysis": {"stock_score": score, "signal": "BUY",
                         "price_data": {"current_price": 100.0},
                         "indicators": {"atr": atr}},
            "trade_plan": {"trade_setup": {
                "primary_scenario": "breakout",
                "scenarios": {"breakout": {"entry": 100.0, "stop_loss": stop,
                                           "targets": {"target_1": t1, "target_2": t2}}},
            }},
            "plan_checks": ["Illiquid: thin book."],
            "as_of": "2026-09-02",
        }
    return detail


class TestPlanDefaults:
    def test_defaults_from_plan(self, monkeypatch) -> None:
        from app.services import portfolio, stocks

        monkeypatch.setattr(stocks, "detail", _fake_detail())
        d = portfolio.plan_defaults("comi", 100.0)
        assert d["stop"] == 95.0 and d["target1"] == 110.0 and d["target2"] == 120.0
        assert d["source"] == "trade plan" and d["score"] == 71.0
        assert "Auto-filled" in d["note"] and "R:R 4.0" in d["note"]
        assert d["warnings"] == ["Illiquid: thin book."]

    def test_stop_not_below_entry_falls_back_to_atr(self, monkeypatch) -> None:
        from app.services import portfolio, stocks

        monkeypatch.setattr(stocks, "detail", _fake_detail(stop=101.0, t1=99.0))
        d = portfolio.plan_defaults("COMI", 100.0)
        assert d["stop"] == 96.0 and "TradingView ATR" in d["source"]
        assert d["target1"] is None and d["target2"] == 120.0
        assert any("falling back" in w for w in d["warnings"])

    def test_no_stop_available_is_explained_not_invented(self, monkeypatch) -> None:
        from app.services import portfolio, stocks, history

        monkeypatch.setattr(stocks, "detail", _fake_detail(stop=None, atr=None))
        monkeypatch.setattr(history, "get_history", lambda *a, **k: {"error": "offline"})
        d = portfolio.plan_defaults("COMI", 100.0)
        assert d["stop"] is None
        assert any("enter the stop yourself" in w for w in d["warnings"])

    def test_open_position_autofills_when_stop_omitted(self, monkeypatch) -> None:
        from app.services import portfolio, stocks

        monkeypatch.setattr(stocks, "detail", _fake_detail())
        pos = portfolio.open_position("COMI", 10, 100.0)  # symbol, qty, entry only
        assert "error" not in pos
        assert pos["stop"] == 95.0 and pos["initial_stop"] == 95.0
        assert pos["target1"] == 110.0 and pos["target2"] == 120.0
        assert "Auto-filled" in pos["note"]
        assert pos["plan"]["score"] == 71.0  # guardian's score-at-entry anchor
        assert len(pos["auto_filled"]) == 4
        # A user-supplied value is never overwritten by the plan.
        pos2 = portfolio.open_position("COMI", 10, 100.0, target1=105.0, note="my reason")
        assert pos2["target1"] == 105.0 and pos2["note"] == "my reason" and pos2["stop"] == 95.0

    def test_open_position_without_stop_fails_clearly_when_plan_unavailable(self, monkeypatch) -> None:
        from app.services import portfolio, stocks

        monkeypatch.setattr(stocks, "detail", lambda s, tf="1D": {"error": "TV down"})
        pos = portfolio.open_position("COMI", 10, 100.0)
        assert "error" in pos and "stop is required" in pos["error"]


# ── buying more / selling part of an open position ───────────────────────────

class TestAdjustPosition:
    def _open(self):
        from app.services import portfolio

        pos = portfolio.open_position("COMI", 100, 100.0, 95.0, note="test")
        assert "error" not in pos
        return pos

    def test_buy_more_blends_entry_and_journals(self) -> None:
        from app.services import portfolio

        pos = self._open()
        r = portfolio.adjust_position(pos["id"], 100, 110.0)
        assert "error" not in r
        assert r["qty"] == 200 and r["entry"] == pytest.approx(105.0)
        assert r["initial_stop"] == 95.0 and r["stop"] == 95.0  # untouched
        assert r["fill"]["entry_before"] == 100.0 and r["fill"]["entry_after"] == pytest.approx(105.0)
        fills = portfolio.position_fills(pos["id"])
        assert [f["side"] for f in fills] == ["buy", "buy"]  # add + opening buy

    def test_averaging_down_is_warned(self) -> None:
        from app.services import portfolio

        pos = self._open()
        r = portfolio.adjust_position(pos["id"], 100, 90.0)
        assert r["entry"] == pytest.approx(95.0)
        assert any("Averaging DOWN" in w for w in r.get("risk_warnings", []))

    def test_partial_sell_realizes_pnl_and_keeps_entry(self) -> None:
        from app.services import portfolio
        from app.config import settings

        pos = self._open()
        r = portfolio.adjust_position(pos["id"], -40, 110.0)
        assert "error" not in r
        assert r["qty"] == 60 and r["entry"] == 100.0
        fees = (100.0 * 40 + 110.0 * 40) * settings.fee_pct_per_side / 100.0
        expected = round((110.0 - 100.0) * 40 - fees, 2)
        assert r["fill"]["realized_pnl"] == pytest.approx(expected)
        assert r["fill"]["r_multiple"] == pytest.approx(round((expected / 40) / 5.0, 2))
        perf = portfolio.performance()
        assert perf["realized_pnl_partial_sales"] == pytest.approx(expected)
        assert perf["partial_sales_count"] == 1
        assert perf["realized_pnl"] == pytest.approx(expected)  # nothing closed yet

    def test_selling_everything_closes_the_position(self) -> None:
        from app.services import portfolio

        pos = self._open()
        r = portfolio.adjust_position(pos["id"], -100, 120.0)
        assert r["status"] == "closed" and r["fill"]["closed_position"] is True
        assert r["exit_price"] == 120.0

    def test_validation(self) -> None:
        from app.services import portfolio

        pos = self._open()
        assert "error" in portfolio.adjust_position(pos["id"], 0, 100.0)
        assert "error" in portfolio.adjust_position(pos["id"], 10, 0)
        assert "error" in portfolio.adjust_position(pos["id"], -150, 100.0)
        assert "error" in portfolio.adjust_position(999999, 10, 100.0)
        portfolio.close_position(pos["id"], 100.0)
        assert "error" in portfolio.adjust_position(pos["id"], 10, 100.0)


class TestPlanDefaultsFallback:
    def test_tradingview_outage_falls_back_to_yahoo_atr(self, monkeypatch) -> None:
        from app.services import portfolio, stocks, history

        monkeypatch.setattr(stocks, "detail", lambda s, tf="1D": {
            "symbol": s,
            "analysis": {"error": {"code": "UPSTREAM_ERROR", "message": "empty body outage"}},
            "trade_plan": {"error": "Analysis failed"},
            "plan_checks": [], "as_of": "x",
        })
        # 20 flat bars with a 1.0 range → ATR14 == 1.0, last close 100.
        monkeypatch.setattr(history, "get_history",
                            lambda *a, **k: {"symbol": "EFIH", "candles": _candles([100.0] * 20)})
        d = portfolio.plan_defaults("EFIH", 23.05)
        assert "error" not in d
        assert d["stop"] == pytest.approx(21.05)          # 23.05 − 2 × 1.0
        assert "Yahoo" in d["source"]
        assert d["target1"] is None and d["score"] is None
        assert any("TradingView analysis is unavailable" in w for w in d["warnings"])
        # And open_position uses it when the user gives only symbol/qty/entry.
        pos = portfolio.open_position("EFIH", 543, 23.05)
        assert "error" not in pos and pos["stop"] == pytest.approx(21.05)
        assert any("Yahoo" in a for a in pos["auto_filled"])


class TestDuplicateProtection:
    def test_opening_a_symbol_already_held_warns(self) -> None:
        from app.services import portfolio

        first = portfolio.open_position("COMI", 100, 100.0, 95.0, note="a")
        second = portfolio.open_position("COMI", 50, 101.0, 95.0, note="b")
        assert "error" not in second
        assert any("already hold 100 COMI" in w for w in second.get("risk_warnings", []))

    def test_delete_position_erases_record_and_fills(self) -> None:
        from app.services import portfolio

        pos = portfolio.open_position("COMI", 100, 100.0, 95.0, note="dup")
        r = portfolio.delete_position(pos["id"])
        assert r.get("ok") is True and r["deleted"]["symbol"] == "COMI"
        assert portfolio.position_fills(pos["id"]) == []
        assert "error" in portfolio.delete_position(pos["id"])  # gone

    def test_delete_refuses_when_partial_sales_exist(self) -> None:
        from app.services import portfolio

        pos = portfolio.open_position("COMI", 100, 100.0, 95.0, note="x")
        portfolio.adjust_position(pos["id"], -10, 110.0)
        r = portfolio.delete_position(pos["id"])
        assert "error" in r and "partial sales" in r["error"]


# ── Phase 0 (2026-09-04): invalid targets, missing snapshot, original stop ───

class TestPlanIntegrity:
    def test_target_below_entry_is_never_a_hit(self) -> None:
        # The live MENA case: entry 7.20, stop 6.60, target 1 typed as 6.88.
        # Mark 6.99 is a -2.9% loss — the old code said TARGET1_HIT.
        pos = _pos(entry=7.20, stop=6.60, target1=6.88, target2=7.53)
        r = _assess(pos, 6.99, [7.2] * 20 + [7.1, 7.05, 6.99], spread=0.2)
        assert r["verdict"] == "PLAN_INVALID"
        assert "TARGET1_HIT" not in r["all_verdicts"]
        assert r["severity"] == "warning"
        assert r["target1"] is None and r["target2"] == 7.53
        assert any("6.88" in f and "at/below your entry" in f for f in r["plan_faults"])
        assert any("Fix this record" in s for s in r["reasons"])

    def test_valid_target_still_fires_alongside_invalid_one(self) -> None:
        pos = _pos(entry=100.0, stop=95.0, target1=90.0, target2=110.0)
        r = _assess(pos, 111.0, [100.0] * 20 + [104.0, 108.0, 111.0])
        # Target 2 is real and reached; the bogus target 1 is flagged, not "hit".
        # (TIGHTEN_STOP also applies here — the trade is past +1R — and is fine.)
        assert r["verdict"] == "TARGET2_HIT"
        assert "PLAN_INVALID" in r["all_verdicts"] and "TARGET1_HIT" not in r["all_verdicts"]

    def test_target2_not_above_target1_is_flagged(self) -> None:
        pos = _pos(entry=100.0, stop=95.0, target1=110.0, target2=105.0)
        r = _assess(pos, 101.0, [100.0] * 20 + [101.0])
        assert r["verdict"] == "PLAN_INVALID" and r["target2"] is None and r["target1"] == 110.0

    def test_stop_still_wins_over_plan_invalid(self) -> None:
        pos = _pos(entry=100.0, stop=95.0, target1=90.0)
        r = _assess(pos, 94.0, [100.0] * 20 + [97.0, 94.0])
        assert r["verdict"] == "EXIT_STOP" and "PLAN_INVALID" in r["all_verdicts"]

    def test_missing_snapshot_is_said_out_loud(self) -> None:
        r = _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=None)
        assert r["thesis_check"] == "unavailable"
        assert any("No daily snapshot" in s for s in r["reasons"])
        r2 = _assess(_pos(), 101.0, [100.0] * 20 + [101.0],
                     snap={"date": "2026-09-01", "score": 60, "signal": "BUY"}, entry_score=60)
        assert r2["thesis_check"] == "ok"
        assert not any("No daily snapshot" in s for s in r2["reasons"])

    def test_unknown_entry_score_is_explained(self) -> None:
        snap = {"date": "2026-09-01", "score": 40, "signal": "NEUTRAL"}
        r = _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=snap, entry_score=None)
        assert r["verdict"] == "HOLD"
        assert any("Score at entry is unknown" in s for s in r["reasons"])
        r2 = _assess(_pos(), 101.0, [100.0] * 20 + [101.0], snap=snap, entry_score=70)
        assert r2["verdict"] == "THESIS_BROKEN"
        assert not any("Score at entry is unknown" in s for s in r2["reasons"])

    def test_unknown_initial_risk_is_explained(self) -> None:
        pos = _pos(entry=11.65, stop=12.50, initial_stop=None, target1=13.05, target2=13.55)
        r = _assess(pos, 12.80, [11.6] * 20 + [12.0, 12.5, 12.8], spread=0.3)
        assert r["r_now"] is None
        assert any("Initial risk is unknown" in s for s in r["reasons"])

    def test_open_rejects_manual_target_at_or_below_entry(self) -> None:
        from app.services import portfolio

        bad = portfolio.open_position("MENA", 100, 7.20, 6.60, target1=6.88, target2=7.53, note="x")
        assert "error" in bad and "target1 6.88" in bad["error"]
        bad2 = portfolio.open_position("MENA", 100, 7.20, 6.60, target1=7.60, target2=7.50, note="x")
        assert "error" in bad2 and "target2" in bad2["error"]
        ok = portfolio.open_position("MENA", 100, 7.20, 6.60, target1=7.53, target2=8.25, note="x")
        assert "error" not in ok and ok["target1"] == 7.53

    def test_update_rejects_bad_targets_and_records_original_stop_once(self) -> None:
        from app.services import portfolio

        pos = portfolio.open_position("ISPH", 10, 11.65, 12.50, note="winner", raised_stop=True)
        assert pos["initial_stop"] is None
        assert "error" in portfolio.update_position(pos["id"], target1=11.0)
        assert "error" in portfolio.update_position(pos["id"], target1=13.0, target2=12.5)
        ok_t = portfolio.update_position(pos["id"], target1=13.05, target2=13.55)
        assert "error" not in ok_t and ok_t["target1"] == 13.05 and ok_t["target2"] == 13.55
        # target2 alone must still respect the stored target1
        assert "error" in portfolio.update_position(pos["id"], target2=13.0)
        # original stop: must be below entry, and can be set only once
        assert "error" in portfolio.update_position(pos["id"], initial_stop=11.70)
        ok = portfolio.update_position(pos["id"], initial_stop=11.10)
        assert "error" not in ok and ok["initial_stop"] == 11.10 and ok["stop"] == 12.50
        again = portfolio.update_position(pos["id"], initial_stop=11.00)
        assert "error" in again and "already recorded" in again["error"]
        # and R is now anchored to it
        assert portfolio._risk_per_share(ok) == pytest.approx(0.55)
