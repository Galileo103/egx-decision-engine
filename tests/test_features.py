"""Signal Scorecard + Relative-strength leaders + candidate weighting — offline.

Yahoo history is monkeypatched with synthetic candles; nothing touches the
network. Pins the grading arithmetic, the weight gate (MIN_SAMPLE), the RS
ranking maths and the fact that ranking is unchanged until a track record exists.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_feat_"), "test_feat.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import leaders, scorecard, screeners  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for table in ("scanner_hits", "signal_outcomes", "rs_leaders"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    with leaders._lock:
        leaders._candle_cache.clear()
    leaders._bench_cache = None
    scorecard._weights_cache = None
    monkeypatch.setattr(leaders, "_FETCH_PAUSE", 0.0)
    yield


def _series(closes: list[float], start: str = "2026-01-05") -> list[dict]:
    day = datetime.fromisoformat(start)
    out = []
    for c in closes:
        while day.weekday() >= 5:  # skip Sat/Sun so dates look like sessions
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": c, "high": c * 1.01,
                    "low": c * 0.99, "close": c, "volume": 200_000})
        day += timedelta(days=1)
    return out


def _fake_history(table: dict[str, list[float]]):
    def get_history(symbol, range_="1y", interval="1d"):
        key = symbol.upper().replace(".CA", "")
        if key not in table:
            return {"error": f"no data for {symbol}"}
        return {"symbol": symbol, "candles": _series(table[key])}
    return get_history


# ── benchmark ────────────────────────────────────────────────────────────────

class TestBenchmark:
    def test_proxy_when_case30_is_thin(self, monkeypatch) -> None:
        from app.services import history
        from app import symbols

        # ^CASE30 has 1 bar → proxy from two "constituents" rising 1%/day and flat.
        monkeypatch.setattr(symbols, "universe", lambda name: ["AAA", "BBB"])
        monkeypatch.setattr(leaders, "universe_symbols", lambda name: ["AAA", "BBB"])
        up = [100.0 * (1.01 ** i) for i in range(40)]
        flat = [50.0] * 40
        table = {"^CASE30": [1.0], "AAA": up, "BBB": flat}
        monkeypatch.setattr(history, "get_history", _fake_history(table))
        b = leaders.benchmark_series(force=True)
        assert "proxy" in b["source"]
        assert b["bars"] > 30
        # Equal-weight of +1% and 0% → +0.5%/day.
        dates = b["dates"]
        r = leaders.benchmark_return(b, dates[0], dates[10])
        assert r == pytest.approx(1.005 ** 10 - 1, rel=1e-6)

    def test_benchmark_return_uses_nearest_prior_bar(self) -> None:
        bench = {"dates": ["2026-01-05", "2026-01-07"], "series": {"2026-01-05": 100.0, "2026-01-07": 110.0}}
        assert leaders.benchmark_return(bench, "2026-01-05", "2026-01-08") == pytest.approx(0.10)
        assert leaders.benchmark_return(bench, "2026-01-01", "2026-01-07") is None


# ── scorecard ────────────────────────────────────────────────────────────────

def _hit(date: str, scanner: str, symbol: str) -> int:
    return db.execute(
        "INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at) VALUES (?, ?, ?, '{}', 'x')",
        (date, scanner, symbol),
    )


class TestScorecard:
    def test_grade_hit_arithmetic(self) -> None:
        candles = _series([100.0 + i for i in range(30)])  # +1 per session
        bench = {"dates": [c["time"] for c in candles],
                 "series": {c["time"]: 1000.0 for c in candles}}  # flat index
        hit = {"hit_id": 1, "date": candles[3]["time"], "scanner": "squeeze", "symbol": "AAA"}
        out = scorecard.grade_hit(hit, candles, bench)
        assert out["entry_close"] == 103.0
        assert out["ret_5"] == pytest.approx(5 / 103 * 100, abs=1e-3)
        assert out["ret_10"] == pytest.approx(10 / 103 * 100, abs=1e-3)
        assert out["ret_20"] == pytest.approx(20 / 103 * 100, abs=1e-3)
        assert out["bench_10"] == pytest.approx(0.0)
        assert out["excess_10"] == pytest.approx(out["ret_10"])

    def test_grade_hit_open_horizons_are_null(self) -> None:
        candles = _series([100.0] * 12)
        bench = {"dates": [], "series": {}}
        hit = {"hit_id": 1, "date": candles[0]["time"], "scanner": "s", "symbol": "AAA"}
        out = scorecard.grade_hit(hit, candles, bench)
        assert out["ret_5"] is not None and out["ret_10"] is not None and out["ret_20"] is None
        assert out["bench_5"] is None and out["excess_5"] is None

    def test_grade_persists_and_weights_gate_on_sample(self, monkeypatch) -> None:
        from app.services import history

        table = {"^CASE30": [1.0], "AAA": [100.0 + i for i in range(40)], "BBB": [100.0 - i * 0.5 for i in range(40)]}
        monkeypatch.setattr(leaders, "universe_symbols", lambda name: ["AAA", "BBB"])
        monkeypatch.setattr(history, "get_history", _fake_history(table))
        dates = [c["time"] for c in _series(table["AAA"])]
        # 5 momentum hits on the rising stock, 5 squeeze hits on the falling one.
        for i in range(5):
            _hit(dates[i], "momentum", "AAA")
            _hit(dates[i], "squeeze", "BBB")
        r = scorecard.grade()
        assert r["graded"] == 10 and r["fully_graded_20d"] == 10
        card = scorecard.scorecard()
        mom = card["scanners"]["momentum"]["horizons"]["10"]
        sq = card["scanners"]["squeeze"]["horizons"]["10"]
        assert mom["n"] == 5 and mom["win_rate"] == 100.0 and mom["beat_rate"] == 100.0
        assert sq["win_rate"] == 0.0
        # Below MIN_SAMPLE both weights stay neutral — 5 hits prove nothing.
        assert card["weights"] == {"momentum": 1.0, "squeeze": 1.0}
        assert "neutral" in card["scanners"]["momentum"]["weight_basis"]
        # Re-running grades nothing new (all 20d horizons complete).
        assert scorecard.grade()["graded"] == 0

    def test_weight_formula(self) -> None:
        assert scorecard._weight_from(0.5, scorecard.MIN_SAMPLE) == 1.0
        assert scorecard._weight_from(0.9, scorecard.MIN_SAMPLE) == 1.5   # capped
        assert scorecard._weight_from(0.1, scorecard.MIN_SAMPLE) == 0.5   # floored
        assert scorecard._weight_from(0.9, scorecard.MIN_SAMPLE - 1) == 1.0  # insufficient sample

    def test_evidence_weight_equals_family_count_without_record(self) -> None:
        scanners = ["volume_breakout", "momentum", "squeeze"]  # 2 families
        assert screeners._evidence_weight(scanners, {}) == screeners._family_count(scanners)
        # A proven family counts more; an unproven one stays at 1.0.
        assert screeners._evidence_weight(scanners, {"squeeze": 1.4}) == pytest.approx(2.4)
        # Inside a family the best scanner's weight wins (no double count).
        assert screeners._evidence_weight(["volume_breakout", "momentum"], {"momentum": 1.5, "volume_breakout": 0.6}) == 1.5


# ── leaders ──────────────────────────────────────────────────────────────────

class TestLeaders:
    def test_compute_ranks_outperformer_first_and_filters_illiquid(self, monkeypatch) -> None:
        from app.services import history
        from app.config import settings

        n = 140
        strong = [100.0 * (1.004 ** i) for i in range(n)]      # steady uptrend
        weak = [100.0 * (0.998 ** i) for i in range(n)]        # steady downtrend
        flat = [100.0] * n
        table = {"^CASE30": [1.0], "STRONG": strong, "WEAK": weak, "FLAT": flat}
        monkeypatch.setattr(history, "get_history", _fake_history(table))
        monkeypatch.setattr(leaders, "universe_symbols", lambda name: ["STRONG", "WEAK", "FLAT"])
        monkeypatch.setattr(settings, "min_daily_value_egp", 1.0)

        out = leaders.compute("EGX100", limit=10, persist=True)
        assert "error" not in out
        syms = [r["symbol"] for r in out["rows"]]
        assert syms[0] == "STRONG" and syms[-1] == "WEAK"
        top = out["rows"][0]
        assert top["ret_3m"] > 0 and top["excess_3m"] > 0 and top["new_high"] is True and top["above_sma50"] is True
        assert out["rows"][-1]["new_high"] is False
        # Stored ranking is served by latest().
        stored = leaders.latest("EGX100")
        assert stored["stored"] is True and stored["rows"][0]["symbol"] == "STRONG"

    def test_illiquid_names_are_filtered(self, monkeypatch) -> None:
        from app.services import history
        from app.config import settings

        table = {"^CASE30": [1.0], "AAA": [100.0 * (1.003 ** i) for i in range(140)]}
        monkeypatch.setattr(history, "get_history", _fake_history(table))
        monkeypatch.setattr(leaders, "universe_symbols", lambda name: ["AAA"])
        # Synthetic volume is 200k shares × ~100 EGP ≈ 20-30M EGP/day; set the floor above it.
        monkeypatch.setattr(settings, "min_daily_value_egp", 1e12)
        out = leaders.compute("EGX30", limit=10)
        assert out["rows"] == [] and out["filtered_illiquid"] == 1
        assert leaders.compute("EGX30", limit=10, include_illiquid=True)["rows"][0]["liquid"] is False

    def test_latest_empty_before_first_run(self) -> None:
        assert leaders.latest("EGX70") == {"rows": [], "universe": "EGX70", "date": None, "stored": False}


class TestLatestCandidates:
    def test_rebuilds_from_stored_hits_without_network(self) -> None:
        import json as _json
        for scanner, sym, payload in [
            ("squeeze", "AAA", {"indicators": {"close": 10.0}, "changePercent": 1.2}),
            ("momentum", "AAA", {"price": 10.1, "current_change": 1.5, "score": 66}),
            ("smart_money", "BBB", {"last_close": 5.0}),
            ("pattern_double_bottom", "CCC", {"neckline": 1}),   # excluded: patterns have their own tab
        ]:
            db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at) VALUES (?, ?, ?, ?, 'x')",
                       ("2026-09-02", scanner, sym, _json.dumps(payload)))
        out = screeners.latest_candidates()
        assert out["stored"] is True and out["as_of"] == "2026-09-02"
        syms = [c["symbol"] for c in out["candidates"]]
        assert syms == ["AAA", "BBB"] and "CCC" not in syms
        aaa = out["candidates"][0]
        assert aaa["hit_count"] == 2 and aaa["family_count"] == 2 and aaa["price"] in (10.0, 10.1) and aaa["score"] == 66

    def test_empty_when_nothing_stored(self) -> None:
        out = screeners.latest_candidates()
        assert out["candidates"] == [] and out["as_of"] is None
