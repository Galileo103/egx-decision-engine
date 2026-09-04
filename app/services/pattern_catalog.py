"""Catalog of every chart, candlestick and price-action pattern the app knows.

One entry per pattern: category (as the user groups them), direction, kind,
a reliability tier and a frequency tier, plus a one-line description. The
tiers are QUALITATIVE and start from the classic Western references
(Bulkowski's *Encyclopedia of Chart Patterns* rankings, Nison's candlestick
work, Wyckoff/price-action practice). They are a starting prior, not EGX
statistics — the Signal Scorecard grades every CONFIRMED detection against
what the stock actually did next, so Egypt-specific hit rates accumulate per
pattern over time and are shown next to these tiers.

``detected`` marks patterns the scanner currently implements.
"""
from __future__ import annotations

from typing import Any

CATEGORIES: dict[str, str] = {
    "reversal": "Reversal patterns",
    "triangle": "Triangle patterns",
    "continuation": "Continuation patterns",
    "wedge": "Wedge patterns",
    "channel": "Channel patterns",
    "candlestick": "Candlestick patterns",
    "price_action": "Price-action patterns",
}

RELIABILITY_ORDER = {"high": 3, "medium": 2, "low": 1}


def _p(key: str, label: str, category: str, direction: str, kind: str, reliability: str,
       frequency: str, note: str, detected: bool = True) -> dict[str, Any]:
    return {
        "key": key, "label": label, "category": category,
        "category_label": CATEGORIES[category], "direction": direction, "kind": kind,
        "reliability": reliability, "frequency": frequency, "note": note, "detected": detected,
    }


CATALOG: dict[str, dict[str, Any]] = {p["key"]: p for p in [
    # ── Reversal ────────────────────────────────────────────────────────────
    _p("head_shoulders", "Head & Shoulders", "reversal", "bearish", "reversal", "high", "common",
       "Three peaks, the middle highest; neckline under the two dips. Break below the neckline confirms."),
    _p("inverse_head_shoulders", "Inverse Head & Shoulders", "reversal", "bullish", "reversal", "high", "common",
       "Three troughs, the middle lowest; neckline over the two rallies. Break above confirms."),
    _p("double_top", "Double Top", "reversal", "bearish", "reversal", "medium", "common",
       "Two highs at about the same level with a dip between; confirmed below the dip."),
    _p("double_bottom", "Double Bottom", "reversal", "bullish", "reversal", "medium", "common",
       "Two lows at about the same level with a bounce between; confirmed above the bounce."),
    _p("triple_top", "Triple Top", "reversal", "bearish", "reversal", "medium", "uncommon",
       "Three equal highs; confirmed below the lowest dip between them."),
    _p("triple_bottom", "Triple Bottom", "reversal", "bullish", "reversal", "high", "uncommon",
       "Three equal lows; confirmed above the highest bounce between them."),
    _p("rounding_top", "Rounding Top", "reversal", "bearish", "reversal", "medium", "uncommon",
       "A slow dome: gradual rise, plateau, gradual fall. Confirmed below the left rim."),
    _p("rounding_bottom", "Rounding Bottom", "reversal", "bullish", "reversal", "high", "uncommon",
       "A slow bowl over months; confirmed above the rim. One of the more dependable long bases."),
    _p("cup_handle", "Cup & Handle", "reversal", "bullish", "reversal", "medium", "uncommon",
       "Rounded bowl back to the old high, then a small shallow pullback (handle); buy the rim break."),
    _p("inverse_cup_handle", "Inverse Cup & Handle", "reversal", "bearish", "reversal", "medium", "rare",
       "Upside-down cup: rounded top then a small bounce (handle); confirmed below the rim."),
    _p("diamond_top", "Diamond Top", "reversal", "bearish", "reversal", "medium", "rare",
       "Swings widen then narrow after an advance; confirmed below the lower right edge."),
    _p("diamond_bottom", "Diamond Bottom", "reversal", "bullish", "reversal", "medium", "rare",
       "Swings widen then narrow after a decline; confirmed above the upper right edge."),
    # ── Triangles ───────────────────────────────────────────────────────────
    _p("ascending_triangle", "Ascending Triangle", "triangle", "bullish", "continuation", "medium", "common",
       "Flat top, rising lows. Buyers step up each dip; upside break is the expected resolution."),
    _p("descending_triangle", "Descending Triangle", "triangle", "bearish", "continuation", "medium", "common",
       "Flat bottom, falling highs. Sellers press each rally; downside break expected."),
    _p("symmetrical_triangle", "Symmetrical Triangle", "triangle", "neutral", "continuation", "medium", "common",
       "Converging highs and lows. Direction decided by the break — usually with the prior trend."),
    _p("expanding_triangle", "Expanding Triangle", "triangle", "neutral", "reversal", "low", "rare",
       "Highs rising AND lows falling — volatility expanding. Erratic; often a top."),
    _p("ascending_broadening_triangle", "Ascending Broadening Triangle", "triangle", "bearish", "reversal", "low", "rare",
       "Flat lows, rising highs that get wider. Tends to break down."),
    _p("descending_broadening_triangle", "Descending Broadening Triangle", "triangle", "bullish", "reversal", "low", "rare",
       "Flat highs, falling lows that get wider. Tends to break up."),
    # ── Continuation ────────────────────────────────────────────────────────
    _p("bull_flag", "Bull Flag", "continuation", "bullish", "continuation", "high", "common",
       "Sharp rally (pole) then a small, tight drift down. Break above the flag resumes the rally."),
    _p("bear_flag", "Bear Flag", "continuation", "bearish", "continuation", "high", "common",
       "Sharp drop (pole) then a small drift up. Break below the flag resumes the fall."),
    _p("bull_pennant", "Bull Pennant", "continuation", "bullish", "continuation", "medium", "uncommon",
       "Pole then a tiny converging triangle. Resolves upward."),
    _p("bear_pennant", "Bear Pennant", "continuation", "bearish", "continuation", "medium", "uncommon",
       "Pole down then a tiny converging triangle. Resolves downward."),
    _p("rectangle", "Rectangle", "continuation", "neutral", "continuation", "medium", "common",
       "Sideways box between flat support and resistance. Trade the break."),
    _p("bullish_rectangle", "Bullish Rectangle", "continuation", "bullish", "continuation", "medium", "common",
       "A rectangle inside an uptrend — a pause; upside break expected."),
    _p("bearish_rectangle", "Bearish Rectangle", "continuation", "bearish", "continuation", "medium", "common",
       "A rectangle inside a downtrend; downside break expected."),
    # ── Wedges (also listed by the user under continuation) ─────────────────
    _p("rising_wedge", "Rising Wedge", "wedge", "bearish", "reversal", "medium", "common",
       "Both lines rise but converge — buyers tiring. Usually breaks down."),
    _p("falling_wedge", "Falling Wedge", "wedge", "bullish", "reversal", "medium", "common",
       "Both lines fall but converge — sellers tiring. Usually breaks up."),
    _p("broadening_wedge", "Broadening Wedge", "wedge", "neutral", "reversal", "low", "rare",
       "Both lines slope the same way but diverge. Unstable; often resolves against the slope."),
    # ── Channels ────────────────────────────────────────────────────────────
    _p("ascending_channel", "Ascending Channel", "channel", "bullish", "continuation", "medium", "common",
       "Parallel rising lines. Buy near the lower line in an uptrend; a break below ends it."),
    _p("descending_channel", "Descending Channel", "channel", "bearish", "continuation", "medium", "common",
       "Parallel falling lines. A break above the upper line is the reversal to watch."),
    _p("horizontal_channel", "Horizontal Channel", "channel", "neutral", "continuation", "medium", "common",
       "Flat parallel lines — the same shape as a rectangle, read as a range to trade."),
    _p("bullish_channel", "Bullish Channel", "channel", "bullish", "continuation", "medium", "common",
       "An ascending channel with price holding its upper half — strong trend."),
    _p("bearish_channel", "Bearish Channel", "channel", "bearish", "continuation", "medium", "common",
       "A descending channel with price pinned in its lower half — weak trend."),
    # ── Candlesticks (single/double/triple bar, last completed session) ─────
    _p("doji", "Doji", "candlestick", "neutral", "indecision", "low", "common",
       "Open ≈ close. Indecision; meaningful only after a strong move."),
    _p("dragonfly_doji", "Dragonfly Doji", "candlestick", "bullish", "reversal", "medium", "uncommon",
       "Doji with a long lower shadow: sellers pushed down, buyers recovered everything."),
    _p("gravestone_doji", "Gravestone Doji", "candlestick", "bearish", "reversal", "medium", "uncommon",
       "Doji with a long upper shadow: buyers pushed up, sellers took it all back."),
    _p("hammer", "Hammer", "candlestick", "bullish", "reversal", "medium", "common",
       "Small body at the top, lower shadow ≥ 2× body, after a decline."),
    _p("inverted_hammer", "Inverted Hammer", "candlestick", "bullish", "reversal", "low", "common",
       "Small body at the bottom, long upper shadow, after a decline. Needs next-day confirmation."),
    _p("hanging_man", "Hanging Man", "candlestick", "bearish", "reversal", "low", "common",
       "Hammer shape after an advance. Needs next-day confirmation."),
    _p("shooting_star", "Shooting Star", "candlestick", "bearish", "reversal", "medium", "common",
       "Small body at the bottom, long upper shadow, after an advance."),
    _p("bullish_engulfing", "Bullish Engulfing", "candlestick", "bullish", "reversal", "high", "common",
       "Down candle fully swallowed by the next up candle's body, after a decline."),
    _p("bearish_engulfing", "Bearish Engulfing", "candlestick", "bearish", "reversal", "high", "common",
       "Up candle fully swallowed by the next down candle's body, after an advance."),
    _p("piercing_pattern", "Piercing Pattern", "candlestick", "bullish", "reversal", "medium", "uncommon",
       "Down candle, then an up candle opening lower and closing above its midpoint."),
    _p("dark_cloud_cover", "Dark Cloud Cover", "candlestick", "bearish", "reversal", "medium", "uncommon",
       "Up candle, then a down candle opening higher and closing below its midpoint."),
    _p("morning_star", "Morning Star", "candlestick", "bullish", "reversal", "high", "uncommon",
       "Long down candle, small-bodied pause, long up candle closing into the first body."),
    _p("evening_star", "Evening Star", "candlestick", "bearish", "reversal", "high", "uncommon",
       "Long up candle, small-bodied pause, long down candle closing into the first body."),
    _p("three_white_soldiers", "Three White Soldiers", "candlestick", "bullish", "reversal", "high", "uncommon",
       "Three consecutive long up candles, each closing higher, small upper shadows."),
    _p("three_black_crows", "Three Black Crows", "candlestick", "bearish", "reversal", "high", "uncommon",
       "Three consecutive long down candles, each closing lower."),
    _p("harami", "Harami", "candlestick", "neutral", "reversal", "low", "common",
       "Small candle inside the previous large body. Bullish after a decline, bearish after an advance."),
    _p("inverted_harami", "Inverted Harami", "candlestick", "neutral", "continuation", "low", "common",
       "Large candle engulfs a small prior body but does NOT reverse it — usually continuation."),
    _p("tweezer_top", "Tweezer Top", "candlestick", "bearish", "reversal", "low", "common",
       "Two candles with matching highs after an advance."),
    _p("tweezer_bottom", "Tweezer Bottom", "candlestick", "bullish", "reversal", "low", "common",
       "Two candles with matching lows after a decline."),
    _p("three_inside_up", "Three Inside Up", "candlestick", "bullish", "reversal", "medium", "uncommon",
       "Bullish harami plus a third candle closing above the first candle's open."),
    _p("three_inside_down", "Three Inside Down", "candlestick", "bearish", "reversal", "medium", "uncommon",
       "Bearish harami plus a third candle closing below the first candle's open."),
    _p("three_outside_up", "Three Outside Up", "candlestick", "bullish", "reversal", "medium", "uncommon",
       "Bullish engulfing plus a third candle closing higher."),
    _p("three_outside_down", "Three Outside Down", "candlestick", "bearish", "reversal", "medium", "uncommon",
       "Bearish engulfing plus a third candle closing lower."),
    _p("marubozu", "Marubozu", "candlestick", "neutral", "continuation", "medium", "uncommon",
       "Full-range body, no shadows. Bullish if up, bearish if down — one-sided conviction."),
    _p("spinning_top", "Spinning Top", "candlestick", "neutral", "indecision", "low", "common",
       "Small body, long shadows both sides. Indecision."),
    _p("inside_bar", "Inside Bar", "candlestick", "neutral", "continuation", "low", "common",
       "Whole range inside the prior bar's range. Coil; trade the break of the mother bar."),
    _p("outside_bar", "Outside Bar", "candlestick", "neutral", "reversal", "medium", "common",
       "Range engulfs the prior bar's range. Direction of the close carries the message."),
    _p("shark_32", "Shark-32", "candlestick", "neutral", "continuation", "medium", "common",
       "Two consecutive inside bars over three sessions (lower highs, higher lows). A coil that continues "
       "the prior trend about 60% of the time (Bulkowski). Enter on a close outside the first bar's range; "
       "target = the pattern's height."),
    # ── Price action ────────────────────────────────────────────────────────
    _p("breakout", "Breakout", "price_action", "neutral", "continuation", "medium", "common",
       "Close beyond the prior 20-session high (bullish) or low (bearish). Volume decides its worth."),
    _p("false_breakout", "False Breakout", "price_action", "neutral", "reversal", "medium", "common",
       "A breakout that closes back inside the range within 3 sessions — trapped traders."),
    _p("retest", "Retest", "price_action", "neutral", "continuation", "medium", "common",
       "After a breakout, price returns to the broken level and holds it."),
    _p("failed_retest", "Failed Retest", "price_action", "neutral", "reversal", "medium", "uncommon",
       "Price returns to the broken level and closes back through it — the breakout has failed."),
    _p("pullback", "Pullback", "price_action", "bullish", "continuation", "medium", "common",
       "In an uptrend, 2-5 down sessions into the 20-day average — the classic buy-the-dip spot."),
    _p("throwback", "Throwback", "price_action", "bullish", "continuation", "medium", "common",
       "After an upside breakout, a return to the breakout level that holds."),
    _p("spring", "Spring", "price_action", "bullish", "reversal", "medium", "uncommon",
       "Wyckoff: a dip under range support that snaps back inside — a shakeout of weak holders."),
    _p("upthrust", "Upthrust", "price_action", "bearish", "reversal", "medium", "uncommon",
       "Wyckoff: a poke above range resistance that falls back inside — distribution."),
    _p("bull_trap", "Bull Trap", "price_action", "bearish", "reversal", "medium", "common",
       "Upside breakout that fails and reverses — longs trapped above."),
    _p("bear_trap", "Bear Trap", "price_action", "bullish", "reversal", "medium", "common",
       "Downside breakout that fails and reverses — shorts/sellers trapped below."),
    _p("higher_high_higher_low", "Higher High / Higher Low", "price_action", "bullish", "structure", "medium", "common",
       "Swing structure of an uptrend: each high and each low above the last."),
    _p("lower_high_lower_low", "Lower High / Lower Low", "price_action", "bearish", "structure", "medium", "common",
       "Swing structure of a downtrend: each high and each low below the last."),
    _p("change_of_character", "Change of Character (CHoCH)", "price_action", "neutral", "reversal", "medium", "uncommon",
       "First close through the last swing AGAINST the trend — the structure has changed."),
    _p("break_of_structure", "Break of Structure (BOS)", "price_action", "neutral", "continuation", "medium", "common",
       "Close through the last swing WITH the trend — the trend re-asserts itself."),
]}


def info(key: str) -> dict[str, Any]:
    """Catalog entry for a pattern key (safe default for unknown keys)."""
    return CATALOG.get(key) or {
        "key": key, "label": key.replace("_", " ").title(), "category": "reversal",
        "category_label": CATEGORIES["reversal"], "direction": "neutral", "kind": "reversal",
        "reliability": "low", "frequency": "uncommon", "note": "", "detected": True,
    }


def enrich(row: dict[str, Any]) -> dict[str, Any]:
    """Attach catalog metadata to a detection row (in place) and return it."""
    meta = info(str(row.get("pattern")))
    row.setdefault("label", meta["label"])
    row["category"] = meta["category"]
    row["category_label"] = meta["category_label"]
    # Some patterns are direction-neutral in the catalog but the detection
    # itself knows which way it broke; keep the detector's direction if set.
    row["direction"] = row.get("direction") or meta["direction"]
    row["kind"] = meta["kind"]
    row["reliability"] = meta["reliability"]
    row["frequency"] = meta["frequency"]
    row["note"] = meta["note"]
    return row


def catalog(with_stats: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """Whole catalog as a list, optionally merged with Scorecard stats per key
    (stats keyed by ``pattern_<key>`` scanner names)."""
    out = []
    for key, meta in CATALOG.items():
        row = dict(meta)
        if with_stats:
            row["egx_stats"] = with_stats.get(f"pattern_{key}")
        out.append(row)
    return out
