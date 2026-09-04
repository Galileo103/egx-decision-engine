"""Proven-rules scanner, checklist replay, and their Candidates / edge wiring — offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_rules_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app import symbols as symbols_mod  # noqa: E402
from app.services import edge, leaders, patterns, replay, rule_scanner, scorecard, screeners  # noqa: E402
from app.services import rules_backtest as RB  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("scanner_hits", "signal_outcomes", "proven_edge", "setups", "positions", "watchlist"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    scorecard.invalidate_weights()
    yield


def _bars(closes, vols=None, start=datetime(2025, 1, 6)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.3,
                    "low": min(o, c) - 0.3, "close": c, "volume": vols[i] if vols else 200_000})
        day += timedelta(days=1)
    return out


def _breakout_stock(n=260):
    """Flat base, then the LAST bar closes above the 20-day high on 2x volume (range_breakout)."""
    closes = [100.0 + (0.3 if i % 2 else -0.3) for i in range(n - 1)] + [103.5]
    vols = [200_000] * (n - 1) + [500_000]
    return _bars(closes, vols)


def _flat_stock(n=260):
    return _bars([50.0 + (0.2 if i % 2 else -0.2) for i in range(n)])


def _install(monkeypatch, table):
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym.upper(), []))
    any_c = next(iter(table.values()))
    dates = [c["time"] for c in any_c]
    monkeypatch.setattr(leaders, "benchmark_series",
                        lambda force=False, range_="1y": {"source": "test", "dates": dates, "series": {d: 100.0 for d in dates}})
    monkeypatch.setattr(rule_scanner, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(replay, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(RB, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(symbols_mod, "universe", lambda name: list(table))


class TestRuleScanner:
    def test_last_bar_breakout_is_found_and_journaled_live(self, monkeypatch) -> None:
        _install(monkeypatch, {"BRK": _breakout_stock(), "FLT": _flat_stock()})
        out = rule_scanner.scan("TEST", persist=True)
        assert "error" not in out and out["scanned"] == 2
        assert out["by_rule"].get("range_breakout") == 1
        hit = next(r for r in out["rows"] if r["scanner"] == "range_breakout")
        assert hit["symbol"] == "BRK" and hit["price"] == 103.5 and hit["volume_ratio"] > 2
        rows = db.query("SELECT scanner, symbol, source, date FROM scanner_hits")
        assert rows and all(r["source"] == "live" for r in rows)
        assert rows[0]["date"] == _breakout_stock()[-1]["time"]
        # idempotent — a second scan replaces, never duplicates
        rule_scanner.scan("TEST", persist=True)
        assert db.query("SELECT COUNT(*) AS n FROM scanner_hits")[0]["n"] == len(rows)

    def test_illiquid_names_are_dropped(self, monkeypatch) -> None:
        thin = _breakout_stock()
        for c in thin:
            c["volume"] = 10          # ~1,000 EGP a day
        thin[-1]["volume"] = 40       # the breakout bar still has 4x volume, so the rule fires…
        _install(monkeypatch, {"BRK": thin})
        out = rule_scanner.scan("TEST", persist=False)
        assert out["hits"] == 0 and out["filtered_illiquid"] >= 1

    def test_latest_and_edge_attachment(self, monkeypatch) -> None:
        _install(monkeypatch, {"BRK": _breakout_stock()})
        db.execute("INSERT INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, metric_label, verdict, "
                   "verdict_text, extra_json, universe, computed_at) VALUES ('scanner', 'range_breakout', 'x', 'h', 4015, 46.3, "
                   "2.01, 'm', 'edge', 'Proven edge on this sample', '{\"rate_vs_random_pp\": 2.4, \"excess_vs_random\": 1.59}', 'EGX100', 'x')")
        rule_scanner.scan("TEST", persist=True)
        latest = rule_scanner.latest()
        assert latest["hits"] >= 1 and latest["date"] == _breakout_stock()[-1]["time"]
        rb = next(r for r in latest["rows"] if r["scanner"] == "range_breakout")
        assert rb["edge"]["verdict"] == "edge" and rb["edge"]["n"] == 4015

    def test_stored_rule_hits_reach_candidates_with_measured_weight(self, monkeypatch) -> None:
        _install(monkeypatch, {"BRK": _breakout_stock()})
        rule_scanner.scan("TEST", persist=True)
        # a replayed record makes range_breakout weigh 1.1 (55% right vs a 50% default yardstick)
        for i in range(40):
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                       "VALUES (?, 'range_breakout', ?, '{}', 'x', 'replay')", (f"2024-0{(i % 9) + 1}-10", f"R{i}"))
            hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
            exc = 1.0 if i < 22 else -1.0
            db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, ret_10, bench_10, "
                       "excess_10, graded_at, source) VALUES (?, '2024-01-10', 'range_breakout', ?, '2024-01-10', 10, ?, 0, ?, 'x', 'replay')",
                       (hid, f"R{i}", exc, exc))
        scorecard.invalidate_weights()
        latest = screeners.latest_candidates()
        syms = {c["symbol"]: c for c in latest["candidates"]}
        # the flat base + volume close above the band trips the squeeze breakout too
        assert "BRK" in syms and set(syms["BRK"]["scanners"]) == {"range_breakout", "squeeze_breakout"}
        assert syms["BRK"]["family_count"] == 2            # coil + thrust
        assert syms["BRK"]["evidence_weight"] == 2.1       # 1.1 (measured) + 1.0 (neutral)
        assert not any(s.startswith("R") for s in syms)     # replayed rows never surface
        assert screeners._family_count(["range_breakout", "momentum"]) == 1      # same thrust family
        assert screeners._family_count(["squeeze_breakout", "range_breakout"]) == 2

    def test_checklist_hits_are_excluded_from_candidates(self) -> None:
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES ('2026-09-03', 'checklist_setup', 'AAA', '{}', 'x', 'live')")
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                   "VALUES ('2026-09-02', 'momentum', 'BBB', '{}', 'x', 'live')")
        latest = screeners.latest_candidates()
        assert latest["as_of"] == "2026-09-02" and [c["symbol"] for c in latest["candidates"]] == ["BBB"]

    def test_background_job(self, monkeypatch) -> None:
        _install(monkeypatch, {"BRK": _breakout_stock()})
        out = rule_scanner.job.run_sync(rule_scanner.scan, "TEST", False, None, None)
        assert "error" not in out and rule_scanner.status()["running"] is False


class TestChecklistReplay:
    def test_checklist_accepts_a_window(self, monkeypatch) -> None:
        from app.services import checklist as CK

        c = _breakout_stock()
        _install(monkeypatch, {"BRK": c})
        monkeypatch.setattr(patterns, "detect", lambda sym, cc=None: {"symbol": sym, "patterns": [], "events": []})
        ck = CK.checklist("BRK", candles=c[:200])
        assert "error" not in ck and ck["as_of"] == c[199]["time"]
        assert ck["verdict"] in ("setup", "watch", "no_setup")

    def test_replay_journals_checklist_verdicts(self, monkeypatch) -> None:
        c = _breakout_stock(320)
        _install(monkeypatch, {"BRK": c})
        monkeypatch.setattr(patterns, "detect", lambda sym, cc=None: {"symbol": sym, "patterns": [], "events": []})
        hits = replay.checklist_hits("BRK", c, step=20)
        assert hits and all(h["scanner"].startswith("checklist_") for h in hits)
        assert all(h["payload"]["direction"] == "bullish" for h in hits)
        out = replay.run("TEST", "1y", patterns=False, checklist=True)
        assert "error" not in out and out["checklist"] is True
        names = {r["scanner"] for r in db.query("SELECT DISTINCT scanner FROM scanner_hits WHERE source = 'replay'")}
        assert any(n.startswith("checklist_") for n in names)
        # never mistaken for candidates
        assert screeners.latest_candidates()["candidates"] == []

    def test_edge_checklist_summary(self) -> None:
        def seed(verdict, exc, n=25):
            for i in range(n):
                db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                           "VALUES (?, ?, ?, '{}', 'x', 'replay')", (f"2025-05-{(i % 28) + 1:02d}", f"checklist_{verdict}", f"{verdict[:2]}{i}"))
                hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
                db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, ret_10, bench_10, "
                           "excess_10, graded_at, source) VALUES (?, '2025-05-01', ?, ?, '2025-05-01', 10, ?, 0, ?, 'x', 'replay')",
                           (hid, f"checklist_{verdict}", f"{verdict[:2]}{i}", exc, exc))
        seed("setup", 2.5)
        seed("no_setup", -0.5)
        rows = edge._scorecard_rows()
        kinds = {r["kind"] for r in rows}
        assert kinds == {"checklist"}
        setup_row = next(r for r in rows if r["name"] == "checklist_setup")
        assert setup_row["label"] == "Checklist verdict: SETUP"
        cs = edge.checklist_summary(rows, {"avg_excess": 0.42})
        assert cs["verdict"] == "edge" and cs["spread_10d"] == 3.0
        assert "The checklist works" in cs["text"] and cs["setup"]["n"] == 25
        stored = edge.latest()
        assert stored["checklist"] is None            # nothing persisted yet
