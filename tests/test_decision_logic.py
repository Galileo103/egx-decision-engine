"""Offline tests for the decision logic — the parts that can actually be wrong.

The smoke suite covers plumbing (routes answer, registry is non-empty). This
covers the arithmetic and rules a wrong answer would cost real money on:
the trading calendar, alert evaluators and their dedupe, position/fee/R math,
the risk guardrails, and candidate ranking. Nothing here touches the network.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta

# Must happen before any `app.*` import.
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="egx_logic_"), "test_logic.db"
)
os.environ["ACCOUNT_SIZE"] = "100000"
os.environ["RISK_PCT"] = "1.0"
os.environ["FEE_PCT_PER_SIDE"] = "0.25"

import pytest  # noqa: E402

from app import calendar_egx, db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Each test starts from empty mutable tables."""
    for table in ("positions", "snapshots", "alert_rules", "alerts_fired", "scanner_hits"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed literals
    yield


# ── trading calendar ─────────────────────────────────────────────────────────

class TestCalendar:
    def test_weekend_is_not_a_trading_day(self) -> None:
        assert not calendar_egx.is_trading_day(date(2026, 8, 28))  # Friday
        assert not calendar_egx.is_trading_day(date(2026, 8, 29))  # Saturday

    def test_sunday_through_thursday_trade(self) -> None:
        for d in range(30, 32):  # Sun 30, Mon 31 Aug 2026
            assert calendar_egx.is_trading_day(date(2026, 8, d))

    def test_holiday_is_not_a_trading_day(self) -> None:
        assert not calendar_egx.is_trading_day(date(2026, 5, 27))  # Eid al-Adha
        assert not calendar_egx.is_trading_day(date(2026, 1, 25))  # Revolution Day

    def test_last_trading_day_skips_weekend_and_holiday(self) -> None:
        # Saturday 29 Aug -> back to Thursday 27 Aug.
        assert calendar_egx.last_trading_day(date(2026, 8, 29)) == date(2026, 8, 27)
        # Eid runs Wed 27 - Sat 30 May; Sunday 31 May looks back to Tue 26.
        assert calendar_egx.last_trading_day(date(2026, 5, 30)) == date(2026, 5, 26)

    def test_session_boundaries(self) -> None:
        cairo = calendar_egx.CAIRO
        trading_day = date(2026, 8, 31)  # Monday
        assert not calendar_egx.is_market_open(
            datetime.combine(trading_day, calendar_egx.SESSION_OPEN, tzinfo=cairo)
            - timedelta(minutes=1)
        )
        assert calendar_egx.is_market_open(
            datetime.combine(trading_day, calendar_egx.SESSION_OPEN, tzinfo=cairo)
        )
        # The close is exclusive.
        assert not calendar_egx.is_market_open(
            datetime.combine(trading_day, calendar_egx.SESSION_CLOSE, tzinfo=cairo)
        )


# ── position sizing, fees, R-multiples ───────────────────────────────────────

class TestPositionMath:
    def test_fixed_fractional_size(self) -> None:
        from app.services import portfolio

        r = portfolio.size_position(100_000, 1.0, 100.0, 95.0)
        assert r["shares"] == 200            # 1000 EGP risk / 5 per share
        assert r["risk_amount"] == 1000.0

    def test_size_rejects_stop_at_or_above_entry(self) -> None:
        from app.services import portfolio

        assert "error" in portfolio.size_position(100_000, 1.0, 100.0, 100.0)
        assert "error" in portfolio.size_position(100_000, 1.0, 100.0, 105.0)

    def test_size_capped_by_capital(self) -> None:
        from app.services import portfolio

        # A 0.1% stop distance would demand a position far above the account.
        r = portfolio.size_position(10_000, 1.0, 100.0, 99.9)
        assert r["shares"] * 100.0 <= 10_000
        assert "capped by available capital" in r["risk_reward_note"]

    def test_round_trip_fees_both_legs(self) -> None:
        from app.services import portfolio

        # 0.25%/side on 10,000 in + 11,000 out = 25 + 27.5
        assert portfolio._round_trip_fees(10.0, 11.0, 1000) == 52.5

    def test_close_position_is_net_of_fees(self) -> None:
        from app.services import portfolio

        opened = portfolio.open_position("COMI", 100, 50.0, 45.0, note="unit test")
        assert "error" not in opened
        closed = portfolio.close_position(int(opened["id"]), 55.0)
        assert closed["pnl_gross"] == 500.0
        assert closed["fees"] == pytest.approx(26.25)     # 0.25% of 5000 + 5500
        assert closed["pnl"] == pytest.approx(473.75)
        # Net R: 473.75 / 100 shares / 5.0 risk-per-share
        assert closed["r_multiple"] == pytest.approx(0.95, abs=0.01)

    def test_closing_twice_is_refused(self) -> None:
        from app.services import portfolio

        opened = portfolio.open_position("COMI", 10, 20.0, 18.0, note="unit test")
        pid = int(opened["id"])
        assert "error" not in portfolio.close_position(pid, 22.0)
        assert "error" in portfolio.close_position(pid, 22.0)


# ── risk guardrails ──────────────────────────────────────────────────────────

class TestRiskGuardrails:
    def test_note_is_required(self) -> None:
        from app.services import portfolio

        r = portfolio.open_position("COMI", 10, 50.0, 48.0, note="   ")
        assert "error" in r and "note is required" in r["error"]

    def test_open_heat_cap_blocks_then_allows_override(self) -> None:
        from app.services import portfolio

        # 5% of a 100k account in one trade is fine on its own.
        first = portfolio.open_position("COMI", 500, 50.0, 40.0, note="setup A")
        assert "error" not in first

        # A second 5% trade would take heat to 10% > the 6% cap.
        blocked = portfolio.open_position("HRHO", 500, 50.0, 40.0, note="setup B")
        assert blocked.get("requires_override") is True
        assert "BLOCKED" in blocked["error"]

        allowed = portfolio.open_position(
            "HRHO", 500, 50.0, 40.0, note="setup B", allow_override=True
        )
        assert "error" not in allowed
        assert any("OVERRIDDEN" in w for w in allowed["risk_warnings"])

    def test_large_single_trade_risk_warns(self) -> None:
        from app.services import portfolio

        # 3% of the account in one trade: allowed, but must warn.
        r = portfolio.open_position("COMI", 300, 50.0, 40.0, note="setup")
        assert "error" not in r
        assert any("risks" in w for w in r.get("risk_warnings", []))

    def test_performance_reports_open_heat_and_discipline(self) -> None:
        from app.services import portfolio

        opened = portfolio.open_position("COMI", 100, 50.0, 45.0, note="setup")
        portfolio.close_position(int(opened["id"]), 60.0, plan_followed=True)
        other = portfolio.open_position("SWDY", 100, 20.0, 18.0, note="setup")
        portfolio.close_position(int(other["id"]), 19.0, plan_followed=False)

        perf = portfolio.performance()
        assert perf["plan_followed_count"] == 1
        assert perf["plan_deviated_count"] == 1
        assert perf["avg_r_plan_followed"] > 0
        assert perf["avg_r_plan_deviated"] < 0
        assert perf["fees_paid"] > 0
        assert perf["realized_pnl"] < perf["realized_pnl_gross"]


# ── alert evaluators ─────────────────────────────────────────────────────────

def _seed_snapshot(symbol: str, day: str, **cols) -> None:
    fields = {"price": 10.0, "bbw": 0.10, "score": 50.0, "signal": "NEUTRAL"}
    fields.update(cols)
    db.execute(
        "INSERT OR REPLACE INTO snapshots (symbol, date, timeframe, price, bbw, score, signal, created_at) "
        "VALUES (?, ?, '1D', ?, ?, ?, ?, ?)",
        (symbol, day, fields["price"], fields["bbw"], fields["score"],
         fields["signal"], f"{day}T15:00:00+03:00"),
    )


class TestAlertEvaluators:
    def test_price_above_fires_only_at_or_above_level(self, monkeypatch) -> None:
        from app.services import alerts

        monkeypatch.setattr(alerts, "_live_quote",
                            lambda s: {"price": 55.0, "previous_close": 50.0, "source": "test"})
        rule = {"rule_type": "price_above"}
        assert alerts._eval_price_threshold(rule, {"symbol": "COMI", "level": 54.0})
        assert not alerts._eval_price_threshold(rule, {"symbol": "COMI", "level": 56.0})

    def test_entry_hit_requires_a_real_cross(self, monkeypatch) -> None:
        from app.services import alerts

        # Crossed up through 52 since the previous close: fires.
        monkeypatch.setattr(alerts, "_live_quote",
                            lambda s: {"price": 55.0, "previous_close": 50.0, "source": "test"})
        assert alerts._eval_entry_hit({}, {"symbol": "COMI", "entry": 52.0})

        # Already above entry before AND after — a state, not an event.
        monkeypatch.setattr(alerts, "_live_quote",
                            lambda s: {"price": 55.0, "previous_close": 54.0, "source": "test"})
        assert not alerts._eval_entry_hit({}, {"symbol": "COMI", "entry": 52.0})

    def test_entry_hit_never_fires_without_a_reference_close(self, monkeypatch) -> None:
        """The snapshot fallback has no previous close; firing on price >= entry
        would repeat every dedupe window forever."""
        from app.services import alerts

        monkeypatch.setattr(alerts, "_live_quote",
                            lambda s: {"price": 99.0, "previous_close": None, "source": "snapshot 2026-08-27"})
        assert not alerts._eval_entry_hit({}, {"symbol": "COMI", "entry": 52.0})

    def test_squeeze_uses_latest_snapshot_date(self) -> None:
        from app.services import alerts

        _seed_snapshot("COMI", "2026-08-26", bbw=0.01)   # old: tight
        _seed_snapshot("COMI", "2026-08-27", bbw=0.09)   # latest: loose
        hits = alerts._eval_squeeze({}, {"universe": "ALL", "bbw_max": 0.04})
        assert not hits, "must read only the most recent snapshot date"

        _seed_snapshot("SWDY", "2026-08-27", bbw=0.02)
        hits = alerts._eval_squeeze({}, {"universe": "ALL", "bbw_max": 0.04})
        assert [s for s, _ in hits] == ["SWDY"]

    def test_score_min_threshold(self) -> None:
        from app.services import alerts

        _seed_snapshot("COMI", "2026-08-27", score=81.0)
        _seed_snapshot("SWDY", "2026-08-27", score=42.0)
        hits = alerts._eval_score_min({}, {"universe": "ALL", "threshold": 70.0})
        assert [s for s, _ in hits] == ["COMI"]

    def test_signal_change_is_edge_triggered(self) -> None:
        from app.services import alerts

        _seed_snapshot("COMI", "2026-08-26", signal="NEUTRAL")
        _seed_snapshot("COMI", "2026-08-27", signal="BUY")
        assert alerts._eval_signal_change({}, {"symbol": "COMI"})

        _seed_snapshot("SWDY", "2026-08-26", signal="BUY")
        _seed_snapshot("SWDY", "2026-08-27", signal="BUY")
        assert not alerts._eval_signal_change({}, {"symbol": "SWDY"})

    def test_dedupe_window_suppresses_a_refire(self) -> None:
        from app.services import alerts

        rule_id = db.execute(
            "INSERT INTO alert_rules (name, rule_type, params_json, enabled, created_at) "
            "VALUES ('t', 'price_above', '{}', 1, ?)",
            (alerts._now_iso(),),
        )
        assert not alerts._recently_fired(rule_id, "COMI")
        db.execute(
            "INSERT INTO alerts_fired (rule_id, symbol, message, fired_at, delivered) "
            "VALUES (?, 'COMI', 'm', ?, 0)",
            (rule_id, alerts._now_iso()),
        )
        assert alerts._recently_fired(rule_id, "COMI")
        assert not alerts._recently_fired(rule_id, "SWDY")

    def test_rule_crud_reports_missing_rows_honestly(self) -> None:
        from app.services import alerts

        created = alerts.create_rule("t", "price_above", {"symbol": "COMI", "level": 10})
        rid = int(created["id"])
        assert alerts.toggle_rule(rid, False)["ok"] is True
        assert alerts.delete_rule(rid)["ok"] is True
        # Second delete must NOT claim success.
        assert alerts.delete_rule(rid)["ok"] is False
        assert alerts.toggle_rule(rid, True)["ok"] is False


# ── candidate ranking ────────────────────────────────────────────────────────

class TestCandidateRanking:
    def test_correlated_scanners_count_once(self) -> None:
        from app.services.screeners import _family_count

        # volume_breakout and momentum both read the same daily bar.
        assert _family_count(["volume_breakout", "momentum"]) == 1
        assert _family_count(["volume_breakout", "squeeze"]) == 2
        assert _family_count(["squeeze", "volume_breakout", "momentum", "smart_money"]) == 3

    def test_unknown_scanner_is_its_own_family(self) -> None:
        from app.services.screeners import _family_count

        assert _family_count(["squeeze", "something_new"]) == 2


# ── scheduler job accounting ─────────────────────────────────────────────────

class TestJobAccounting:
    def test_nested_stage_failure_is_a_failure(self) -> None:
        from app.scheduler import _result_failed

        assert _result_failed({"error": "boom"})
        assert _result_failed({"snapshot": {"error": "upstream down"}, "candidates": {"count": 3}})
        assert not _result_failed({"snapshot": {"saved": 100}, "candidates": {"count": 3}})
        assert not _result_failed({"skipped": "non-trading day (weekend/holiday)"})


# ── database hygiene ─────────────────────────────────────────────────────────

class TestDatabase:
    def test_executemany_is_atomic(self) -> None:
        rows = [("AAA", "2026-08-27", "1D", 1.0), ("BBB", "2026-08-27", "1D", 2.0)]
        n = db.executemany(
            "INSERT OR REPLACE INTO snapshots (symbol, date, timeframe, price) VALUES (?, ?, ?, ?)",
            rows,
        )
        assert n == 2
        assert db.query("SELECT COUNT(*) AS n FROM snapshots")[0]["n"] == 2

    def test_prune_refuses_unknown_tables(self) -> None:
        with pytest.raises(ValueError):
            db.prune("positions", "opened_at", 30)      # not an append-only log
        with pytest.raises(ValueError):
            db.prune("job_runs", "finished_at", 30)     # wrong column

    def test_prune_removes_only_old_rows(self) -> None:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        db.execute(
            "INSERT INTO job_runs (job, started_at, finished_at, ok, detail) VALUES ('old', ?, ?, 1, '')",
            ((now - timedelta(days=200)).isoformat(), (now - timedelta(days=200)).isoformat()),
        )
        db.execute(
            "INSERT INTO job_runs (job, started_at, finished_at, ok, detail) VALUES ('new', ?, ?, 1, '')",
            (now.isoformat(), now.isoformat()),
        )
        assert db.prune("job_runs", "started_at", 90) == 1
        remaining = [r["job"] for r in db.query("SELECT job FROM job_runs")]
        assert remaining == ["new"]

    def test_scanner_hits_are_deduplicated_per_day(self) -> None:
        for _ in range(3):
            db.execute(
                "INSERT OR REPLACE INTO scanner_hits (date, scanner, symbol, payload_json, created_at) "
                "VALUES ('2026-08-27', 'squeeze', 'COMI', '{}', '2026-08-27T15:00:00+03:00')"
            )
        assert db.query("SELECT COUNT(*) AS n FROM scanner_hits")[0]["n"] == 1
