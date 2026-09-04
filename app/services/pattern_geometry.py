"""Trendline-based shapes: triangles, wedges, channels, rectangles, flags,
pennants, broadening formations, diamonds, rounding tops/bottoms and the
inverse cup.

Method: swing highs and lows over a window are fitted with least-squares
lines. The pair of lines is classified by the sign of each slope (flat /
rising / falling, measured in ATR per bar) and by whether the gap between
them shrinks (converging), grows (diverging) or stays (parallel). Status is
CONFIRMED when the last close is beyond a line within the last 5 sessions,
else FORMING while price is still inside.
"""
from __future__ import annotations

from typing import Optional

from app.services.pattern_common import f, fit_line, make_row, point, sma, swing_points, trend_before

WINDOWS = (30, 45, 60)      # bars examined for line-based shapes (shortest first)
FLAT = 0.04                 # |slope| below this many ATR/bar counts as flat
MAX_RESID = 0.9             # line fit tolerance (ATR)
BREAK_MAX_AGE = 5


def _slope_class(slope_atr: float) -> str:
    if abs(slope_atr) < FLAT:
        return "flat"
    return "up" if slope_atr > 0 else "down"


def _lines(candles: list[dict], atr: float, window: int):
    """Fitted upper/lower lines over the last ``window`` bars, or None."""
    n = len(candles)
    start = n - window
    sh, sl = swing_points(candles[start:], k=3)
    sh = [(i + start, p) for i, p in sh]
    sl = [(i + start, p) for i, p in sl]
    if len(sh) < 2 or len(sl) < 2:
        return None
    up = fit_line(sh)
    lo = fit_line(sl)
    if not up or not lo or up[2] > MAX_RESID * atr or lo[2] > MAX_RESID * atr:
        return None
    return {"sh": sh, "sl": sl, "up": up, "lo": lo, "start": start,
            "last_close": float(candles[-1]["close"])}


def _gap(L: dict, idx: int) -> float:
    return (L["up"][0] * idx + L["up"][1]) - (L["lo"][0] * idx + L["lo"][1])


def _classify(L: dict, atr: float, n: int) -> Optional[dict]:
    """Shape family from slopes and convergence, or None if no clean shape."""
    su, sl_ = L["up"][0] / atr, L["lo"][0] / atr
    cu, cl = _slope_class(su), _slope_class(sl_)
    g0, g1 = _gap(L, L["start"]), _gap(L, n - 1)
    if g0 <= 0.5 * atr or g1 < -0.5 * atr:
        return None
    # A "consolidation" wider than 40% of price is a whole trend, not a shape.
    if max(g0, g1) > 0.40 * float(L["last_close"]):
        return None
    ratio = g1 / g0 if g0 else 1.0
    conv = ratio < 0.6
    div = ratio > 1.5
    par = not conv and not div
    if cu == "flat" and cl == "up" and conv:
        return {"name": "ascending_triangle", "direction": "bullish"}
    if cu == "down" and cl == "flat" and conv:
        return {"name": "descending_triangle", "direction": "bearish"}
    if cu == "down" and cl == "up" and conv:
        return {"name": "symmetrical_triangle", "direction": "neutral"}
    if cu == "up" and cl == "up" and conv:
        return {"name": "rising_wedge", "direction": "bearish"}
    if cu == "down" and cl == "down" and conv:
        return {"name": "falling_wedge", "direction": "bullish"}
    if cu == "up" and cl == "down" and div:
        return {"name": "expanding_triangle", "direction": "neutral"}
    if cu == "up" and cl == "flat" and div:
        return {"name": "ascending_broadening_triangle", "direction": "bearish"}
    if cu == "flat" and cl == "down" and div:
        return {"name": "descending_broadening_triangle", "direction": "bullish"}
    if cu == cl and cu != "flat" and div:
        return {"name": "broadening_wedge", "direction": "neutral"}
    if cu == "flat" and cl == "flat" and par:
        return {"name": "rectangle", "direction": "neutral"}
    if cu == "up" and cl == "up" and par:
        return {"name": "ascending_channel", "direction": "bullish"}
    if cu == "down" and cl == "down" and par:
        return {"name": "descending_channel", "direction": "bearish"}
    return None


def _status_lines(candles: list[dict], closes: list[float], L: dict, n: int) -> Optional[dict]:
    """Break of either line within BREAK_MAX_AGE sessions → confirmed; inside → forming."""
    last_pivot = max(L["sh"][-1][0], L["sl"][-1][0])
    for j in range(max(last_pivot + 1, n - BREAK_MAX_AGE), n):
        up = L["up"][0] * j + L["up"][1]
        lo = L["lo"][0] * j + L["lo"][1]
        if closes[j] > up:
            return {"status": "confirmed", "side": "up", "break_index": j}
        if closes[j] < lo:
            return {"status": "confirmed", "side": "down", "break_index": j}
    up_now = L["up"][0] * (n - 1) + L["up"][1]
    lo_now = L["lo"][0] * (n - 1) + L["lo"][1]
    if lo_now <= closes[-1] <= up_now:
        return {"status": "forming", "side": None, "break_index": None}
    return None


def _line_rows(candles: list[dict], atr: float, closes: list[float]) -> list[dict]:
    n = len(candles)
    out: list[dict] = []
    seen: set[str] = set()
    for window in WINDOWS:
        if n < window + 20:
            continue
        L = _lines(candles, atr, window)
        if not L:
            continue
        shape = _classify(L, atr, n)
        if not shape or shape["name"] in seen:
            continue
        st = _status_lines(candles, closes, L, n)
        if not st:
            continue
        name, direction = shape["name"], shape["direction"]
        up_now = L["up"][0] * (n - 1) + L["up"][1]
        lo_now = L["lo"][0] * (n - 1) + L["lo"][1]
        # Measured move = the shape's height, capped at 25% of price so a wide
        # broadening formation cannot project a nonsensical target.
        height = min(max(_gap(L, L["start"]), _gap(L, n - 1)), 0.25 * closes[-1])
        ctx = trend_before(closes, L["start"], 20) or 0.0
        # Rectangles inherit the trend they interrupt; channels get the
        # bullish/bearish label when price hugs the trend-side half.
        if name == "rectangle":
            if ctx >= 5:
                name, direction = "bullish_rectangle", "bullish"
            elif ctx <= -5:
                name, direction = "bearish_rectangle", "bearish"
            else:
                name = "horizontal_channel" if window >= 45 else "rectangle"
        if name == "ascending_channel" and closes[-1] > (up_now + lo_now) / 2:
            name, direction = "bullish_channel", "bullish"
        if name == "descending_channel" and closes[-1] < (up_now + lo_now) / 2:
            name, direction = "bearish_channel", "bearish"
        if st["status"] == "confirmed":
            broke_up = st["side"] == "up"
            level = up_now if broke_up else lo_now
            target = level + height if broke_up else level - height
            stop = lo_now if broke_up else up_now
            direction = "bullish" if broke_up else "bearish"
        else:
            bullish = direction == "bullish" or (direction == "neutral" and ctx > 0)
            level = up_now if bullish else lo_now
            target = level + height if bullish else level - height
            stop = lo_now if bullish else up_now
        pts = [point(candles, i, p, "high") for i, p in L["sh"]] + [point(candles, i, p, "low") for i, p in L["sl"]]
        pts.sort(key=lambda p: p["index"])
        fit_q = 1.0 - max(L["up"][2], L["lo"][2]) / (MAX_RESID * atr)
        touches = len(L["sh"]) + len(L["sl"])
        quality = int(30 * fit_q + min(30, 6 * touches) + (25 if st["status"] == "confirmed" else 12)
                      + min(15, height / atr * 3))
        out.append(make_row(name, direction, st["status"], candles, level=level, target=target,
                            stop_hint=stop, points=pts, quality=quality, break_index=st["break_index"],
                            extra={"window_bars": window, "broke": st.get("side"),
                                   "upper_slope_atr": round(L["up"][0] / atr, 3),
                                   "lower_slope_atr": round(L["lo"][0] / atr, 3), "height": round(height, 4),
                                   "trend_into_pct": round(ctx, 2)}))
        seen.add(name)
    return out


def _flags(candles: list[dict], atr: float, closes: list[float]) -> list[dict]:
    """Flag / pennant: a pole of >= 4 ATR in <= 12 bars, then 5-20 bars of tight drift."""
    n = len(candles)
    out: list[dict] = []
    for tip in range(n - 6, max(n - 26, 12), -1):
        for length in range(5, 13):
            base = tip - length
            if base < 0:
                break
            move = closes[tip] - closes[base]
            if abs(move) < 4.0 * atr:
                continue
            bullish = move > 0
            cons = candles[tip + 1:]
            if not 5 <= len(cons) <= 20:
                break
            highs = [f(c["high"]) or 0.0 for c in cons]
            lows = [f(c["low"]) or 0.0 for c in cons]
            width = max(highs) - min(lows)
            if width > 0.5 * abs(move):
                break
            idx = list(range(tip + 1, n))
            up = fit_line(list(zip(idx, highs)))
            lo = fit_line(list(zip(idx, lows)))
            if not up or not lo:
                break
            su, sl_ = up[0] / atr, lo[0] / atr
            gap0 = (up[1] + up[0] * idx[0]) - (lo[1] + lo[0] * idx[0])
            gap1 = (up[1] + up[0] * idx[-1]) - (lo[1] + lo[0] * idx[-1])
            pennant = gap0 > 0 and gap1 < 0.6 * gap0
            counter = (su < 0 and sl_ < 0) if bullish else (su > 0 and sl_ > 0)
            if not (pennant or counter or (abs(su) < FLAT and abs(sl_) < FLAT)):
                break
            name = ("bull_pennant" if bullish else "bear_pennant") if pennant else ("bull_flag" if bullish else "bear_flag")
            upper_now = up[1] + up[0] * (n - 1)
            lower_now = lo[1] + lo[0] * (n - 1)
            level = upper_now if bullish else lower_now
            brk = None
            for j in range(max(tip + 4, n - BREAK_MAX_AGE), n):
                lvl = (up[1] + up[0] * j) if bullish else (lo[1] + lo[0] * j)
                if (bullish and closes[j] > lvl) or (not bullish and closes[j] < lvl):
                    brk = j
                    break
            if brk is None and ((bullish and closes[-1] < lower_now - 0.5 * atr) or
                                (not bullish and closes[-1] > upper_now + 0.5 * atr)):
                break  # drifted out the wrong way — flag failed
            status = "confirmed" if brk is not None else "forming"
            target = level + abs(move) if bullish else level - abs(move)
            stop = min(lows) - 0.3 * atr if bullish else max(highs) + 0.3 * atr
            quality = int(40 + min(25, abs(move) / atr * 3) + (20 if status == "confirmed" else 8)
                          + max(0, 15 - len(cons)))
            pts = [point(candles, base, closes[base], "pole start"), point(candles, tip, closes[tip], "pole tip"),
                   point(candles, n - 1, closes[-1], "flag end")]
            out.append(make_row(name, "bullish" if bullish else "bearish", status, candles, level=level,
                                target=target, stop_hint=stop, points=pts, quality=quality, break_index=brk,
                                extra={"pole_pct": round(move / closes[base] * 100.0, 2), "pole_bars": length,
                                       "flag_bars": len(cons)}))
            return out
    return out


def _quadratic_fit(xs: list[float], ys: list[float]) -> Optional[tuple[float, float, float, float]]:
    """Least-squares parabola y = a x² + b x + c → (a, b, c, r²)."""
    n = len(xs)
    if n < 8:
        return None
    sx = sum(xs); sx2 = sum(x * x for x in xs); sx3 = sum(x ** 3 for x in xs); sx4 = sum(x ** 4 for x in xs)
    sy = sum(ys); sxy = sum(x * y for x, y in zip(xs, ys)); sx2y = sum(x * x * y for x, y in zip(xs, ys))
    # Solve the 3x3 normal equations by Cramer's rule.
    m = [[sx4, sx3, sx2], [sx3, sx2, sx], [sx2, sx, n]]
    v = [sx2y, sxy, sy]

    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))

    d = det(m)
    if abs(d) < 1e-12:
        return None
    sol = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = v[r]
        sol.append(det(mi) / d)
    a, b, c = sol
    mean = sy / n
    ss_tot = sum((y - mean) ** 2 for y in ys) or 1e-12
    ss_res = sum((y - (a * x * x + b * x + c)) ** 2 for x, y in zip(xs, ys))
    return a, b, c, 1.0 - ss_res / ss_tot


def _rounding(candles: list[dict], atr: float, closes: list[float]) -> list[dict]:
    """Rounding bottom/top and inverse cup & handle via a parabola fit."""
    n = len(candles)
    out: list[dict] = []
    for window in (120, 90, 60, 40):
        if n < window + 10:
            continue
        start = n - window
        xs = [float(i) for i in range(window)]
        ys = closes[start:]
        fit = _quadratic_fit(xs, ys)
        if not fit:
            continue
        a, b, c, r2 = fit
        if r2 < 0.70 or a == 0:
            continue
        vertex = -b / (2 * a)
        if not 0.25 * window <= vertex <= 0.75 * window:
            continue
        depth = abs(a) * (window / 2.0) ** 2   # rim-to-vertex height of the fitted parabola
        if depth < 3.0 * atr:
            continue
        rim_l, rim_r = ys[0], ys[-1]
        if abs(rim_l - rim_r) > 2.0 * atr:
            continue
        rim = max(rim_l, rim_r) if a > 0 else min(rim_l, rim_r)
        bullish = a > 0
        name = "rounding_bottom" if bullish else "rounding_top"
        extreme_idx = start + int(round(vertex))
        extreme = min(closes[start:]) if bullish else max(closes[start:])
        brk = None
        for j in range(n - BREAK_MAX_AGE, n):
            if (bullish and closes[j] > rim + 0.2 * atr) or (not bullish and closes[j] < rim - 0.2 * atr):
                brk = j
                break
        status = "confirmed" if brk is not None else "forming"
        target = rim + (rim - extreme) if bullish else rim - (extreme - rim)
        stop = extreme - 0.5 * atr if bullish else extreme + 0.5 * atr
        # Inverse cup & handle: a rounding TOP followed by a small bounce (handle) below the rim.
        if not bullish:
            tail = closes[-8:]
            if min(tail) < rim - 0.5 * atr and closes[-1] > min(tail) and closes[-1] < rim:
                name = "inverse_cup_handle"
        quality = int(40 * r2 + min(25, depth / atr * 3) + (20 if status == "confirmed" else 10)
                      + (15 if abs(rim_l - rim_r) < atr else 5))
        pts = [point(candles, start, rim_l, "left rim"), point(candles, extreme_idx, extreme, "bottom" if bullish else "top"),
               point(candles, n - 1, closes[-1], "right rim")]
        out.append(make_row(name, "bullish" if bullish else "bearish", status, candles, level=rim, target=target,
                            stop_hint=stop, points=pts, quality=quality, break_index=brk,
                            extra={"window_bars": window, "fit_r2": round(r2, 3),
                                   "depth_pct": round(abs(rim - extreme) / rim * 100.0, 2)}))
        break
    return out


def _diamond(candles: list[dict], atr: float, closes: list[float]) -> list[dict]:
    """Diamond: 10-bar ranges widen through the first half then narrow through the second."""
    n = len(candles)
    out: list[dict] = []
    highs = [f(c["high"]) or 0.0 for c in candles]
    lows = [f(c["low"]) or 0.0 for c in candles]
    for window in (60, 45, 30):
        if n < window + 25:
            continue
        start = n - window
        half = window // 2
        step = max(5, window // 6)
        rng = []
        for s in range(start, n - step + 1, step):
            rng.append(max(highs[s:s + step]) - min(lows[s:s + step]))
        if len(rng) < 4:
            continue
        k = len(rng) // 2
        first, second = rng[:k], rng[k:]
        widening = all(first[i] <= first[i + 1] * 1.05 for i in range(len(first) - 1)) and first[-1] >= 1.6 * first[0]
        narrowing = all(second[i] * 1.05 >= second[i + 1] for i in range(len(second) - 1)) and second[-1] <= 0.6 * second[0]
        if not (widening and narrowing):
            continue
        ctx = trend_before(closes, start, 30) or 0.0
        if abs(ctx) < 5:
            continue
        bullish = ctx < 0     # diamond bottom after a decline, top after an advance
        name = "diamond_bottom" if bullish else "diamond_top"
        mid_hi = max(highs[start + half - step:start + half + step])
        mid_lo = min(lows[start + half - step:start + half + step])
        height = mid_hi - mid_lo
        recent_hi = max(highs[-step:])
        recent_lo = min(lows[-step:])
        level = recent_hi if bullish else recent_lo
        brk = None
        for j in range(n - BREAK_MAX_AGE, n):
            edge = max(highs[j - step:j]) if bullish else min(lows[j - step:j])
            if (bullish and closes[j] > edge) or (not bullish and closes[j] < edge):
                brk = j
                level = edge
                break
        status = "confirmed" if brk is not None else "forming"
        target = level + height if bullish else level - height
        stop = recent_lo - 0.3 * atr if bullish else recent_hi + 0.3 * atr
        pts = [point(candles, start, closes[start], "start"), point(candles, start + half, mid_hi, "widest high"),
               point(candles, start + half, mid_lo, "widest low"), point(candles, n - 1, closes[-1], "apex")]
        quality = int(35 + min(25, height / atr * 3) + (20 if status == "confirmed" else 8) + min(20, abs(ctx)))
        out.append(make_row(name, "bullish" if bullish else "bearish", status, candles, level=level, target=target,
                            stop_hint=stop, points=pts, quality=quality, break_index=brk,
                            extra={"window_bars": window, "trend_into_pct": round(ctx, 2), "height": round(height, 4)}))
        break
    return out


def detect(candles: list[dict], atr: float) -> list[dict]:
    if len(candles) < 50 or not atr:
        return []
    closes = [float(c["close"]) for c in candles]
    out: list[dict] = []
    for fn in (_line_rows, _flags, _rounding, _diamond):
        try:
            out.extend(fn(candles, atr, closes))
        except Exception:  # noqa: BLE001 — one detector failing must not hide the rest
            continue
    return out
