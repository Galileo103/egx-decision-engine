"""Task 3 — minimum reward-to-risk gate at open / update, Guardian near-entry targets."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_rr_"), "t.db")
os.environ.setdefault("ACCOUNT_SIZE", "100000")
os.environ.setdefault("RISK_PCT", "1.0")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import guardian, leaders, portfolio  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for table in ("positions", "position_fills", "guardian_verdicts", "snapshots"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    # a fully specified position never consults the trade plan; pin the ATR the gate uses
    monkeypatch.setattr(portfolio, "atr14", lambda sym: 1.0)
    yield


def _bars(closes, start=datetime(2026, 6, 1), rng=0.5):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + rng,
                    "low": min(o, c) - rng, "close": c, "volume": 100_000})
        day += timedelta(days=1)
    return out


class TestPlanQuality:
    def test_pure_math(self) -> None:
        # entry 100, stop 96 (risk 4), T1 106 = 1.5R, ATR 1.0 -> 6 ATR away: passes
        q = portfolio.plan_quality(100, 96, 106, 110, atr=1.0)
        assert q["ok"] and q["checked"] and q["rr_t1"] == 1.5 and q["rr_t2"] == 2.5 and q["t1_atr"] == 6.0
        # T1 at 1.2R fails the R:R test only
        q = portfolio.plan_quality(100, 96, 104.8, None, atr=1.0)
        assert not q["ok"] and len(q["faults"]) == 1 and "reward-to-risk" in q["faults"][0]
        # T1 0.3% above entry against a 4.4% stop (the CLHO case): both tests fail
        q = portfolio.plan_quality(17.47, 16.70, 17.53, 18.11, atr=0.45)
        assert len(q["faults"]) == 2 and q["rr_t1"] == pytest.approx(0.08, abs=0.01)
        # no target -> nothing to check
        q = portfolio.plan_quality(100, 96, None, None, atr=1.0)
        assert q["ok"] and not q["checked"]
        # unknown risk (raised stop) -> the R:R test is skipped, the ATR test still runs
        q = portfolio.plan_quality(100, None, 100.4, None, atr=1.0)
        assert q["rr_t1"] is None and len(q["faults"]) == 1 and "ATR" in q["faults"][0]
        # unknown ATR -> the ATR test is skipped
        q = portfolio.plan_quality(100, 96, 100.4, None, atr=None)
        assert q["t1_atr"] is None and len(q["faults"]) == 1 and "reward-to-risk" in q["faults"][0]
        # thresholds are configurable
        q = portfolio.plan_quality(100, 96, 104.8, None, atr=1.0, min_rr=1.0)
        assert q["ok"]
        # target 2 alone is judged when there is no target 1
        q = portfolio.plan_quality(100, 96, None, 101, atr=1.0)
        assert not q["ok"] and "target 2" in q["faults"][0]


class TestOpenGate:
    def test_low_rr_target_is_blocked_then_overridable(self) -> None:
        res = portfolio.open_position("CLHO", 100, 17.47, 16.70, target1=17.53, target2=18.11, note="test")
        assert "error" in res and res["error"].startswith("BLOCKED") and res["requires_override"] is True
        assert res["plan_quality"]["rr_t1"] == pytest.approx(0.08, abs=0.01)
        assert db.query("SELECT COUNT(*) AS n FROM positions")[0]["n"] == 0
        ok = portfolio.open_position("CLHO", 100, 17.47, 16.70, target1=17.53, target2=18.11, note="test",
                                     allow_override=True)
        assert "error" not in ok and ok["target1"] == 17.53
        assert any("OVERRIDDEN plan-quality" in w for w in ok["risk_warnings"])
        assert ok["plan_quality"]["ok"] is False

    def test_good_plan_passes_and_reports_quality(self) -> None:
        ok = portfolio.open_position("COMI", 100, 100.0, 96.0, target1=108.0, target2=112.0, note="setup")
        assert "error" not in ok and ok["plan_quality"]["ok"] and ok["plan_quality"]["rr_t1"] == 2.0
        assert not any("plan-quality" in w for w in ok.get("risk_warnings", []))

    def test_no_target_is_not_gated(self) -> None:
        ok = portfolio.open_position("COMI", 100, 100.0, 96.0, note="no targets yet")
        assert "error" not in ok and ok["plan_quality"]["checked"] is False

    def test_update_gate_blocks_new_noise_target(self) -> None:
        ok = portfolio.open_position("COMI", 100, 100.0, 96.0, target1=108.0, note="setup")
        pid = ok["id"]
        res = portfolio.update_position(pid, target1=100.5)
        assert "error" in res and res["error"].startswith("BLOCKED") and res["requires_override"] is True
        assert db.query("SELECT target1 FROM positions WHERE id = ?", (pid,))[0]["target1"] == 108.0
        res = portfolio.update_position(pid, target1=100.5, allow_override=True)
        assert "error" not in res and res["target1"] == 100.5
        assert any("OVERRIDDEN plan-quality" in w for w in res["risk_warnings"])
        # the risk anchor is the INITIAL stop even after the current stop was raised
        portfolio.update_position(pid, stop=99.0)
        res = portfolio.update_position(pid, target1=106.0)      # 1.5R vs initial risk 4.0
        assert "error" not in res and res["plan_quality"]["rr_t1"] == 1.5
        # a stop-only update never touches the gate
        res = portfolio.update_position(pid, stop=99.5)
        assert "error" not in res and "plan_quality" not in res

    def test_size_position_reports_rr(self) -> None:
        r = portfolio.size_position(100_000, 1.0, 100.0, 96.0, "COMI", target1=100.4)
        assert r["plan_quality"]["ok"] is False and "PLAN WARNING" in r["risk_reward_note"]
        r = portfolio.size_position(100_000, 1.0, 100.0, 96.0, "COMI", target1=108.0)
        assert r["plan_quality"]["ok"] is True and "Reward-to-risk to target 1 is 2.00R" in r["risk_reward_note"]
        r = portfolio.size_position(100_000, 1.0, 100.0, 96.0, "COMI")
        assert r["plan_quality"] is None


class TestGuardianNearEntryTarget:
    def test_target_inside_one_atr_is_plan_invalid_not_hit(self, monkeypatch) -> None:
        # ATR ~1.0 (range 0.5 each side); entry 100, T1 100.4 -> inside one ATR
        candles = _bars([100.0] * 40)
        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": candles)
        ok = portfolio.open_position("COMI", 100, 100.0, 96.0, target1=100.4, target2=108.0, note="x",
                                     allow_override=True)
        pid = ok["id"]
        pos = db.query("SELECT * FROM positions WHERE id = ?", (pid,))[0]
        since = [c for c in candles if c["time"] > str(pos["opened_at"])[:10]]
        row = guardian.assess_position(pos, {"price": 100.6, "source": "test", "as_of": "x"}, candles, since,
                                       None, None, "unknown")
        assert "PLAN_INVALID" in row["all_verdicts"]
        assert "TARGET1_HIT" not in row["all_verdicts"]
        assert any("inside one day's normal range" in r for r in row["reasons"])
        # the far target is still checked normally
        row2 = guardian.assess_position(pos, {"price": 108.5, "source": "test", "as_of": "x"}, candles, since,
                                        None, None, "unknown")
        assert "TARGET2_HIT" in row2["all_verdicts"] and "TARGET1_HIT" not in row2["all_verdicts"]
