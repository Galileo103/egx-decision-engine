"""Task 6 — weekly review: week bounds, attribution, you-vs-system, discipline, Guardian
follow-through, heat series, notes, digest. Offline (portfolio marks stubbed)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_review_"), "t.db")
os.environ.setdefault("ACCOUNT_SIZE", "100000")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import portfolio, review  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for table in ("positions", "position_fills", "guardian_verdicts", "scanner_hits", "proven_edge",
                  "review_notes", "snapshots"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    monkeypatch.setattr(portfolio, "atr14", lambda sym: 1.0)
    monkeypatch.setattr(review, "_performance", lambda: {
        "open_count": 1, "closed_count": 2, "realized_pnl": 500.0, "unrealized_pnl": 120.0, "win_rate": 50.0,
        "avg_r": 0.4, "open_heat_pct": 1.2,
        "benchmark": {"since": "2026-08-31", "index_change_pct": 1.5, "portfolio_net_pnl": 620.0,
                      "portfolio_return_pct_of_account": 0.62}, "benchmark_note": "EGX30 +1.5%"})
    yield


def _pos(symbol, entry, stop, opened, closed=None, exit_price=None, qty=100, plan_followed=None, t1=None,
         stop_now=None):
    db.execute(
        "INSERT INTO positions (symbol, side, qty, entry, stop, initial_stop, target1, opened_at, closed_at, exit_price, "
        "note, status, plan_followed) VALUES (?, 'long', ?, ?, ?, ?, ?, ?, ?, ?, 'test', ?, ?)",
        (symbol, qty, entry, stop_now if stop_now is not None else stop, stop, t1, opened + "T11:00:00+03:00",
         (closed + "T12:00:00+03:00") if closed else None, exit_price, "closed" if closed else "open", plan_followed))
    return db.query("SELECT MAX(id) AS id FROM positions")[0]["id"]


def _hit(symbol, scanner, d):
    db.execute("INSERT OR IGNORE INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
               "VALUES (?, ?, ?, '{}', 'x', 'live')", (d, scanner, symbol))


def _edge_rule(name, avg_r, win, n=1000, verdict="edge"):
    db.execute("INSERT OR REPLACE INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, metric_label, "
               "verdict, verdict_text, extra_json, universe, computed_at) VALUES ('rule', ?, ?, '3y', ?, ?, ?, 'avg R', ?, '', "
               "'{}', 'EGX100', 'x')", (name, name, n, win, avg_r, verdict))


class TestWeek:
    def test_bounds_sunday_to_thursday(self) -> None:
        assert review.week_bounds(date(2026, 9, 6)) == (date(2026, 9, 6), date(2026, 9, 10))     # Sunday
        assert review.week_bounds(date(2026, 9, 8)) == (date(2026, 9, 6), date(2026, 9, 10))     # Tuesday
        assert review.week_bounds(date(2026, 9, 10)) == (date(2026, 9, 6), date(2026, 9, 10))    # Thursday
        # Friday / Saturday review the week that just ended
        assert review.week_bounds(date(2026, 9, 11)) == (date(2026, 9, 6), date(2026, 9, 10))
        assert review.week_bounds(date(2026, 9, 12)) == (date(2026, 9, 6), date(2026, 9, 10))


class TestAttribution:
    def test_live_rule_hits_on_or_before_fill(self) -> None:
        _hit("COMI", "range_breakout", "2026-09-01")
        _hit("COMI", "pattern_bull_flag", "2026-09-01")       # context, not an entry rule
        _hit("COMI", "checklist_setup", "2026-09-01")
        _hit("COMI", "squeeze", "2026-08-30")                 # 2 days before: still counts
        _hit("COMI", "momentum_3", "2026-08-20")              # too old
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES ('2026-09-01', 'pullback_trend', 'COMI', '{}', 'x', 'replay')")   # replay rows never count
        assert review.attribute("COMI", "2026-09-01T11:00:00+03:00") == ["range_breakout", "squeeze"]
        assert review.attribute("COMI", None) == []


class TestReview:
    def test_full_week_with_trades_and_verdicts(self) -> None:
        _edge_rule("range_breakout", 0.38, 45.8)
        _edge_rule("momentum_3", 0.26, 44.9)
        # two closed trades in the week of 2026-09-06: one by the plan (stop), one discretionary
        _hit("AAA", "range_breakout", "2026-08-31")
        _pos("AAA", 100.0, 96.0, "2026-08-31", closed="2026-09-07", exit_price=112.0, plan_followed=1, t1=112.0)
        _hit("BBB", "momentum_3", "2026-09-01")
        _pos("BBB", 50.0, 48.0, "2026-09-01", closed="2026-09-08", exit_price=49.0, plan_followed=0, t1=56.0,
             stop_now=47.0)                                     # stop was LOWERED, exit by hand
        # an older closed trade outside the week, unattributed
        _pos("CCC", 10.0, 9.0, "2026-08-10", closed="2026-08-20", exit_price=11.0, plan_followed=1)
        # open position opened this week with a Guardian TIGHTEN_STOP that was acted on
        pid = _pos("DDD", 20.0, 19.0, "2026-09-06", stop_now=19.6)
        db.execute("INSERT INTO guardian_verdicts (date, position_id, symbol, verdict, severity, mark, r_now, suggested_stop, "
                   "reasons_json, notified, created_at) VALUES ('2026-09-07', ?, 'DDD', 'TIGHTEN_STOP', 'advice', 21.2, 1.2, 19.5, "
                   "'[\"raise\"]', 0, 'x')", (pid,))
        # and an EXIT_STOP on BBB with no ledger action before it closed... it closed on 09-08 -> acted
        bbb = db.query("SELECT id FROM positions WHERE symbol = 'BBB'")[0]["id"]
        db.execute("INSERT INTO guardian_verdicts (date, position_id, symbol, verdict, severity, mark, r_now, reasons_json, "
                   "notified, created_at) VALUES ('2026-09-07', ?, 'BBB', 'EXIT_STOP', 'critical', 47.5, -1.2, '[\"out\"]', 0, 'x')",
                   (bbb,))
        # an ignored actionable verdict on AAA before it closed? AAA closed 09-07 at target -> acted (closed)
        rev = review.compute("2026-09-08")
        assert "error" not in rev
        assert rev["week"]["start"] == "2026-09-06" and rev["week"]["end"] == "2026-09-10"
        assert rev["week"]["prev"] == "2026-08-30" and rev["week"]["next"] == "2026-09-13"
        assert [t["symbol"] for t in rev["closed"]] == ["BBB", "AAA"] or [t["symbol"] for t in rev["closed"]] == ["AAA", "BBB"]
        by = {t["symbol"]: t for t in rev["closed"]}
        assert by["AAA"]["exit_how"] == "target" and by["AAA"]["r_net"] > 2.8   # 3R gross, net of fees
        assert by["BBB"]["exit_how"] == "discretionary" and by["BBB"]["stop_lowered"] is True
        assert by["AAA"]["rules"] == ["range_breakout"] and by["BBB"]["rules"] == ["momentum_3"]
        assert [o["symbol"] for o in rev["opened"]] == ["DDD"]
        # you vs system covers ALL closed trades, per rule, against the replayed expectation
        vs = {r["rule"]: r for r in rev["you_vs_system"]["rows"]}
        assert vs["range_breakout"]["system_avg_r"] == 0.38 and vs["range_breakout"]["n"] == 1
        assert vs["range_breakout"]["gap_r"] == round(vs["range_breakout"]["avg_r"] - 0.38, 2)
        assert "too few" in vs["range_breakout"]["read"]
        assert [u["symbol"] for u in rev["you_vs_system"]["unattributed"]] == ["CCC"]
        # discipline
        d = rev["discipline"]
        assert d["followed_n"] == 2 and d["deviated_n"] == 1 and d["stops_lowered"] == ["BBB"]
        # CCC had no target recorded, so its by-hand exit is discretionary too
        assert sorted(d["discretionary_exits"]) == ["BBB", "CCC"] and d["avg_r_followed"] > d["avg_r_deviated"]
        assert d["read"].startswith("Deviating from the plan cost you")
        # guardian follow-through
        g = {(r["symbol"], r["verdict"]): r for r in rev["guardian"]["rows"]}
        assert g[("DDD", "TIGHTEN_STOP")]["acted"] is True and g[("DDD", "TIGHTEN_STOP")]["how"] == "stop raised"
        assert g[("BBB", "EXIT_STOP")]["acted"] is True and g[("BBB", "EXIT_STOP")]["how"] == "closed"
        assert rev["guardian"]["ignored"] == []
        # heat per session: DDD open from 09-06 with risk (20-19.6)*100 = 40 EGP -> 0.04%; AAA/BBB open on 09-06/09-07
        heat = {h["date"]: h for h in rev["heat"]}
        assert set(heat) >= {"2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"}
        assert heat["2026-09-06"]["open_positions"] == 3 and heat["2026-09-10"]["open_positions"] == 1
        from app.config import settings
        assert heat["2026-09-10"]["heat_pct"] == pytest.approx(round(40.0 / settings.account_size * 100.0, 2))
        # headline + digest
        assert "2 trades closed" in rev["headline"] and "1 opened" in rev["headline"]
        assert "EGX30 +1.50%" in rev["headline"]
        txt = review.digest_text(rev)
        assert txt.startswith("[EGX weekly review] 2026-09-06") and "range_breakout: you" in txt
        assert "Plan followed: 2×" in txt

    def test_ignored_actionable_verdict_is_called_out(self) -> None:
        pid = _pos("EEE", 10.0, 9.0, "2026-09-01")
        db.execute("INSERT INTO guardian_verdicts (date, position_id, symbol, verdict, severity, mark, r_now, reasons_json, "
                   "notified, created_at) VALUES ('2026-09-07', ?, 'EEE', 'EXIT_STOP', 'critical', 8.9, -1.1, '[]', 0, 'x')", (pid,))
        db.execute("INSERT INTO guardian_verdicts (date, position_id, symbol, verdict, severity, mark, r_now, reasons_json, "
                   "notified, created_at) VALUES ('2026-09-08', ?, 'EEE', 'EXIT_STOP', 'critical', 8.7, -1.3, '[]', 0, 'x')", (pid,))
        rev = review.compute("2026-09-08")
        g = rev["guardian"]
        assert g["ignored"] == ["EEE EXIT_STOP"] and g["rows"][0]["repeats"] == 2
        assert "no action in the ledger" in g["read"] and "EEE EXIT_STOP" in rev["headline"]
        # a partial sale after the verdict counts as acting on it
        db.execute("INSERT INTO position_fills (position_id, ts, side, qty, price, fees, realized_pnl, entry_after, qty_after, note) "
                   "VALUES (?, '2026-09-09T11:00:00+03:00', 'sell', 50, 8.8, 1, -61, 10, 50, '')", (pid,))
        rev2 = review.compute("2026-09-08")
        assert rev2["guardian"]["ignored"] == [] and rev2["guardian"]["rows"][0]["how"] == "sold 50 shares"

    def test_empty_week_has_no_errors(self) -> None:
        rev = review.compute("2026-07-15")
        assert "error" not in rev and rev["closed"] == [] and rev["opened"] == []
        assert rev["you_vs_system"]["rows"] == [] and rev["guardian"]["rows"] == []
        assert rev["discipline"]["read"].startswith("Not enough")
        assert all(h["open_positions"] == 0 and h["heat_pct"] == 0.0 for h in rev["heat"])
        assert "0 trades closed" in rev["headline"]
        assert review.digest_text(rev).startswith("[EGX weekly review]")

    def test_notes_round_trip_and_normalise_to_sunday(self) -> None:
        res = review.save_note("2026-09-08", "  Let the Guardian decide.  ")
        assert res["ok"] is True and res["week_start"] == "2026-09-06" and res["text"] == "Let the Guardian decide."
        assert review.get_note("2026-09-06")["text"] == "Let the Guardian decide."
        rev = review.compute("2026-09-07")
        assert rev["note"]["text"] == "Let the Guardian decide."
        assert "Lesson: Let the Guardian decide." in review.digest_text(rev)
        assert review.save_note("nonsense", "x")["error"]
        assert review.save_note("2026-09-06", "")["ok"] is True and review.notes() == []

    def test_digest_does_not_send_when_asked_not_to(self, monkeypatch) -> None:
        from app.services import alerts

        calls = []
        monkeypatch.setattr(alerts, "send_telegram", lambda text: calls.append(text) or True)
        out = review.digest(send=False, week="2026-09-08")
        assert out["sent"] is False and out["text"].startswith("[EGX weekly review]") and calls == []
        out2 = review.digest(send=True, week="2026-09-08")
        assert out2["sent"] is True and len(calls) == 1 and out2["week"] == "2026-09-06 → 2026-09-10"
