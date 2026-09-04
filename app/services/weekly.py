"""Weekly context from the daily candles the page already has.

EGX is an end-of-day market and every decision card runs on daily bars. The
weekly view answers a different question — *is the larger trend intact?* —
so instead of a second feed we resample the daily candles into weekly bars
(Sunday-to-Thursday sessions grouped by trading week) and compute three things:

  * ``context``      — swing structure, position vs the 10- and 40-week
                       averages (≈ the 50- and 200-day), one sentence for the
                       checklist's Trend pillar;
  * ``zones``        — tested weekly swing zones for the levels card;
  * ``structure_rows`` — weekly HH/HL, LH/LL, BOS and CHoCH as pattern rows
                       (``weekly_*`` keys, ``timeframe="1W"``) for the
                       patterns list, tagged with their own horizon.

No I/O here: callers pass the daily candles in.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.services.pattern_common import atr as _atr, f as _f, sma as _sma, swing_points

SWING_K = 2            # a weekly swing must dominate 2 weeks each side
MIN_WEEKS = 20         # below this the weekly view is not worth showing
CLUSTER_ATR = 0.75     # weekly swings within this many weekly ATR form one zone
RECENT_WEEKS = 2       # BOS / CHoCH must be within this many weekly bars
SMA_FAST, SMA_SLOW = 10, 40


def _iso_week(ts: str) -> Optional[tuple[int, int]]:
    """Trading-week key. EGX trades Sunday–Thursday, but ISO weeks run
    Monday–Sunday, so a Sunday session would land in the PREVIOUS week;
    shifting every date forward one day puts Sunday with its Mon–Thu."""
    try:
        d = date.fromisoformat(str(ts)[:10])
    except ValueError:
        return None
    y, w, _ = (d + timedelta(days=1)).isocalendar()
    return (y, w)


def resample(candles: list[dict]) -> list[dict]:
    """Daily → weekly OHLCV, oldest first. A week's ``time`` is its LAST session
    (so the newest weekly bar shares its date with the newest daily bar); the
    current, unfinished week is kept and flagged ``partial``."""
    out: list[dict] = []
    cur: Optional[dict] = None
    cur_key: Optional[tuple[int, int]] = None
    for c in candles:
        o, h, l, cl = _f(c.get("open")), _f(c.get("high")), _f(c.get("low")), _f(c.get("close"))
        if cl is None:
            continue
        key = _iso_week(str(c.get("time")))
        if key is None:
            continue
        if cur is None or key != cur_key:
            cur = {"time": str(c.get("time")), "week_start": str(c.get("time")), "open": o if o is not None else cl,
                   "high": h if h is not None else cl, "low": l if l is not None else cl, "close": cl,
                   "volume": _f(c.get("volume")) or 0.0, "sessions": 1}
            cur_key = key
            out.append(cur)
        else:
            cur["time"] = str(c.get("time"))
            cur["high"] = max(cur["high"], h if h is not None else cl)
            cur["low"] = min(cur["low"], l if l is not None else cl)
            cur["close"] = cl
            cur["volume"] += _f(c.get("volume")) or 0.0
            cur["sessions"] += 1
    for w in out:
        w["partial"] = False
    if out:
        last = out[-1]
        last_day = date.fromisoformat(last["time"])
        # EGX trades Sunday–Thursday; the week is complete once Thursday has closed.
        last["partial"] = last_day.weekday() != 3
    return out


def context(candles: list[dict]) -> dict:
    """Weekly trend context. Never raises; returns {"error": ...} when thin."""
    try:
        weeks = resample(candles)
        if len(weeks) < MIN_WEEKS:
            return {"error": f"only {len(weeks)} weekly bars (need {MIN_WEEKS}+)", "bars": len(weeks)}
        closes = [w["close"] for w in weeks]
        price = closes[-1]
        atr = _atr(weeks) or price * 0.05
        fast = _sma(closes, SMA_FAST)
        slow = _sma(closes, SMA_SLOW)
        slow_prev = _sma(closes, SMA_SLOW, len(closes) - 5) if len(closes) > SMA_SLOW + 5 else None
        sh, sl = swing_points(weeks, k=SWING_K)
        structure = None
        if len(sh) >= 2 and len(sl) >= 2:
            hh, hl = sh[-1][1] > sh[-2][1], sl[-1][1] > sl[-2][1]
            lh, ll = sh[-1][1] < sh[-2][1], sl[-1][1] < sl[-2][1]
            structure = ("higher_high_higher_low" if hh and hl else
                         "lower_high_lower_low" if lh and ll else "mixed")
        above_fast = fast is not None and price > fast
        above_slow = slow is not None and price > slow
        slow_rising = slow is not None and slow_prev is not None and slow > slow_prev
        # Verdict: up needs price above the 40-week (or the 10-week when the
        # 40-week is not available yet) and a structure that is not LH/LL.
        anchor_up = above_slow if slow is not None else above_fast
        if anchor_up and structure != "lower_high_lower_low":
            trend = "up"
        elif not anchor_up and structure != "higher_high_higher_low":
            trend = "down"
        else:
            trend = "mixed"

        parts = []
        if structure == "higher_high_higher_low":
            parts.append("higher highs and higher lows")
        elif structure == "lower_high_lower_low":
            parts.append("lower highs and lower lows")
        elif structure == "mixed":
            parts.append("mixed swings")
        ma_bits = []
        if fast is not None:
            ma_bits.append(f"{'above' if above_fast else 'below'} the 10-week average ({fast:.2f})")
        if slow is not None:
            ma_bits.append(f"{'above' if above_slow else 'below'} the 40-week ({slow:.2f}{', rising' if slow_rising else ', flat/falling'})")
        if ma_bits:
            parts.append("price " + " and ".join(ma_bits))
        text = "Weekly: " + "; ".join(parts) + "." if parts else "Weekly: not enough structure yet."
        if trend == "up":
            text += " The larger trend is up."
        elif trend == "down":
            text += " The larger trend is down — daily buy signals are counter-trend."
        else:
            text += " The larger trend is undecided."
        return {
            "bars": len(weeks), "partial_week": bool(weeks[-1].get("partial")), "as_of": weeks[-1]["time"],
            "price": round(price, 4), "atr": round(atr, 4), "structure": structure, "trend": trend,
            "sma10": round(fast, 4) if fast is not None else None,
            "sma40": round(slow, 4) if slow is not None else None,
            "above_sma10": above_fast if fast is not None else None,
            "above_sma40": above_slow if slow is not None else None,
            "sma40_rising": slow_rising if slow is not None and slow_prev is not None else None,
            "last_swing_high": round(sh[-1][1], 4) if sh else None,
            "last_swing_low": round(sl[-1][1], 4) if sl else None,
            "text": text,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def zones(candles: list[dict]) -> list[dict]:
    """Tested weekly swing zones (2+ touches), strongest first. Never raises."""
    try:
        weeks = resample(candles)
        if len(weeks) < MIN_WEEKS:
            return []
        n = len(weeks)
        atr = _atr(weeks) or weeks[-1]["close"] * 0.05
        sh, sl = swing_points(weeks, k=SWING_K)
        pts = sorted([(i, p, "high") for i, p in sh] + [(i, p, "low") for i, p in sl], key=lambda t: t[1])
        clusters: list[dict] = []
        for i, p, kind in pts:
            if clusters and abs(p - clusters[-1]["prices"][-1]) <= CLUSTER_ATR * atr:
                cl = clusters[-1]
            else:
                cl = {"prices": [], "idx": [], "kinds": []}
                clusters.append(cl)
            cl["prices"].append(p)
            cl["idx"].append(i)
            cl["kinds"].append(kind)
        out = []
        for cl in clusters:
            touches = len(cl["prices"])
            if touches < 2:
                continue
            last_idx = max(cl["idx"])
            recency = 1.0 - (n - 1 - last_idx) / n
            out.append({
                "level": round(sum(cl["prices"]) / touches, 4), "source": "weekly swings",
                "timeframe": "1W", "touches": touches, "last_touch": weeks[last_idx]["time"],
                "recency": round(recency, 2), "strength": round(touches * 1.5 + recency * 1.5, 2),
                "kinds": {"highs": cl["kinds"].count("high"), "lows": cl["kinds"].count("low")},
            })
        out.sort(key=lambda z: -z["strength"])
        return out
    except Exception:  # noqa: BLE001
        return []


def structure_rows(candles: list[dict]) -> list[dict]:
    """Weekly HH/HL, LH/LL, BOS, CHoCH as pattern rows (``weekly_*``). Never raises."""
    try:
        from app.services.pattern_action import structure_rows as _structure

        weeks = resample(candles)
        if len(weeks) < MIN_WEEKS:
            return []
        atr = _atr(weeks) or weeks[-1]["close"] * 0.05
        rows = _structure(weeks, atr, k=SWING_K, lookback=len(weeks), recent=RECENT_WEEKS,
                          prefix="weekly_", label_suffix="(weekly)", timeframe="1W")
        for r in rows:
            r["weekly_bars"] = len(weeks)
        return rows
    except Exception:  # noqa: BLE001
        return []
