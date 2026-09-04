"""Event clustering: one market event described by several pattern rows must be
counted once — in the API, the panel and the checklist."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_ev_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import checklist, patterns  # noqa: E402
from app.services.pattern_catalog import enrich  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


def _bars(rows, vols=None):
    day = datetime(2026, 1, 5)
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c,
                    "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _flat(n, px=100.0, body=0.6, wick=0.3):
    out = []
    for i in range(n):
        up = i % 2 == 0
        o, c = (px - body / 2, px + body / 2) if up else (px + body / 2, px - body / 2)
        out.append((o, max(o, c) + wick, min(o, c) - wick, c))
    return out


def _bull_trap_candles():
    rows = _flat(70)
    rows.append((100.5, 103.2, 100.4, 103.0))   # break up
    rows.append((102.8, 102.9, 99.6, 99.9))     # back inside next day → false breakout + bull trap
    return _bars(rows)


def _row(pattern, direction, *, target=None, break_date=None, start_date=None, quality=50,
         status="confirmed", neckline=None, dist=None):
    return enrich({"pattern": pattern, "direction": direction, "status": status, "target": target,
                   "break_date": break_date, "start_date": start_date, "quality": quality,
                   "neckline": neckline, "distance_to_neckline_pct": dist})


CANDLES = _bars(_flat(12))  # 12 sessions: 2026-01-05 … 2026-01-20
AS_OF = CANDLES[-1]["time"]


class TestClusterRules:
    def test_known_synonym_pairs_cluster(self) -> None:
        rows = [_row("false_breakout", "bearish", target=95, break_date=AS_OF, start_date=AS_OF, quality=55),
                _row("bull_trap", "bearish", target=95, break_date=AS_OF, start_date=AS_OF, quality=60),
                _row("higher_high_higher_low", "bullish", start_date=CANDLES[0]["time"], quality=55),
                _row("break_of_structure", "bullish", target=110, break_date=AS_OF, start_date=CANDLES[0]["time"], quality=60)]
        events = patterns.cluster_events(rows, atr=1.0, candles=CANDLES)
        assert len(events) == 2
        bear = next(e for e in events if e["direction"] == "bearish")
        assert bear["label"] == "Bull Trap" and bear["also_seen_as"] == ["False Breakout"] and bear["framings"] == 2
        bull = next(e for e in events if e["direction"] == "bullish")
        assert bull["label"] == "Break of Structure (BOS)" and bull["also_seen_as"] == ["Higher High / Higher Low"]

    def test_same_target_adjacent_break_clusters(self) -> None:
        d1, d0 = CANDLES[-1]["time"], CANDLES[-2]["time"]
        rows = [_row("upthrust", "bearish", target=95.0, break_date=d0, start_date=d0, quality=59),
                _row("bull_trap", "bearish", target=95.1, break_date=d1, start_date=d0, quality=60)]
        events = patterns.cluster_events(rows, atr=1.0, candles=CANDLES)
        assert len(events) == 1 and events[0]["framings"] == 2

    def test_opposite_directions_never_cluster(self) -> None:
        rows = [_row("breakout", "bullish", target=95.0, break_date=AS_OF, start_date=AS_OF),
                _row("upthrust", "bearish", target=95.0, break_date=AS_OF, start_date=AS_OF)]
        assert len(patterns.cluster_events(rows, atr=1.0, candles=CANDLES)) == 2

    def test_far_targets_or_distant_breaks_stay_separate(self) -> None:
        rows = [_row("upthrust", "bearish", target=95.0, break_date=AS_OF, start_date=AS_OF),
                _row("bearish_engulfing", "bearish", target=98.0, break_date=AS_OF, start_date=AS_OF),
                _row("failed_retest", "bearish", target=95.0, break_date=CANDLES[0]["time"], start_date=CANDLES[0]["time"])]
        assert len(patterns.cluster_events(rows, atr=1.0, candles=CANDLES)) == 3

    def test_neutral_rows_never_cluster(self) -> None:
        rows = [_row("spinning_top", "neutral", neckline=100, break_date=AS_OF, start_date=AS_OF),
                _row("doji", "neutral", neckline=100, break_date=AS_OF, start_date=AS_OF)]
        assert len(patterns.cluster_events(rows, atr=1.0, candles=CANDLES)) == 2

    def test_headline_is_best_row_and_members_are_marked(self) -> None:
        rows = [_row("false_breakout", "bearish", target=95, break_date=AS_OF, start_date=AS_OF, quality=55),
                _row("bull_trap", "bearish", target=95, break_date=AS_OF, start_date=AS_OF, quality=60)]
        patterns.cluster_events(rows, atr=1.0, candles=CANDLES)
        head = next(r for r in rows if r["event_headline"])
        other = next(r for r in rows if not r["event_headline"])
        assert head["pattern"] == "bull_trap" and other["pattern"] == "false_breakout"
        assert head["event_id"] == other["event_id"]
        assert other["also_seen_as"] == []

    def test_events_ordered_newest_first(self) -> None:
        rows = [_row("double_bottom", "bullish", target=120, break_date=CANDLES[3]["time"], start_date=CANDLES[0]["time"], quality=75),
                _row("bull_trap", "bearish", target=95, break_date=AS_OF, start_date=CANDLES[-2]["time"], quality=60)]
        events = patterns.cluster_events(rows, atr=1.0, candles=CANDLES)
        assert [e["pattern"] for e in events] == ["bull_trap", "double_bottom"]


class TestHorizon:
    @pytest.mark.parametrize("age,bucket", [(0, "today"), (1, "today"), (2, "days"), (7, "days"),
                                            (8, "weeks"), (43, "weeks"), (60, "weeks"), (61, "months"), (100, "months"),
                                            (None, "unknown")])
    def test_buckets(self, age, bucket) -> None:
        assert patterns.horizon_of(age) == bucket

    def test_age_from_start_date(self) -> None:
        rows = [_row("double_bottom", "bullish", target=120, start_date="2026-01-05")]
        patterns.cluster_events(rows, atr=1.0, candles=CANDLES)
        assert rows[0]["age_days"] == (datetime(2026, 1, 20) - datetime(2026, 1, 5)).days
        assert rows[0]["horizon"] == "weeks"


class TestDecisiveLevel:
    def test_nearest_trigger_wins_and_collects_labels(self) -> None:
        rows = [_row("bull_trap", "bearish", neckline=5.91, dist=0.17),
                _row("false_breakout", "bearish", neckline=5.91, dist=0.17),
                _row("break_of_structure", "bullish", neckline=5.91, dist=0.17),
                _row("upthrust", "bearish", neckline=6.12, dist=3.73),
                _row("double_bottom", "bullish", neckline=5.78, dist=-2.03)]
        dl = patterns.decisive_level(rows, atr=0.2)
        assert dl["level"] == 5.91
        assert dl["labels"] == ["Break of Structure (BOS)", "Bull Trap", "False Breakout"]
        assert dl["directions"] == ["bearish", "bullish"]

    def test_none_without_levels(self) -> None:
        assert patterns.decisive_level([_row("higher_high_higher_low", "bullish")], atr=1.0) is None


class TestEndToEnd:
    def test_detect_counts_one_bearish_event_for_a_trap(self) -> None:
        res = patterns.detect("TST", _bull_trap_candles())
        rows = res["patterns"]
        keys = {r["pattern"] for r in rows}
        assert {"false_breakout", "bull_trap"} <= keys
        fb = next(r for r in rows if r["pattern"] == "false_breakout")
        bt = next(r for r in rows if r["pattern"] == "bull_trap")
        assert fb["event_id"] == bt["event_id"]
        assert bt["event_headline"] and not fb["event_headline"]
        assert "False Breakout" in bt["also_seen_as"]
        assert res["distinct_events"] < len(rows)
        assert res["events_by_direction"].get("bearish", 0) == 1
        assert res["decisive_level"] is not None
        for r in rows:
            assert "event_id" in r and "horizon" in r and "age_days" in r

    def test_checklist_names_the_event_once(self, monkeypatch) -> None:
        from app.services import leaders, market

        monkeypatch.setattr(leaders, "daily_candles", lambda sym, range_="1y": _bars(_flat(150)[:-2] + list(_bull_trap_candles_tail())))
        monkeypatch.setattr(market, "median_daily_value", lambda sym, days=20: 50_000_000.0)
        res = checklist.checklist("TST")
        pa = next(p for p in res["pillars"] if p["key"] == "price_action")
        assert pa["status"] == "fail"
        assert "1 event" in pa["text"]
        assert "Bull Trap (also seen as False Breakout)" in pa["text"]
        # The event is named once, not once per framing.
        assert pa["text"].count("False Breakout") == 1


def _bull_trap_candles_tail():
    return [(100.5, 103.2, 100.4, 103.0), (102.8, 102.9, 99.6, 99.9)]
