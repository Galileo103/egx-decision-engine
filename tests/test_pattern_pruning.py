"""Task 2 — pattern catalog pruned to measured survivors (Proven-edge verdicts)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_prune_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, edge, leaders, pattern_catalog, patterns  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for table in ("proven_edge", "pattern_hits", "scanner_hits", "signal_outcomes", "regime_daily"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
    edge.invalidate_pattern_edges()
    with leaders._lock:
        leaders._candle_cache.clear()
    yield


def _edge_row(key: str, verdict: str, horizon: int = 10, n: int = 100, metric: float = 1.0) -> None:
    extra = {"horizon": horizon, "horizons": {"10": {"verdict": verdict}, str(horizon): {"verdict": verdict}},
             "by_regime": {"bull": {"verdict": verdict, "n": n, "edge_metric": metric}}}
    db.execute("INSERT OR REPLACE INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, metric_label, "
               "verdict, verdict_text, extra_json, universe, computed_at) VALUES ('pattern', ?, ?, 'x', ?, 50, ?, '', ?, '', ?, 'T', 'x')",
               (f"pattern_{key}", key, n, metric, verdict, json.dumps(extra)))
    edge.invalidate_pattern_edges()


def _bars(closes, start=datetime(2024, 1, 2)):
    day, out = start, []
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        o = closes[i - 1] if i else c
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": max(o, c) + 0.3,
                    "low": min(o, c) - 0.3, "close": c, "volume": 100_000})
        day += timedelta(days=1)
    return out


class TestEdgeLookup:
    def test_pattern_edges_reads_verdicts_and_horizons(self) -> None:
        assert edge.pattern_edges() == {}
        _edge_row("double_bottom", "edge", horizon=40, n=300, metric=1.8)
        _edge_row("doji", "negative", n=7000, metric=-0.3)
        _edge_row("three_inside_up", "too_few", n=8)
        e = edge.pattern_edges()
        assert e["double_bottom"]["verdict"] == "edge" and e["double_bottom"]["horizon"] == 40
        assert e["doji"]["verdict"] == "negative"
        assert e["three_inside_up"]["verdict"] == "too_few"
        # cached until invalidated
        _edge_row("hammer", "marginal")
        assert "hammer" in edge.pattern_edges()


class TestCatalogStamp:
    def test_attach_edge_and_views(self) -> None:
        edges = {"double_bottom": {"verdict": "edge", "horizon": 40, "n": 300, "edge_metric": 1.8, "hit_rate": 48},
                 "doji": {"verdict": "negative", "horizon": 10, "n": 7000, "edge_metric": -0.3, "hit_rate": 49},
                 "hammer": {"verdict": "marginal", "horizon": 10, "n": 400, "edge_metric": -0.2, "hit_rate": 42},
                 "three_inside_up": {"verdict": "too_few", "horizon": 10, "n": 8}}
        rows = [pattern_catalog.enrich({"pattern": k}, edges) for k in
                ("double_bottom", "doji", "hammer", "three_inside_up", "weekly_higher_high_higher_low")]
        by = {r["pattern"]: r for r in rows}
        assert by["double_bottom"]["proven"] is True and by["double_bottom"]["edge_horizon"] == 40
        assert by["doji"]["edge_verdict"] == "negative" and by["doji"]["proven"] is False
        assert by["three_inside_up"]["edge_verdict"] == "unmeasured"       # too_few reads as unmeasured
        assert by["weekly_higher_high_higher_low"]["edge_verdict"] == "unmeasured"
        proven = [r["pattern"] for r in rows if pattern_catalog.passes_view(r, "proven")]
        not_neg = [r["pattern"] for r in rows if pattern_catalog.passes_view(r, "not_negative")]
        everything = [r["pattern"] for r in rows if pattern_catalog.passes_view(r, "all")]
        assert proven == ["double_bottom"]
        assert not_neg == ["double_bottom", "hammer", "three_inside_up", "weekly_higher_high_higher_low"]
        assert len(everything) == 5
        # without an edge table nothing is silently 'proven'
        plain = pattern_catalog.enrich({"pattern": "double_bottom"}, {})
        assert plain["edge_verdict"] == "unmeasured" and plain["proven"] is False


class TestDetectView:
    def test_detect_filters_before_counting(self, monkeypatch) -> None:
        # a chart with a clear doji-like flat bar pattern set is hard to force; stub the sub-detectors
        candles = _bars([10.0 + 0.05 * i for i in range(200)])
        from app.services import pattern_action, pattern_candles, pattern_geometry, weekly

        def fake_detect(c, atr):
            return [{"pattern": "doji", "status": "confirmed", "quality": 60, "direction": "neutral",
                     "neckline": None, "target": None, "start_date": c[-2]["time"], "break_date": c[-1]["time"]},
                    {"pattern": "bull_trap", "status": "confirmed", "quality": 70, "direction": "bearish",
                     "neckline": 19.0, "target": 18.0, "start_date": c[-5]["time"], "break_date": c[-1]["time"]},
                    {"pattern": "hammer", "status": "confirmed", "quality": 55, "direction": "bullish",
                     "neckline": None, "target": None, "start_date": c[-2]["time"], "break_date": c[-1]["time"]}]
        monkeypatch.setattr(pattern_candles, "detect", fake_detect)
        monkeypatch.setattr(pattern_action, "detect", lambda c, atr: [])
        monkeypatch.setattr(pattern_geometry, "detect", lambda c, atr: [])
        monkeypatch.setattr(weekly, "structure_rows", lambda c: [])
        _edge_row("doji", "negative", n=7000, metric=-0.3)
        _edge_row("bull_trap", "edge", horizon=20, n=2000, metric=0.5)
        _edge_row("hammer", "marginal", n=400, metric=-0.2)

        everything = patterns.detect("AAA", candles, view="all")
        assert {r["pattern"] for r in everything["patterns"]} == {"doji", "bull_trap", "hammer"}
        assert everything["hidden"] == 0 and everything["by_verdict"] == {"negative": 1, "edge": 1, "marginal": 1}

        proven = patterns.detect("AAA", candles, view="proven")
        assert [r["pattern"] for r in proven["patterns"]] == ["bull_trap"]
        assert proven["hidden"] == 2 and proven["hidden_by_verdict"] == {"negative": 1, "marginal": 1}
        assert proven["view"] == "proven" and proven["edge_measured"] is True
        # events and direction counts describe what is shown, not what was found
        assert proven["events_by_direction"] == {"bearish": 1}
        assert proven["by_direction"] == {"bearish": 1}

        not_neg = patterns.detect("AAA", candles, view="not_negative")
        assert {r["pattern"] for r in not_neg["patterns"]} == {"bull_trap", "hammer"}
        assert not_neg["hidden_by_verdict"] == {"negative": 1}
        # an unknown view falls back to 'all'
        assert patterns.detect("AAA", candles, view="bogus")["view"] == "all"

    def test_latest_restamps_stored_rows(self) -> None:
        for pat, status in (("doji", "confirmed"), ("double_bottom", "confirmed"), ("hammer", "forming")):
            payload = {"symbol": "AAA", "pattern": pat, "status": status, "quality": 60, "category": "candlestick",
                       "direction": "bullish", "label": pat}
            db.execute("INSERT INTO pattern_hits (date, universe, symbol, pattern, category, status, quality, payload_json, "
                       "created_at) VALUES ('2026-09-06', 'EGX100', 'AAA', ?, 'candlestick', ?, 60, ?, 'x')",
                       (pat, status, json.dumps(payload)))
        _edge_row("doji", "negative")
        _edge_row("double_bottom", "edge", horizon=40)
        out = patterns.latest("EGX100", view="proven")
        assert [r["pattern"] for r in out["rows"]] == ["double_bottom"]
        assert out["rows"][0]["edge_verdict"] == "edge" and out["rows"][0]["edge_horizon"] == 40
        assert out["total"] == 3 and out["hidden"] == 2
        assert out["hidden_by_verdict"] == {"negative": 1, "unmeasured": 1}
        assert patterns.latest("EGX100", view="not_negative")["hidden_by_verdict"] == {"negative": 1}
        assert len(patterns.latest("EGX100")["rows"]) == 3


class TestCatalogVerdicts:
    def test_catalog_lists_survivors_and_negatives(self, monkeypatch) -> None:
        from app.services import scorecard

        monkeypatch.setattr(scorecard, "scorecard", lambda: {"scanners": {}})
        _edge_row("bull_pennant", "edge", horizon=40, n=285, metric=6.3)
        _edge_row("doji", "negative", n=7000, metric=-0.3)
        c = patterns.catalog()
        assert "error" not in c and c["edge_measured"] is True
        assert c["proven"] == ["bull_pennant"] and c["negative"] == ["doji"]
        by = {p["key"]: p for p in c["patterns"]}
        assert by["bull_pennant"]["edge_verdict"] == "edge" and by["bull_pennant"]["proven"] is True
        assert by["bull_pennant"]["egx_stats"]["horizon"] == 40
        assert by["bull_pennant"]["egx_stats"]["verdict_by_horizon"]["40"] == "edge"
        assert by["double_bottom"]["edge_verdict"] == "unmeasured"
        assert c["by_verdict"]["unmeasured"] > 60


class TestChecklistIgnoresNegative:
    def test_negative_shapes_and_events_do_not_count(self, monkeypatch) -> None:
        candles = _bars([20.0 + 0.05 * i for i in range(200)])
        rows = [
            {"pattern": "descending_triangle", "label": "Descending Triangle", "category": "triangle", "status": "confirmed",
             "direction": "bearish", "target": 15.0, "target_pct": -20.0, "neckline": 19.0, "quality": 70,
             "edge_verdict": "negative", "event_headline": True, "timeframe": "1D"},
            {"pattern": "three_black_crows", "label": "Three Black Crows", "category": "candlestick", "status": "confirmed",
             "direction": "bearish", "quality": 60, "edge_verdict": "negative", "event_headline": True, "timeframe": "1D"},
        ]
        monkeypatch.setattr(patterns, "detect", lambda sym, c=None, view="all": {"patterns": rows})
        out = checklist.checklist("AAA", candles=candles, regime_state="bull")
        assert "error" not in out
        pil = {p["key"]: p for p in out["pillars"]}
        # the confirmed bearish shape would have FAILED the pillar; as a negative-record type it is ignored
        assert pil["patterns"]["status"] == "warn"
        assert "Ignored 1 shape" in pil["patterns"]["text"] and "Descending Triangle" in pil["patterns"]["text"]
        assert pil["patterns"]["ignored_negative"] == ["descending_triangle"]
        assert pil["price_action"]["status"] == "warn" and "No decisive" in pil["price_action"]["text"]
        # the same rows with an edge record DO count
        for r in rows:
            r["edge_verdict"] = "edge"
        out2 = checklist.checklist("AAA", candles=candles, regime_state="bull")
        pil2 = {p["key"]: p for p in out2["pillars"]}
        assert pil2["patterns"]["status"] == "fail" and pil2["price_action"]["status"] == "fail"
