"""Price-action events on the last sessions: breakouts and their failures,
retests, pullbacks/throwbacks, Wyckoff springs/upthrusts, bull/bear traps,
swing structure (HH/HL, LH/LL), break of structure and change of character.

All levels come from the prior 20-session range and from swing points
(window 3) over the last 80 sessions.
"""
from __future__ import annotations

from typing import Optional

from app.services.pattern_common import f, make_row, point, sma, swing_points, vol_ratio

RANGE_BARS = 20
RECENT = 3          # events must have happened within this many sessions
TRAP_WINDOW = 10


def _range_levels(candles: list[dict], idx: int) -> tuple[Optional[float], Optional[float]]:
    """(highest high, lowest low) of the RANGE_BARS bars BEFORE idx."""
    if idx < RANGE_BARS:
        return None, None
    win = candles[idx - RANGE_BARS:idx]
    return max(f(c["high"]) or 0.0 for c in win), min(f(c["low"]) or 0.0 for c in win)


def detect(candles: list[dict], atr: float) -> list[dict]:
    n = len(candles)
    if n < RANGE_BARS + 30 or not atr:
        return []
    closes = [float(c["close"]) for c in candles]
    highs = [f(c["high"]) or 0.0 for c in candles]
    lows = [f(c["low"]) or 0.0 for c in candles]
    out: list[dict] = []

    # ── breakouts, false breakouts, traps, retests ─────────────────────────
    # Walk the last TRAP_WINDOW bars oldest→newest. The first range break is
    # the reference event; a close back through its level within 3 sessions
    # makes it a false breakout (trap) — and that reversal bar must NOT be
    # read as a fresh breakout the other way.
    breaks: list[tuple[int, str]] = []
    for j in range(n - TRAP_WINDOW, n):
        hi, lo = _range_levels(candles, j)
        if hi is None:
            continue
        side = "up" if closes[j] > hi else ("down" if closes[j] < lo else None)
        if side:
            breaks.append((j, side))
    consumed: set[int] = set()
    for j, side in breaks:
        if j in consumed:
            continue
        hi, lo = _range_levels(candles, j)
        if hi is None:
            continue
        level = hi if side == "up" else lo
        bullish = side == "up"
        age = n - 1 - j
        after = closes[j + 1:]
        # Did it fail? A close back inside within 3 sessions of the break.
        fail_idx = next((j + 1 + k for k, c in enumerate(after[:3])
                         if (bullish and c < level) or (not bullish and c > level)), None)
        if fail_idx is not None:
            consumed.update(range(j, fail_idx + 1))
        vr = vol_ratio(candles, j)
        if fail_idx is not None:
            if n - 1 - fail_idx <= RECENT + 2:
                trap = "bull_trap" if bullish else "bear_trap"
                out.append(make_row("false_breakout", "bearish" if bullish else "bullish", "confirmed", candles,
                                    level=level, target=(lo if bullish else hi), stop_hint=(highs[j] + 0.3 * atr) if bullish else (lows[j] - 0.3 * atr),
                                    points=[point(candles, j, closes[j], "break"), point(candles, fail_idx, closes[fail_idx], "back inside")],
                                    quality=int(55 + (10 if (vr or 0) < 1.0 else 0)), break_index=fail_idx,
                                    extra={"range_high": round(hi, 4), "range_low": round(lo, 4), "break_volume_ratio_at_break": vr}))
                out.append(make_row(trap, "bearish" if bullish else "bullish", "confirmed", candles,
                                    level=level, target=(lo if bullish else hi), stop_hint=(highs[j] + 0.3 * atr) if bullish else (lows[j] - 0.3 * atr),
                                    points=[point(candles, j, closes[j], "trap break"), point(candles, fail_idx, closes[fail_idx], "reversal")],
                                    quality=60, break_index=fail_idx,
                                    extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
            continue
        # Genuine breakout (still beyond the level) — only the most recent one.
        if any(k > j and k not in consumed for k, _ in breaks):
            continue
        if age <= RECENT:
            out.append(make_row("breakout", "bullish" if bullish else "bearish", "confirmed", candles,
                                level=level, target=level + (hi - lo) if bullish else level - (hi - lo),
                                stop_hint=level - 0.5 * atr if bullish else level + 0.5 * atr,
                                points=[point(candles, j, closes[j], "breakout close")],
                                quality=int(45 + min(30, ((vr or 1.0) - 1.0) * 30) + (10 if abs(closes[j] - level) > 0.5 * atr else 0)),
                                break_index=j, extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
        else:
            # Older break still valid: did price come back to the level (retest / throwback)?
            touched = [k for k in range(j + 1, n) if (bullish and lows[k] <= level + 0.5 * atr) or (not bullish and highs[k] >= level - 0.5 * atr)]
            if touched and n - 1 - touched[-1] <= RECENT:
                k = touched[-1]
                held = (bullish and closes[-1] > level) or (not bullish and closes[-1] < level)
                if held:
                    name = "throwback" if bullish else "retest"
                    out.append(make_row(name, "bullish" if bullish else "bearish", "confirmed", candles,
                                        level=level, target=level + (hi - lo) if bullish else level - (hi - lo),
                                        stop_hint=level - 0.7 * atr if bullish else level + 0.7 * atr,
                                        points=[point(candles, j, closes[j], "breakout"), point(candles, k, lows[k] if bullish else highs[k], "retest")],
                                        quality=60, break_index=k, extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
                    if bullish:  # a held retest after an upside break is also, generically, a retest
                        out.append(make_row("retest", "bullish", "confirmed", candles, level=level,
                                            target=level + (hi - lo), stop_hint=level - 0.7 * atr,
                                            points=[point(candles, j, closes[j], "breakout"), point(candles, k, lows[k], "retest")],
                                            quality=58, break_index=k, extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
                else:
                    out.append(make_row("failed_retest", "bearish" if bullish else "bullish", "confirmed", candles,
                                        level=level, target=lo if bullish else hi,
                                        stop_hint=highs[k] + 0.3 * atr if bullish else lows[k] - 0.3 * atr,
                                        points=[point(candles, j, closes[j], "breakout"), point(candles, k, closes[k], "failed retest")],
                                        quality=60, break_index=n - 1, extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))

    # ── spring / upthrust (intrabar poke through the range that closes back inside) ──
    for j in range(n - 1, n - 1 - RECENT, -1):
        hi, lo = _range_levels(candles, j)
        if hi is None:
            break
        if lows[j] < lo - 0.1 * atr and closes[j] > lo and closes[j] > closes[j - 1]:
            out.append(make_row("spring", "bullish", "confirmed", candles, level=lo, target=hi,
                                stop_hint=lows[j] - 0.3 * atr, points=[point(candles, j, lows[j], "spring low")],
                                quality=int(55 + min(20, (lo - lows[j]) / atr * 20)), break_index=j,
                                extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
            break
        if highs[j] > hi + 0.1 * atr and closes[j] < hi and closes[j] < closes[j - 1]:
            out.append(make_row("upthrust", "bearish", "confirmed", candles, level=hi, target=lo,
                                stop_hint=highs[j] + 0.3 * atr, points=[point(candles, j, highs[j], "upthrust high")],
                                quality=int(55 + min(20, (highs[j] - hi) / atr * 20)), break_index=j,
                                extra={"range_high": round(hi, 4), "range_low": round(lo, 4)}))
            break

    # ── pullback in an uptrend ────────────────────────────────────────────
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    if s20 and s50 and s20 > s50 and closes[-1] > s50:
        down = 0
        for k in range(n - 1, 0, -1):
            if closes[k] < closes[k - 1]:
                down += 1
            else:
                break
        if 2 <= down <= 5 and abs(closes[-1] - s20) <= 1.0 * atr:
            out.append(make_row("pullback", "bullish", "confirmed", candles, level=s20,
                                target=max(highs[-down - 1:]), stop_hint=min(lows[-down:]) - 0.5 * atr,
                                points=[point(candles, n - 1 - down, closes[n - 1 - down], "swing high"),
                                        point(candles, n - 1, closes[-1], "pullback low")],
                                quality=int(50 + (10 if down >= 3 else 0)), break_index=n - 1,
                                extra={"down_sessions": down, "sma20": round(s20, 4), "sma50": round(s50, 4)}))

    # ── swing structure, BOS, CHoCH ───────────────────────────────────────
    start = max(0, n - 80)
    sh, sl = swing_points(candles[start:], k=3)
    sh = [(i + start, p) for i, p in sh]
    sl = [(i + start, p) for i, p in sl]
    if len(sh) >= 2 and len(sl) >= 2:
        hh = sh[-1][1] > sh[-2][1]
        hl = sl[-1][1] > sl[-2][1]
        lh = sh[-1][1] < sh[-2][1]
        ll = sl[-1][1] < sl[-2][1]
        last_high, last_low = sh[-1], sl[-1]
        pts = [point(candles, i, p, "H") for i, p in sh[-2:]] + [point(candles, i, p, "L") for i, p in sl[-2:]]
        pts.sort(key=lambda p: p["index"])
        if hh and hl:
            out.append(make_row("higher_high_higher_low", "bullish", "confirmed", candles, level=last_low[1],
                                target=None, stop_hint=last_low[1] - 0.3 * atr, points=pts, quality=55,
                                break_index=None, extra={"last_swing_high": round(last_high[1], 4),
                                                         "last_swing_low": round(last_low[1], 4)}))
            # BOS up: close above the last swing high in the last RECENT bars.
            brk = next((j for j in range(n - RECENT, n) if j > last_high[0] and closes[j] > last_high[1]), None)
            if brk is not None:
                out.append(make_row("break_of_structure", "bullish", "confirmed", candles, level=last_high[1],
                                    target=last_high[1] + (last_high[1] - last_low[1]), stop_hint=last_low[1] - 0.3 * atr,
                                    points=pts + [point(candles, brk, closes[brk], "BOS")], quality=60, break_index=brk))
            # CHoCH: close below the last higher low.
            ch = next((j for j in range(n - RECENT, n) if j > last_low[0] and closes[j] < last_low[1]), None)
            if ch is not None:
                out.append(make_row("change_of_character", "bearish", "confirmed", candles, level=last_low[1],
                                    target=sl[-2][1], stop_hint=last_high[1] + 0.3 * atr,
                                    points=pts + [point(candles, ch, closes[ch], "CHoCH")], quality=60, break_index=ch))
        elif lh and ll:
            out.append(make_row("lower_high_lower_low", "bearish", "confirmed", candles, level=last_high[1],
                                target=None, stop_hint=last_high[1] + 0.3 * atr, points=pts, quality=55,
                                break_index=None, extra={"last_swing_high": round(last_high[1], 4),
                                                         "last_swing_low": round(last_low[1], 4)}))
            brk = next((j for j in range(n - RECENT, n) if j > last_low[0] and closes[j] < last_low[1]), None)
            if brk is not None:
                out.append(make_row("break_of_structure", "bearish", "confirmed", candles, level=last_low[1],
                                    target=last_low[1] - (last_high[1] - last_low[1]), stop_hint=last_high[1] + 0.3 * atr,
                                    points=pts + [point(candles, brk, closes[brk], "BOS")], quality=60, break_index=brk))
            ch = next((j for j in range(n - RECENT, n) if j > last_high[0] and closes[j] > last_high[1]), None)
            if ch is not None:
                out.append(make_row("change_of_character", "bullish", "confirmed", candles, level=last_high[1],
                                    target=sh[-2][1], stop_hint=last_low[1] - 0.3 * atr,
                                    points=pts + [point(candles, ch, closes[ch], "CHoCH")], quality=60, break_index=ch))
    return out
