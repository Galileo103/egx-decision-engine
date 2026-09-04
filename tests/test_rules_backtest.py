"""App-rules backtester — synthetic candles, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_rb_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import rules_backtest as RB  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


def _bars(rows, vols=None):
    day = datetime(2025, 1, 6)
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c,
                    "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _flat(n, px=100.0, amp=0.4):
    out = []
    for i in range(n):
        c = px + (amp if i % 2 else -amp)
        out.append((px, c + 0.3, c - 0.3, c))
    return out


def _trend(n, start, step):
    out, px = [], start
    for _ in range(n):
        c = px + step
        out.append((px, max(px, c) + 0.3, min(px, c) - 0.3, c))
        px = c
    return out


class TestIndicators:
    def test_sma_atr_rsi_shapes(self) -> None:
        x = RB.Ind(_bars(_trend(60, 100, 1.0)))
        assert x.sma20[19] is not None and x.sma20[18] is None
        assert x.atr[-1] is not None and x.atr[-1] > 0
        assert x.rsi[-1] is not None and x.rsi[-1] > 70   # straight up → overbought


class TestSimulation:
    def test_range_breakout_trade_hits_target_under_fixed_exit(self) -> None:
        # 80 flat bars, one breakout bar with volume, then a strong rally (target 3R hit).
        rows = _flat(80)
        rows.append((100.4, 104.2, 100.3, 104.0))            # close > 20d high (≈100.7), volume 3x
        rows += _trend(30, 104.0, 0.9)
        vols = [100_000] * 80 + [300_000] + [120_000] * 30
        res = RB.simulate(_bars(rows, vols), "range_breakout", "fixed", capital=100_000.0)
        assert res["metrics"]["trades"] >= 1
        t = res["trades"][0]
        assert t["reason"] == "target" and t["r"] > 2.5           # +3R minus fees/slippage
        assert t["entry_date"] > res["from"]                        # entered on the bar AFTER the signal
        assert res["metrics"]["win_rate"] == 100.0
        assert res["metrics"]["final_equity"] > 100_000

    def test_stop_hit_is_a_loss_of_about_minus_one_r(self) -> None:
        rows = _flat(80)
        rows.append((100.4, 104.2, 100.3, 104.0))
        rows += _trend(15, 104.0, -1.2)                           # straight down → stop
        vols = [100_000] * 80 + [300_000] + [120_000] * 15
        res = RB.simulate(_bars(rows, vols), "range_breakout", "fixed", capital=100_000.0)
        t = res["trades"][0]
        assert t["reason"] in ("stop", "stop_gap")
        assert -1.6 < t["r"] < -0.8                                # ≈ -1R, worse with gap/slippage/fees

    def test_guardian_exit_moves_stop_to_breakeven_after_one_r(self) -> None:
        rows = _flat(80)
        rows.append((100.4, 104.2, 100.3, 104.0))
        rows += _trend(6, 104.0, 0.8)                             # +4.8 ≈ > 1R (risk = 2 ATR ≈ 2-3)
        rows += _trend(12, 108.8, -0.9)                           # then fade back toward entry
        vols = [100_000] * 80 + [300_000] + [120_000] * 18
        res = RB.simulate(_bars(rows, vols), "range_breakout", "guardian", capital=100_000.0)
        assert res["metrics"]["trades"] == 1
        t = res["trades"][0]
        assert t["peak_r"] >= 1.0
        assert t["r"] > -0.3                                      # protected: exit near/above breakeven

    def test_time_only_exits_after_hold_bars(self) -> None:
        rows = _flat(80) + [(100.4, 104.2, 100.3, 104.0)] + _flat(40, 104.0, 0.3)
        vols = [100_000] * 80 + [300_000] + [120_000] * 40
        res = RB.simulate(_bars(rows, vols), "range_breakout", "time_only", capital=100_000.0)
        t = res["trades"][0]
        assert t["reason"] == "time" and t["bars"] == RB.DEFAULTS["hold_bars"]

    def test_no_signal_no_trades(self) -> None:
        res = RB.simulate(_bars(_flat(200)), "range_breakout", "fixed")
        assert res["metrics"]["trades"] == 0 and res["metrics"]["sufficient_sample"] is False
        assert res["metrics"]["total_return_pct"] == 0.0


class TestSurfaces:
    def _patch_history(self, monkeypatch, table):
        from app.services import leaders

        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym.upper(), []))
        monkeypatch.setattr(RB, "_index_return", lambda a, b: 4.0)

    def test_run_has_verdict_and_caveat(self, monkeypatch) -> None:
        rows = _flat(80) + [(100.4, 104.2, 100.3, 104.0)] + _trend(30, 104.0, 0.9) + _flat(60, 130.0)
        vols = [100_000] * 80 + [300_000] + [120_000] * 90
        self._patch_history(monkeypatch, {"AAA": _bars(rows, vols)})
        out = RB.run("AAA", "range_breakout", "fixed", "1y")
        assert "error" not in out
        assert "AAA" in out["verdict"] and "EGX30 returned +4.0%" in out["verdict"]
        assert "sketch, not evidence" in out["verdict"]        # < 20 trades
        assert out["rules"]["exit"]["label"] == "Fixed stop & target"

    def test_compare_exits_ranks_all_four(self, monkeypatch) -> None:
        rows = _flat(80) + [(100.4, 104.2, 100.3, 104.0)] + _trend(30, 104.0, 0.9) + _flat(60, 130.0)
        vols = [100_000] * 80 + [300_000] + [120_000] * 90
        self._patch_history(monkeypatch, {"AAA": _bars(rows, vols)})
        out = RB.compare_exits("AAA", "range_breakout", "1y")
        assert [r["exit_rule"] for r in out["rows"]].__len__() == 4
        assert out["best"] in RB.EXIT_RULES and "paid best" in out["summary"]

    def test_stop_sweep_reports_each_stop(self, monkeypatch) -> None:
        rows = _flat(80) + [(100.4, 104.2, 100.3, 104.0)] + _trend(30, 104.0, 0.9) + _flat(60, 130.0)
        vols = [100_000] * 80 + [300_000] + [120_000] * 90
        self._patch_history(monkeypatch, {"AAA": _bars(rows, vols)})
        out = RB.stop_sweep("AAA", "range_breakout", "fixed", "1y", stops=[1.0, 2.0, 3.0])
        assert [r["stop_atr"] for r in out["rows"]] == [1.0, 2.0, 3.0]
        assert out["best_stop_atr"] in (1.0, 2.0, 3.0)

    def test_universe_run_pools_trades(self, monkeypatch) -> None:
        good = _flat(80) + [(100.4, 104.2, 100.3, 104.0)] + _trend(30, 104.0, 0.9) + _flat(60, 130.0)
        vols = [100_000] * 80 + [300_000] + [120_000] * 90
        self._patch_history(monkeypatch, {"AAA": _bars(good, vols), "BBB": _bars(_flat(200))})
        monkeypatch.setattr(RB, "universe_symbols", lambda name: ["AAA", "BBB", "NODATA"])
        out = RB.universe_run("EGX30", "range_breakout", "fixed", "1y")
        assert out["skipped_no_data"] == 1 and len(out["rows"]) == 2
        assert out["pooled"]["symbols_traded"] == 1 and out["pooled"]["trades"] >= 1
        assert "curve-fitting" in out["summary"]

    def test_replay_open_position_under_guardian(self, monkeypatch) -> None:
        from app.services import portfolio

        db.execute("DELETE FROM positions")
        rows = _flat(80) + _trend(30, 100.0, 0.8)               # bought at 100, rallied to 124
        candles = _bars(rows)
        self._patch_history(monkeypatch, {"AAA": candles})
        opened = candles[80]["time"]
        db.execute("INSERT INTO positions (symbol, side, qty, entry, stop, initial_stop, opened_at, note, status) "
                   "VALUES ('AAA','long',100,100.0,96.0,96.0,?, 'x','open')", (opened + "T10:00:00+03:00",))
        out = RB.replay_positions()
        r = out["rows"][0]
        assert r["symbol"] == "AAA" and r["risk_basis"] == "your initial stop"
        assert r["plan_status"] == "target_3R"                   # +12 = 3R on a 4.0 risk
        assert r["plan_exit"] == pytest.approx(112.0)
        assert r["actual_pnl"] > r["plan_pnl"]                   # holding on happened to beat the plan here
        assert "would already have been closed" in out["summary"]
