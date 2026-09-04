"""Historical replay + Proven-edge table — synthetic candles, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_edge_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app import symbols as symbols_mod  # noqa: E402
from app.services import edge, leaders, replay, scorecard, screeners  # noqa: E402
from app.services import rules_backtest as RB  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for table in ("scanner_hits", "signal_outcomes", "proven_edge", "backtest_runs"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    scorecard.invalidate_weights()
    yield


# ── synthetic market ─────────────────────────────────────────────────────────


def _bars(closes, vols=None, start=datetime(2023, 1, 2)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.3,
                    "low": min(o, c) - 0.3, "close": c, "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _momentum_stock(n=700):
    """Flat, then repeated 3-up steps with mild pullbacks — fires momentum_3 often."""
    closes = [100.0 + (0.4 if i % 2 else -0.4) for i in range(160)]
    px = 100.0
    for i in range(n - 160):
        px += 1.0 if i % 5 != 4 else -2.0   # keeps RSI14 inside the 50-75 momentum window
        closes.append(px)
    return _bars(closes)


def _bench(candles):
    """A benchmark that is flat: every positive return beats it."""
    dates = [c["time"] for c in candles]
    return {"source": "test", "dates": dates, "series": {d: 100.0 for d in dates}}


def _install(monkeypatch, table: dict[str, list[dict]]):
    monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": table.get(sym.upper(), []))
    any_c = next(iter(table.values()))
    monkeypatch.setattr(leaders, "benchmark_series", lambda force=False, range_="1y": _bench(any_c))
    monkeypatch.setattr(replay, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(RB, "universe_symbols", lambda name: list(table))
    monkeypatch.setattr(symbols_mod, "universe", lambda name: list(table))


# ── replay ───────────────────────────────────────────────────────────────────


class TestReplay:
    def test_rule_hits_fire_on_synthetic_momentum(self) -> None:
        hits = replay.rule_hits("AAA", _momentum_stock())
        names = {h["scanner"] for h in hits}
        assert "momentum_3" in names
        assert all(h["payload"]["replay"] is True for h in hits)
        assert all(h["date"] >= "2023-01-02" for h in hits)

    def test_run_journals_as_replay_and_grades_immediately(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock()})
        out = replay.run("TEST", "1y", patterns=False)
        assert "error" not in out and out["signals_found"] > 0
        assert out["new_hits"] == out["signals_found"]
        rows = db.query("SELECT source, COUNT(*) AS n FROM scanner_hits GROUP BY source")
        assert rows == [{"source": "replay", "n": out["signals_found"]}]
        graded = db.query("SELECT COUNT(*) AS n FROM signal_outcomes WHERE source = 'replay'")[0]["n"]
        assert graded == out["graded"] > 0
        # signals inside the last 20 sessions cannot be fully graded yet
        assert out["fully_graded_20d"] < out["graded"] or out["fully_graded_20d"] == out["graded"]
        # idempotent: a second run adds nothing
        again = replay.run("TEST", "1y", patterns=False)
        assert again["new_hits"] == 0

    def test_replayed_hits_never_become_candidates(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock()})
        replay.run("TEST", "1y", patterns=False)
        assert db.query("SELECT COUNT(*) AS n FROM scanner_hits")[0]["n"] > 0
        latest = screeners.latest_candidates()
        assert latest["candidates"] == [] and latest["as_of"] is None
        # setups/guardian-style readers that filter live rows see nothing either
        live = db.query("SELECT COUNT(*) AS n FROM scanner_hits WHERE COALESCE(source,'live') = 'live'")[0]["n"]
        assert live == 0

    def test_clear_removes_only_replay(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock()})
        replay.run("TEST", "1y", patterns=False)
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at) "
                   "VALUES ('2026-09-03', 'momentum', 'AAA', '{}', 'x')")
        res = replay.clear()
        assert res["removed_hits"] > 0
        left = db.query("SELECT scanner, source FROM scanner_hits")
        assert left == [{"scanner": "momentum", "source": "live"}]

    def test_prune_keeps_replay_rows(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock()})
        replay.run("TEST", "1y", patterns=False)
        db.execute("UPDATE scanner_hits SET created_at = '2020-01-01T00:00:00+02:00'")
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at) "
                   "VALUES ('2020-01-01', 'momentum', 'AAA', '{}', '2020-01-01T00:00:00+02:00')")
        removed = db.prune("scanner_hits", "created_at", 180)
        assert removed == 1
        assert db.query("SELECT COUNT(*) AS n FROM scanner_hits WHERE source = 'replay'")[0]["n"] > 0

    def test_background_job_reports_progress(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock(), "BBB": _momentum_stock()})
        out = replay.job.run_sync(replay.run, "TEST", "1y", False, None)
        assert "error" not in out and out["symbols"] == 2
        st = replay.status()
        assert st["running"] is False and st["phase"] == "finished" and st["done"] == 2
        assert st["stored"]["replayed_hits"] == out["signals_found"]


# ── scorecard proxy weights ──────────────────────────────────────────────────


class TestProxyWeights:
    def _seed(self, scanner: str, n: int, beat: bool, source: str = "replay") -> None:
        for i in range(n):
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                       "VALUES (?, ?, ?, '{}', 'x', ?)", (f"2025-01-{(i % 28) + 1:02d}", scanner, f"S{i}", source))
            hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
            exc = 1.5 if beat else -1.5
            db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, "
                       "ret_10, bench_10, excess_10, graded_at, source) VALUES (?, ?, ?, ?, ?, 10, ?, 0, ?, 'x', ?)",
                       (hid, "2025-01-01", scanner, f"S{i}", "2025-01-01", exc, exc, source))

    def test_live_scanner_borrows_replayed_proxy_until_it_has_its_own(self) -> None:
        self._seed("momentum_3", 40, beat=True)          # replayed proxy, 100% beat
        self._seed("range_breakout", 40, beat=False)     # replayed proxy, 0% beat
        card = scorecard.scorecard()
        w = card["weights"]
        assert w["momentum_3"] == 1.5 and w["range_breakout"] == 0.5
        # live scanners inherit, labelled
        assert w["momentum"] == 1.5 and card["scanners"]["momentum"]["proxy"] == "momentum_3"
        assert w["volume_breakout"] == 0.5
        assert "proxy" in card["scanners"]["momentum"]["weight_basis"]
        assert "smart_money" not in w                    # no proxy → untouched (neutral 1.0 downstream)
        assert card["outcomes_by_source"] == {"replay": 80}
        assert screeners._evidence_weight(["momentum"], w) == 1.5

    def test_own_live_sample_overrides_proxy(self) -> None:
        self._seed("momentum_3", 40, beat=True)
        self._seed("momentum", 25, beat=False, source="live")
        card = scorecard.scorecard()
        assert card["weights"]["momentum"] == 0.5
        assert card["scanners"]["momentum"]["proxy"] is None
        assert card["scanners"]["momentum"]["sources"] == {"live": 25}

    def test_small_proxy_sample_does_not_move_weights(self) -> None:
        self._seed("momentum_3", 10, beat=True)
        card = scorecard.scorecard()
        assert card["weights"]["momentum_3"] == 1.0 and "momentum" not in card["weights"]


# ── proven edge ──────────────────────────────────────────────────────────────


class TestEdge:
    def test_verdict_thresholds(self) -> None:
        assert edge.rule_verdict(5, 1.0) == "too_few"
        assert edge.rule_verdict(30, 0.25) == "edge"
        assert edge.rule_verdict(30, 0.05) == "marginal"
        assert edge.rule_verdict(30, -0.1) == "negative"
        # signals are judged against a random entry: (n, rate vs random pp, excess vs random, se)
        assert edge.beat_verdict(30, +4.0, +1.5, 0.3) == "edge"
        assert edge.beat_verdict(30, +4.0, +1.5, 1.0) == "marginal"     # 1.5 < 2 SE: luck, not edge
        assert edge.beat_verdict(30, -5.0, +1.5, 0.3) == "negative"     # right less often than random
        assert edge.beat_verdict(30, +1.0, +0.2, 0.05) == "marginal"
        assert edge.beat_verdict(30, -1.0, -1.5, 0.3) == "negative"
        assert edge.beat_verdict(30, None, None, None) == "too_few"
        assert edge.beat_verdict(10, +9.0, +5.0, 0.1) == "too_few"

    def test_two_way_patterns_use_the_direction_recorded_on_each_hit(self) -> None:
        # 'breakout' is neutral in the catalog; each hit says which way it broke.
        for i in range(25):
            for direction, exc in (("bullish", 3.0), ("bearish", -3.0)):
                db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                           "VALUES (?, 'pattern_breakout', ?, ?, 'x', 'replay')",
                           (f"2025-04-{(i % 28) + 1:02d}", f"{direction[:2]}{i}", '{"direction": "%s"}' % direction))
                hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
                db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, "
                           "ret_10, bench_10, excess_10, graded_at, source) VALUES (?, '2025-04-01', 'pattern_breakout', ?, "
                           "'2025-04-01', 10, ?, 0, ?, 'x', 'replay')", (hid, f"{direction[:2]}{i}", exc, exc))
        h = scorecard.scorecard()["scanners"]["pattern_breakout"]["horizons"]["10"]
        # up-breakouts rose 3%, down-breakouts fell 3%: both were right
        assert h["beat_rate"] == 100.0 and h["avg_excess"] == 3.0

    def test_bearish_signals_are_graded_on_the_stock_falling(self) -> None:
        for i in range(25):
            for scanner, exc in (("pattern_triple_top", -5.0), ("pattern_hammer", -5.0)):
                db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                           "VALUES (?, ?, ?, '{}', 'x', 'replay')", (f"2025-03-{(i % 28) + 1:02d}", scanner, f"Q{i}"))
                hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
                db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, "
                           "ret_10, bench_10, excess_10, graded_at, source) VALUES (?, '2025-03-01', ?, ?, '2025-03-01', "
                           "10, ?, 0, ?, 'x', 'replay')", (hid, scanner, f"Q{i}", exc, exc))
        card = scorecard.scorecard()
        top = card["scanners"]["pattern_triple_top"]["horizons"]["10"]
        ham = card["scanners"]["pattern_hammer"]["horizons"]["10"]
        assert card["scanners"]["pattern_triple_top"]["direction"] == "bearish"
        # same raw outcome (-5%), opposite meaning: the bearish call was right, the bullish one wrong
        assert top["beat_rate"] == 100.0 and top["avg_excess"] == 5.0
        assert ham["beat_rate"] == 0.0 and ham["avg_excess"] == -5.0
        assert card["weights"]["pattern_triple_top"] == 1.5 and card["weights"]["pattern_hammer"] == 0.5

    def test_compute_persists_rules_scanners_and_patterns(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock(), "BBB": _momentum_stock()})
        replay.run("TEST", "1y", patterns=False)
        # two replayed patterns with identical raw outcomes (stock fell 5% vs index):
        # a bearish one (right) and a bullish one (wrong)
        for i in range(25):
            for scanner in ("pattern_triple_top", "pattern_hammer"):
                db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
                           "VALUES (?, ?, ?, '{}', 'x', 'replay')", (f"2025-02-{(i % 28) + 1:02d}", scanner, f"P{i}"))
                hid = db.query("SELECT MAX(id) AS id FROM scanner_hits")[0]["id"]
                db.execute("INSERT INTO signal_outcomes (hit_id, date, scanner, symbol, entry_date, entry_close, "
                           "ret_10, bench_10, excess_10, graded_at, source) VALUES (?, '2025-02-01', ?, ?, "
                           "'2025-02-01', 10, -5.0, 0, -5.0, 'x', 'replay')", (hid, scanner, f"P{i}"))
        out = edge.compute("TEST", "1y", persist=True)
        assert "error" not in out
        assert out["baseline"] and out["baseline"]["sessions"] >= 500
        kinds = {r["kind"] for r in out["rows"]}
        assert kinds == {"rule", "scanner", "pattern", "baseline"}
        rule_names = {r["name"] for r in out["rows"] if r["kind"] == "rule"}
        assert rule_names == set(RB.ENTRY_RULES)
        pats = {r["name"]: r for r in out["rows"] if r["kind"] == "pattern"}
        assert pats["pattern_triple_top"]["verdict"] == "edge" and pats["pattern_hammer"]["verdict"] == "negative"
        assert pats["pattern_triple_top"]["edge_metric"] == 5.0 and pats["pattern_hammer"]["edge_metric"] == -5.0
        assert pats["pattern_triple_top"]["extra"]["direction"] == "bearish"
        assert "random" in out["headline"].lower() and out["summary"]["by_kind"]["rule"] == 4
        assert "baseline" not in out["summary"]["by_kind"]
        # the Scorecard now reads the stored yardstick
        assert scorecard.baseline()["measured"] is True
        stored = edge.latest()
        assert stored["stored"] is True and stored["baseline"]["sessions"] == out["baseline"]["sessions"]
        assert len(stored["rows"]) == len(out["rows"]) - 1          # baseline row lifted out of the table
        assert stored["as_of"] and stored["rows"][0]["kind"] == "rule"   # rules first
        assert isinstance(stored["rows"][0]["extra"], dict)

    def test_latest_is_empty_before_first_compute(self) -> None:
        out = edge.latest()
        assert out["rows"] == [] and out["as_of"] is None
        assert "replay" in out["headline"].lower()

    def test_background_refresh(self, monkeypatch) -> None:
        _install(monkeypatch, {"AAA": _momentum_stock()})
        out = edge.job.run_sync(edge.compute, "TEST", "1y")
        assert "error" not in out
        assert edge.status()["running"] is False and edge.status()["result"]["rows"]
