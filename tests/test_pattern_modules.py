"""Candlestick, trendline-shape and price-action detectors — synthetic, offline."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_pm_"), "t.db")

import pytest  # noqa: E402

from app.services import pattern_action as PA  # noqa: E402
from app.services import pattern_candles as PC  # noqa: E402
from app.services import pattern_common as CM  # noqa: E402
from app.services import pattern_geometry as PG  # noqa: E402
from app.services import patterns  # noqa: E402
from app.services.pattern_catalog import CATALOG, CATEGORIES, enrich  # noqa: E402


def _bars(rows: list[tuple[float, float, float, float]], vols: list[float] | None = None) -> list[dict]:
    """rows = (open, high, low, close)."""
    day = datetime(2026, 1, 5)
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append({"time": day.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c,
                    "volume": vols[i] if vols else 100_000})
        day += timedelta(days=1)
    return out


def _flat(n: int, px: float = 100.0, body: float = 0.6, wick: float = 0.3) -> list[tuple[float, float, float, float]]:
    out = []
    for i in range(n):
        up = i % 2 == 0
        o, c = (px - body / 2, px + body / 2) if up else (px + body / 2, px - body / 2)
        out.append((o, max(o, c) + wick, min(o, c) - wick, c))
    return out


def _decline(n: int, start: float, step: float) -> list[tuple[float, float, float, float]]:
    out = []
    px = start
    for _ in range(n):
        o = px
        c = px - step
        out.append((o, o + 0.2, c - 0.2, c))
        px = c
    return out


def _advance(n: int, start: float, step: float) -> list[tuple[float, float, float, float]]:
    return [(o, h, l, c) for (o, h, l, c) in ((px, px + step + 0.2, px - 0.2, px + step) for px in
                                              [start + i * step for i in range(n)])]


class TestCatalog:
    def test_every_user_pattern_is_present_with_tiers(self) -> None:
        wanted = ["head_shoulders", "inverse_head_shoulders", "double_top", "double_bottom", "triple_top",
                  "triple_bottom", "rounding_top", "rounding_bottom", "cup_handle", "inverse_cup_handle",
                  "diamond_top", "diamond_bottom", "ascending_triangle", "descending_triangle",
                  "symmetrical_triangle", "expanding_triangle", "ascending_broadening_triangle",
                  "descending_broadening_triangle", "bull_flag", "bear_flag", "bull_pennant", "bear_pennant",
                  "rectangle", "bullish_rectangle", "bearish_rectangle", "rising_wedge", "falling_wedge",
                  "broadening_wedge", "ascending_channel", "descending_channel", "horizontal_channel",
                  "bullish_channel", "bearish_channel", "doji", "dragonfly_doji", "gravestone_doji", "hammer",
                  "inverted_hammer", "hanging_man", "shooting_star", "bullish_engulfing", "bearish_engulfing",
                  "piercing_pattern", "dark_cloud_cover", "morning_star", "evening_star", "three_white_soldiers",
                  "three_black_crows", "harami", "inverted_harami", "tweezer_top", "tweezer_bottom",
                  "three_inside_up", "three_inside_down", "three_outside_up", "three_outside_down", "marubozu",
                  "spinning_top", "inside_bar", "outside_bar", "breakout", "false_breakout", "retest",
                  "failed_retest", "pullback", "throwback", "spring", "upthrust", "bull_trap", "bear_trap",
                  "higher_high_higher_low", "lower_high_lower_low", "change_of_character", "break_of_structure"]
        missing = [k for k in wanted if k not in CATALOG]
        assert not missing, missing
        for k, p in CATALOG.items():
            assert p["category"] in CATEGORIES
            assert p["direction"] in ("bullish", "bearish", "neutral")
            assert p["reliability"] in ("high", "medium", "low")
            assert p["frequency"] in ("common", "uncommon", "rare")
            assert p["kind"] in ("reversal", "continuation", "indecision", "structure")

    def test_enrich_keeps_detector_direction(self) -> None:
        row = enrich({"pattern": "symmetrical_triangle", "direction": "bullish"})
        assert row["direction"] == "bullish" and row["category"] == "triangle" and row["reliability"] == "medium"
        assert enrich({"pattern": "symmetrical_triangle", "direction": None})["direction"] == "neutral"


class TestCandles:
    def _detect(self, rows):
        c = _bars(rows)
        return {r["pattern"]: r for r in PC.detect(c, CM.atr(c) or 1.0)}

    def test_hammer_after_decline(self) -> None:
        rows = _flat(20) + _decline(8, 100, 1.0)          # down to 92
        rows.append((91.8, 92.1, 88.5, 92.0))              # hammer: tiny body, long lower shadow
        found = self._detect(rows)
        assert "hammer" in found and found["hammer"]["direction"] == "bullish"
        assert found["hammer"]["category"] if "category" in found["hammer"] else True

    def test_shooting_star_after_advance(self) -> None:
        rows = _flat(20) + _advance(8, 100, 1.0)
        top = rows[-1][3]
        rows.append((top, top + 3.5, top - 0.1, top - 0.2))
        found = self._detect(rows)
        assert "shooting_star" in found and found["shooting_star"]["direction"] == "bearish"

    def test_bullish_engulfing_and_three_outside_up(self) -> None:
        rows = _flat(20) + _decline(8, 100, 1.0)          # ends ~92
        rows.append((92.0, 92.2, 91.0, 91.2))              # down candle
        rows.append((91.0, 93.6, 90.9, 93.4))              # engulfs it
        found = self._detect(rows)
        assert "bullish_engulfing" in found
        rows.append((93.4, 94.5, 93.2, 94.3))              # confirmation
        found = self._detect(rows)
        assert "three_outside_up" in found

    def test_morning_star(self) -> None:
        rows = _flat(20) + _decline(8, 100, 1.0)
        rows.append((92.0, 92.2, 89.8, 90.0))              # long down
        rows.append((89.8, 90.1, 89.5, 89.9))              # star
        rows.append((90.0, 92.4, 89.9, 92.2))              # long up into the first body
        found = self._detect(rows)
        assert "morning_star" in found and found["morning_star"]["direction"] == "bullish"

    def test_doji_and_inside_bar(self) -> None:
        rows = _flat(30)
        rows.append((100.0, 101.0, 99.0, 100.02))          # doji, neutral context
        found = self._detect(rows)
        assert "doji" in found and found["doji"]["direction"] == "neutral"
        rows.append((100.0, 100.5, 99.5, 100.2))           # inside the doji's range
        found = self._detect(rows)
        assert "inside_bar" in found
        assert found["inside_bar"]["trigger_up"] == 101.0

    def test_three_black_crows(self) -> None:
        rows = _flat(20) + _advance(6, 100, 1.0)
        top = rows[-1][3]
        for k in range(3):
            o = top - k * 1.5
            rows.append((o, o + 0.1, o - 1.6, o - 1.5))
        found = self._detect(rows)
        assert "three_black_crows" in found

    def test_no_reversal_candle_without_trend(self) -> None:
        rows = _flat(30)
        rows.append((99.8, 100.1, 96.5, 100.0))            # hammer shape but flat context
        found = self._detect(rows)
        assert "hammer" not in found and "hanging_man" not in found


def _line_series(n_pre: int, upper, lower, n: int, noise: float = 0.0):
    """Bars oscillating between two lines upper(i), lower(i) for i in 0..n-1, with a flat lead-in."""
    rows = _flat(n_pre)
    for i in range(n):
        hi, lo = upper(i), lower(i)
        # Zig-zag: touch upper on even 4-bar cycles, lower on odd.
        phase = (i % 8) / 8.0
        if phase < 0.5:
            c = lo + (hi - lo) * (phase * 2)
        else:
            c = hi - (hi - lo) * ((phase - 0.5) * 2)
        o = c - 0.1
        rows.append((o, max(o, c) + 0.15, min(o, c) - 0.15, c))
    return rows


class TestGeometry:
    def _detect(self, rows):
        c = _bars(rows)
        return {r["pattern"]: r for r in PG.detect(c, CM.atr(c) or 1.0)}

    def test_ascending_triangle(self) -> None:
        rows = _line_series(40, lambda i: 110.0, lambda i: 100.0 + i * 0.22, 40)
        found = self._detect(rows)
        assert "ascending_triangle" in found, list(found)
        r = found["ascending_triangle"]
        assert r["direction"] == "bullish" and r["status"] == "forming"
        assert r["neckline"] == pytest.approx(110.0, abs=1.0)

    def test_symmetrical_triangle_then_breakout(self) -> None:
        rows = _line_series(40, lambda i: 110.0 - i * 0.12, lambda i: 100.0 + i * 0.12, 36)
        found = self._detect(rows)
        assert "symmetrical_triangle" in found, list(found)
        rows2 = rows + [(105.0, 109.5, 104.8, 109.2)]        # close above the falling upper line
        found2 = self._detect(rows2)
        assert found2["symmetrical_triangle"]["status"] == "confirmed"
        assert found2["symmetrical_triangle"]["direction"] == "bullish"

    def test_falling_wedge_and_ascending_channel(self) -> None:
        wedge = _line_series(40, lambda i: 110.0 - i * 0.25, lambda i: 100.0 - i * 0.10, 40)
        assert "falling_wedge" in self._detect(wedge), list(self._detect(wedge))
        chan = _line_series(40, lambda i: 110.0 + i * 0.3, lambda i: 100.0 + i * 0.3, 40)
        found = self._detect(chan)
        assert "ascending_channel" in found or "bullish_channel" in found, list(found)

    def test_rectangle_is_labelled_by_prior_trend(self) -> None:
        rows = _flat(20) + _advance(20, 90, 0.8) + _line_series(0, lambda i: 110.0, lambda i: 103.0, 40)
        found = self._detect(rows)
        assert "bullish_rectangle" in found or "rectangle" in found or "horizontal_channel" in found, list(found)

    def test_bull_flag(self) -> None:
        rows = _flat(40) + _advance(8, 100, 1.5)                 # pole: +12 in 8 bars
        top = rows[-1][3]
        for k in range(8):                                       # tight drift down
            c = top - 0.25 * (k + 1)
            rows.append((c + 0.1, c + 0.35, c - 0.35, c))
        found = self._detect(rows)
        assert "bull_flag" in found, list(found)
        r = found["bull_flag"]
        assert r["direction"] == "bullish" and r["target"] > r["neckline"]

    def test_rounding_bottom(self) -> None:
        import math

        rows = _flat(20, 100.0)
        for i in range(80):
            c = 100.0 - 12.0 * math.sin(math.pi * i / 80)
            rows.append((c - 0.1, c + 0.2, c - 0.3, c))
        found = self._detect(rows)
        assert "rounding_bottom" in found, list(found)
        assert found["rounding_bottom"]["direction"] == "bullish"


class TestPriceAction:
    def _detect(self, rows, vols=None):
        c = _bars(rows, vols)
        return {r["pattern"]: r for r in PA.detect(c, CM.atr(c) or 1.0)}

    def test_breakout_with_volume(self) -> None:
        rows = _flat(50)                                    # range ~99.4-100.6
        rows.append((100.5, 103.2, 100.4, 103.0))           # close above 20-bar high
        vols = [100_000] * 50 + [350_000]
        found = self._detect(rows, vols)
        assert "breakout" in found and found["breakout"]["direction"] == "bullish"
        assert found["breakout"]["break_volume_ratio"] > 3

    def test_false_breakout_is_a_bull_trap(self) -> None:
        rows = _flat(50)
        rows.append((100.5, 103.2, 100.4, 103.0))           # break up
        rows.append((102.8, 102.9, 99.6, 99.9))             # back inside the range next day
        found = self._detect(rows)
        assert "false_breakout" in found and "bull_trap" in found
        assert found["bull_trap"]["direction"] == "bearish"

    def test_spring(self) -> None:
        rows = _flat(50)
        low = min(r[2] for r in rows[-20:])
        rows.append((99.8, 100.2, low - 1.0, 100.1))        # pokes under support, closes back inside and up
        found = self._detect(rows)
        assert "spring" in found and found["spring"]["direction"] == "bullish"

    def test_pullback_in_uptrend(self) -> None:
        rows = _flat(10) + _advance(60, 80, 0.5)            # steady uptrend, SMA20 > SMA50
        top = rows[-1][3]
        for k in range(3):                                  # three down closes toward SMA20
            c = top - 1.2 * (k + 1)
            rows.append((c + 0.3, c + 0.5, c - 0.2, c))
        found = self._detect(rows)
        assert "pullback" in found, list(found)
        assert found["pullback"]["down_sessions"] == 3

    def test_structure_hh_hl_and_bos(self) -> None:
        rows = _flat(20)
        # Up-trending zig-zag: swings 100→106→102→108→104→110 ...
        path = [100, 106, 102, 108, 104, 110, 106, 112]
        for a, b in zip(path, path[1:]):
            for k in range(1, 6):
                c = a + (b - a) * k / 5
                rows.append((c - 0.1, c + 0.2, c - 0.2, c))
        found = self._detect(rows)
        assert "higher_high_higher_low" in found, list(found)
        rows.append((112.0, 114.5, 111.9, 114.3))           # close above the last swing high → BOS
        found = self._detect(rows)
        assert "break_of_structure" in found and found["break_of_structure"]["direction"] == "bullish"


class TestAggregation:
    def test_detect_enriches_and_counts_categories(self) -> None:
        rows = _flat(70)
        rows.append((100.5, 101.9, 100.4, 101.6))   # modest break: target not yet reached
        res = patterns.detect("AGG", _bars(rows))
        assert "error" not in res
        assert res["patterns"], "expected at least the breakout"
        for r in res["patterns"]:
            assert r["category"] in CATEGORIES and r["reliability"] in ("high", "medium", "low")
            assert r["symbol"] == "AGG"
        assert sum(res["by_category"].values()) == len(res["patterns"])


class TestShark32:
    def test_two_consecutive_inside_bars(self) -> None:
        rows = _flat(20) + _advance(8, 100, 1.0)           # uptrend into the coil
        top = rows[-1][3]
        rows.append((top - 0.5, top + 2.0, top - 2.0, top + 0.3))     # bar 1: wide
        rows.append((top, top + 1.2, top - 1.2, top + 0.2))           # inside bar 1
        rows.append((top + 0.1, top + 0.6, top - 0.6, top + 0.1))     # inside bar 2
        c = _bars(rows)
        found = {r["pattern"]: r for r in PC.detect(c, CM.atr(c) or 1.0)}
        assert "shark_32" in found, list(found)
        r = found["shark_32"]
        assert r["direction"] == "bullish"                     # continuation of the prior advance
        assert r["trigger_up"] == pytest.approx(top + 2.0) and r["trigger_down"] == pytest.approx(top - 2.0)
        assert r["target"] == pytest.approx(top + 2.0 + 4.0)    # height 4.0 above the upper trigger
        assert "inside_bar" in found                             # the plain inside bar still fires too

    def test_not_shark_when_second_bar_breaks_out(self) -> None:
        rows = _flat(30)
        rows.append((99.8, 101.5, 98.5, 100.2))
        rows.append((100.0, 100.9, 99.1, 100.3))     # inside
        rows.append((100.2, 102.0, 99.8, 101.8))     # breaks the mother bar's high — not inside
        c = _bars(rows)
        found = {r["pattern"] for r in PC.detect(c, CM.atr(c) or 1.0)}
        assert "shark_32" not in found
