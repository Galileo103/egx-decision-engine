"""Candlestick patterns on the last completed daily bar(s).

Definitions follow Nison's conventions, scaled to the stock: a "long" body is
>= 1.0x the average body of the prior 10 bars, a "small" body <= 0.35x, a
"doji" body <= 10% of the bar's range. Reversal candles need trend context
(net move over the prior 8 sessions) or they are just noise.
"""
from __future__ import annotations

from typing import Optional

from app.services.pattern_common import f, make_row, point, sma, trend_before, vol_ratio

_TREND_PCT = 3.0  # min prior move (%) for a reversal candle to count


def _bar(c: dict) -> Optional[dict]:
    o, h, l, cl = f(c.get("open")), f(c.get("high")), f(c.get("low")), f(c.get("close"))
    if None in (o, h, l, cl) or h < l:
        return None
    body = abs(cl - o)
    rng = h - l
    return {
        "o": o, "h": h, "l": l, "c": cl, "body": body, "range": rng,
        "up": cl > o, "down": cl < o,
        "upper": h - max(o, cl), "lower": min(o, cl) - l,
        "mid": (o + cl) / 2.0,
    }


def detect(candles: list[dict], atr: float) -> list[dict]:
    n = len(candles)
    if n < 25 or not atr:
        return []
    bars = [_bar(c) for c in candles]
    if any(b is None for b in bars[-4:]):
        return []
    closes = [float(c["close"]) for c in candles]
    b1, b2, b3 = bars[-1], bars[-2], bars[-3]           # b1 = last completed bar
    assert b1 and b2 and b3
    avg_body = sma([b["body"] for b in bars[-11:-1] if b], 10) or (atr * 0.4)
    trend = trend_before(closes, n - 2, 8) or 0.0         # move INTO the pattern
    after_decline = trend <= -_TREND_PCT
    after_advance = trend >= _TREND_PCT
    i1, i2, i3 = n - 1, n - 2, n - 3
    vr = vol_ratio(candles, i1)
    out: list[dict] = []

    def long_(b: dict) -> bool:
        return b["body"] >= 1.0 * avg_body

    def small(b: dict) -> bool:
        return b["body"] <= 0.35 * avg_body

    def doji(b: dict) -> bool:
        return b["range"] > 0 and b["body"] <= 0.10 * b["range"]

    def q(base: int, direction: str) -> int:
        s = base
        if vr and vr > 1.3:
            s += 10
        if (direction == "bullish" and after_decline) or (direction == "bearish" and after_advance):
            s += 10
        return min(100, s)

    def add(name: str, direction: str, base: int, level: float, stop: Optional[float], target: Optional[float],
            pts: list[dict], extra: Optional[dict] = None) -> None:
        out.append(make_row(name, direction, "confirmed", candles, level=level, target=target,
                            stop_hint=stop, points=pts, quality=q(base, direction), break_index=i1,
                            extra={"trend_into_pct": round(trend, 2), **(extra or {})}))

    rng1 = b1["range"] or atr
    # ── single-bar ─────────────────────────────────────────────────────────
    if doji(b1):
        if b1["lower"] >= 0.6 * rng1 and b1["upper"] <= 0.1 * rng1:
            add("dragonfly_doji", "bullish", 55, b1["h"], b1["l"] - 0.3 * atr, b1["h"] + rng1,
                [point(candles, i1, b1["c"], "dragonfly doji")])
        elif b1["upper"] >= 0.6 * rng1 and b1["lower"] <= 0.1 * rng1:
            add("gravestone_doji", "bearish", 55, b1["l"], b1["h"] + 0.3 * atr, b1["l"] - rng1,
                [point(candles, i1, b1["c"], "gravestone doji")])
        else:
            direction = "bearish" if after_advance else ("bullish" if after_decline else "neutral")
            add("doji", direction, 40, b1["c"], None if direction == "neutral" else
                (b1["l"] - 0.3 * atr if direction == "bullish" else b1["h"] + 0.3 * atr), None,
                [point(candles, i1, b1["c"], "doji")])
    elif b1["range"] > 0 and b1["upper"] <= 0.05 * rng1 and b1["lower"] <= 0.05 * rng1 and long_(b1):
        direction = "bullish" if b1["up"] else "bearish"
        add("marubozu", direction, 55, b1["c"], b1["l"] if b1["up"] else b1["h"],
            b1["c"] + b1["body"] if b1["up"] else b1["c"] - b1["body"],
            [point(candles, i1, b1["c"], ("bullish " if b1["up"] else "bearish ") + "marubozu")])
    elif small(b1) and b1["upper"] >= 1.0 * b1["body"] and b1["lower"] >= 1.0 * b1["body"] and b1["body"] > 0:
        add("spinning_top", "neutral", 35, b1["c"], None, None, [point(candles, i1, b1["c"], "spinning top")])

    # Hammer family (body in one third of the range, one long shadow).
    if b1["body"] > 0 and b1["lower"] >= 2.0 * b1["body"] and b1["upper"] <= 0.35 * b1["body"] + 0.05 * rng1:
        if after_decline:
            add("hammer", "bullish", 60, b1["h"], b1["l"] - 0.3 * atr, b1["h"] + rng1,
                [point(candles, i1, b1["l"], "hammer low")])
        elif after_advance:
            add("hanging_man", "bearish", 45, b1["l"], b1["h"] + 0.3 * atr, b1["l"] - rng1,
                [point(candles, i1, b1["h"], "hanging man")])
    if b1["body"] > 0 and b1["upper"] >= 2.0 * b1["body"] and b1["lower"] <= 0.35 * b1["body"] + 0.05 * rng1:
        if after_decline:
            add("inverted_hammer", "bullish", 45, b1["h"], b1["l"] - 0.3 * atr, b1["h"] + rng1,
                [point(candles, i1, b1["h"], "inverted hammer")])
        elif after_advance:
            add("shooting_star", "bearish", 60, b1["l"], b1["h"] + 0.3 * atr, b1["l"] - rng1,
                [point(candles, i1, b1["h"], "shooting star")])

    # ── two-bar ────────────────────────────────────────────────────────────
    engulf_up = b2["down"] and b1["up"] and b1["o"] <= b2["c"] and b1["c"] >= b2["o"] and b1["body"] > b2["body"]
    engulf_dn = b2["up"] and b1["down"] and b1["o"] >= b2["c"] and b1["c"] <= b2["o"] and b1["body"] > b2["body"]
    if engulf_up and after_decline:
        add("bullish_engulfing", "bullish", 65, b1["c"], min(b1["l"], b2["l"]) - 0.3 * atr,
            b1["c"] + (b1["c"] - min(b1["l"], b2["l"])),
            [point(candles, i2, b2["c"], "engulfed"), point(candles, i1, b1["c"], "engulfing close")])
    if engulf_dn and after_advance:
        add("bearish_engulfing", "bearish", 65, b1["c"], max(b1["h"], b2["h"]) + 0.3 * atr,
            b1["c"] - (max(b1["h"], b2["h"]) - b1["c"]),
            [point(candles, i2, b2["c"], "engulfed"), point(candles, i1, b1["c"], "engulfing close")])
    if (b2["down"] and long_(b2) and b1["up"] and b1["o"] < b2["l"] and b2["mid"] < b1["c"] < b2["o"]
            and after_decline):
        add("piercing_pattern", "bullish", 55, b2["o"], b1["l"] - 0.3 * atr, b2["o"] + b2["body"],
            [point(candles, i2, b2["c"], "down close"), point(candles, i1, b1["c"], "pierce")])
    if (b2["up"] and long_(b2) and b1["down"] and b1["o"] > b2["h"] and b2["o"] < b1["c"] < b2["mid"]
            and after_advance):
        add("dark_cloud_cover", "bearish", 55, b2["o"], b1["h"] + 0.3 * atr, b2["o"] - b2["body"],
            [point(candles, i2, b2["c"], "up close"), point(candles, i1, b1["c"], "dark cloud")])
    harami = long_(b2) and b1["body"] > 0 and max(b1["o"], b1["c"]) < max(b2["o"], b2["c"]) \
        and min(b1["o"], b1["c"]) > min(b2["o"], b2["c"]) and b1["body"] <= 0.6 * b2["body"]
    if harami and (after_decline or after_advance):
        direction = "bullish" if after_decline else "bearish"
        add("harami", direction, 45, b2["o"], (b2["l"] - 0.3 * atr) if after_decline else (b2["h"] + 0.3 * atr),
            None, [point(candles, i2, b2["c"], "mother"), point(candles, i1, b1["c"], "inside")])
    inv_harami = long_(b1) and small(b2) and max(b2["o"], b2["c"]) < max(b1["o"], b1["c"]) \
        and min(b2["o"], b2["c"]) > min(b1["o"], b1["c"])
    if inv_harami and not (engulf_up or engulf_dn):
        add("inverted_harami", "bullish" if b1["up"] else "bearish", 40, b1["c"],
            b1["l"] if b1["up"] else b1["h"], None,
            [point(candles, i2, b2["c"], "small"), point(candles, i1, b1["c"], "large")])
    if after_advance and abs(b1["h"] - b2["h"]) <= 0.05 * atr and b2["up"] and b1["down"]:
        add("tweezer_top", "bearish", 45, min(b1["l"], b2["l"]), b1["h"] + 0.3 * atr, None,
            [point(candles, i2, b2["h"], "high 1"), point(candles, i1, b1["h"], "high 2")])
    if after_decline and abs(b1["l"] - b2["l"]) <= 0.05 * atr and b2["down"] and b1["up"]:
        add("tweezer_bottom", "bullish", 45, max(b1["h"], b2["h"]), b1["l"] - 0.3 * atr, None,
            [point(candles, i2, b2["l"], "low 1"), point(candles, i1, b1["l"], "low 2")])
    if b1["h"] < b2["h"] and b1["l"] > b2["l"]:
        add("inside_bar", "neutral", 35, b2["h"], b2["l"], None,
            [point(candles, i2, b2["h"], "mother high"), point(candles, i2, b2["l"], "mother low")],
            {"trigger_up": round(b2["h"], 4), "trigger_down": round(b2["l"], 4)})
    if b1["h"] > b2["h"] and b1["l"] < b2["l"]:
        add("outside_bar", "bullish" if b1["up"] else "bearish", 50, b1["c"],
            b1["l"] if b1["up"] else b1["h"], None,
            [point(candles, i2, b2["c"], "inside"), point(candles, i1, b1["c"], "outside close")])

    # ── three-bar ──────────────────────────────────────────────────────────
    trend3 = trend_before(closes, n - 4, 8) or 0.0
    # Shark-32: bar2 inside bar3, bar1 inside bar2 (two consecutive inside bars).
    if (b2["h"] < b3["h"] and b2["l"] > b3["l"] and b1["h"] < b2["h"] and b1["l"] > b2["l"]):
        height = b3["h"] - b3["l"]
        direction = "bullish" if trend3 >= _TREND_PCT else ("bearish" if trend3 <= -_TREND_PCT else "neutral")
        add("shark_32", direction, 50, b3["h"] if direction != "bearish" else b3["l"],
            b3["l"] if direction != "bearish" else b3["h"],
            (b3["h"] + height) if direction == "bullish" else ((b3["l"] - height) if direction == "bearish" else None),
            [point(candles, i3, b3["h"], "bar 1 high"), point(candles, i3, b3["l"], "bar 1 low"),
             point(candles, i2, b2["c"], "inside 1"), point(candles, i1, b1["c"], "inside 2")],
            {"trigger_up": round(b3["h"], 4), "trigger_down": round(b3["l"], 4), "height": round(height, 4),
             "expected_direction_basis": "prior 8-session trend (continuation ~60%)"})
    if (b3["down"] and long_(b3) and small(b2) and b1["up"] and long_(b1) and b1["c"] > b3["mid"]
            and trend3 <= -_TREND_PCT):
        add("morning_star", "bullish", 70, b3["o"], min(b2["l"], b3["l"], b1["l"]) - 0.3 * atr,
            b3["o"] + b3["body"],
            [point(candles, i3, b3["c"], "long down"), point(candles, i2, b2["c"], "star"),
             point(candles, i1, b1["c"], "long up")])
    if (b3["up"] and long_(b3) and small(b2) and b1["down"] and long_(b1) and b1["c"] < b3["mid"]
            and trend3 >= _TREND_PCT):
        add("evening_star", "bearish", 70, b3["o"], max(b2["h"], b3["h"], b1["h"]) + 0.3 * atr,
            b3["o"] - b3["body"],
            [point(candles, i3, b3["c"], "long up"), point(candles, i2, b2["c"], "star"),
             point(candles, i1, b1["c"], "long down")])
    if (all(b["up"] and long_(b) for b in (b3, b2, b1)) and b1["c"] > b2["c"] > b3["c"]
            and all(b["upper"] <= 0.3 * b["body"] for b in (b3, b2, b1))):
        add("three_white_soldiers", "bullish", 65, b1["c"], b3["l"] - 0.3 * atr, b1["c"] + (b1["c"] - b3["o"]) * 0.5,
            [point(candles, i3, b3["c"], "1"), point(candles, i2, b2["c"], "2"), point(candles, i1, b1["c"], "3")])
    if (all(b["down"] and long_(b) for b in (b3, b2, b1)) and b1["c"] < b2["c"] < b3["c"]
            and all(b["lower"] <= 0.3 * b["body"] for b in (b3, b2, b1))):
        add("three_black_crows", "bearish", 65, b1["c"], b3["h"] + 0.3 * atr, b1["c"] - (b3["o"] - b1["c"]) * 0.5,
            [point(candles, i3, b3["c"], "1"), point(candles, i2, b2["c"], "2"), point(candles, i1, b1["c"], "3")])
    # Three inside / outside: harami or engulfing on bars 3-2, confirmation on bar 1.
    harami32 = long_(b3) and b2["body"] > 0 and max(b2["o"], b2["c"]) < max(b3["o"], b3["c"]) \
        and min(b2["o"], b2["c"]) > min(b3["o"], b3["c"])
    if harami32 and b3["down"] and b1["up"] and b1["c"] > b3["o"] and trend3 <= -_TREND_PCT:
        add("three_inside_up", "bullish", 60, b3["o"], b3["l"] - 0.3 * atr, b3["o"] + b3["body"],
            [point(candles, i3, b3["c"], "mother"), point(candles, i2, b2["c"], "inside"), point(candles, i1, b1["c"], "confirm")])
    if harami32 and b3["up"] and b1["down"] and b1["c"] < b3["o"] and trend3 >= _TREND_PCT:
        add("three_inside_down", "bearish", 60, b3["o"], b3["h"] + 0.3 * atr, b3["o"] - b3["body"],
            [point(candles, i3, b3["c"], "mother"), point(candles, i2, b2["c"], "inside"), point(candles, i1, b1["c"], "confirm")])
    engulf32_up = b3["down"] and b2["up"] and b2["o"] <= b3["c"] and b2["c"] >= b3["o"] and b2["body"] > b3["body"]
    engulf32_dn = b3["up"] and b2["down"] and b2["o"] >= b3["c"] and b2["c"] <= b3["o"] and b2["body"] > b3["body"]
    if engulf32_up and b1["up"] and b1["c"] > b2["c"] and trend3 <= -_TREND_PCT:
        add("three_outside_up", "bullish", 60, b2["c"], min(b3["l"], b2["l"]) - 0.3 * atr, b1["c"] + b2["body"],
            [point(candles, i3, b3["c"], "engulfed"), point(candles, i2, b2["c"], "engulfing"), point(candles, i1, b1["c"], "confirm")])
    if engulf32_dn and b1["down"] and b1["c"] < b2["c"] and trend3 >= _TREND_PCT:
        add("three_outside_down", "bearish", 60, b2["c"], max(b3["h"], b2["h"]) + 0.3 * atr, b1["c"] - b2["body"],
            [point(candles, i3, b3["c"], "engulfed"), point(candles, i2, b2["c"], "engulfing"), point(candles, i1, b1["c"], "confirm")])
    return out
