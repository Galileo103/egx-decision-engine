"""Chart-pattern scanner: double/triple bottoms and tops, head & shoulders
(regular and inverse) and cup-with-handle, on Yahoo daily candles.

A pattern is a shape made of swing points. We find swing highs/lows with a
symmetric window, then test the geometric rules of each pattern with a
tolerance scaled to the stock's own volatility (ATR14). Every detection says
whether it is still FORMING or CONFIRMED by a close beyond the neckline, and
carries the neckline, the measured-move target, a stop hint, the breakout
volume ratio and a 0-100 quality score. Confirmed patterns are also journaled
as scanner hits (``pattern_<name>``) so the Signal Scorecard grades them like
any other signal — in a few months the app will know whether these shapes
predict anything on EGX.

Pattern recognition is subjective; this is a finder, not a judge. The
neckline break (with volume) is the signal, the shape is the setup.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.config import settings
from app.symbols import universe as universe_symbols

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

PIVOT_WINDOW = 5          # bars each side that a swing point must dominate
LOOKBACK = 130            # sessions examined for a pattern
MIN_SPACING = 8           # min sessions between equal lows/highs
RECENT_PIVOT_MAX_AGE = 60 # last pivot must be within this many sessions
BREAK_MAX_AGE = 15        # a confirmed break older than this is stale, not a signal
_FETCH_PAUSE = 0.1

PATTERNS: dict[str, dict[str, str]] = {
    "double_bottom": {"label": "Double bottom", "direction": "bullish"},
    "triple_bottom": {"label": "Triple bottom", "direction": "bullish"},
    "inverse_head_shoulders": {"label": "Inverse head & shoulders", "direction": "bullish"},
    "cup_handle": {"label": "Cup with handle", "direction": "bullish"},
    "double_top": {"label": "Double top", "direction": "bearish"},
    "triple_top": {"label": "Triple top", "direction": "bearish"},
    "head_shoulders": {"label": "Head & shoulders", "direction": "bearish"},
}


# ── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _f(v: Any) -> Optional[float]:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _atr(candles: list[dict], period: int = 14) -> Optional[float]:
    trs: list[float] = []
    prev: Optional[float] = None
    for c in candles:
        h, l, cl = _f(c.get("high")), _f(c.get("low")), _f(c.get("close"))
        if h is None or l is None or cl is None:
            continue
        tr = h - l
        if prev is not None:
            tr = max(tr, abs(h - prev), abs(l - prev))
        trs.append(tr)
        prev = cl
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def swing_points(candles: list[dict], k: int = PIVOT_WINDOW) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """(swing highs, swing lows) as (index, price); a point must dominate k bars each side."""
    highs = [_f(c.get("high")) or 0.0 for c in candles]
    lows = [_f(c.get("low")) or 0.0 for c in candles]
    n = len(candles)
    sh: list[tuple[int, float]] = []
    sl: list[tuple[int, float]] = []
    for i in range(k, n - k):
        win_h = highs[i - k:i + k + 1]
        win_l = lows[i - k:i + k + 1]
        if highs[i] >= max(win_h) and win_h.count(highs[i]) == 1:
            sh.append((i, highs[i]))
        if lows[i] > 0 and lows[i] <= min(win_l) and win_l.count(lows[i]) == 1:
            sl.append((i, lows[i]))
    return sh, sl


def _between(points: list[tuple[int, float]], a: int, b: int) -> list[tuple[int, float]]:
    return [p for p in points if a < p[0] < b]


def _vol_ratio(candles: list[dict], idx: int) -> Optional[float]:
    vols = [_f(c.get("volume")) or 0.0 for c in candles[max(0, idx - 20):idx]]
    v = _f(candles[idx].get("volume"))
    if v is None or not vols or sum(vols) == 0:
        return None
    return round(v / (sum(vols) / len(vols)), 2)


def _first_break(closes: list[float], start: int, level_at, bullish: bool) -> Optional[int]:
    """First index > start whose close is beyond the neckline (callable idx -> level)."""
    for j in range(start + 1, len(closes)):
        lvl = level_at(j)
        if lvl is None:
            continue
        if (bullish and closes[j] > lvl) or (not bullish and closes[j] < lvl):
            return j
    return None


def _status(candles: list[dict], closes: list[float], last_pivot_idx: int,
            level_at, bullish: bool, invalid_level: float) -> Optional[dict]:
    """FORMING / CONFIRMED / None (stale or invalidated) plus break metadata."""
    n = len(closes)
    if n - 1 - last_pivot_idx > RECENT_PIVOT_MAX_AGE:
        return None
    brk = _first_break(closes, last_pivot_idx, level_at, bullish)
    last = closes[-1]
    if brk is not None:
        if n - 1 - brk > BREAK_MAX_AGE:
            return None  # broke out long ago — not actionable
        # Confirmed, but a full round trip back through the neckline kills it.
        lvl_now = level_at(n - 1)
        if lvl_now is not None and ((bullish and last < lvl_now * 0.98) or (not bullish and last > lvl_now * 1.02)):
            return None
        return {"status": "confirmed", "break_index": brk, "break_date": str(candles[brk].get("time")),
                "break_close": round(closes[brk], 4), "break_volume_ratio": _vol_ratio(candles, brk)}
    # Still forming: price must not have invalidated the pattern.
    if (bullish and last < invalid_level) or (not bullish and last > invalid_level):
        return None
    return {"status": "forming", "break_index": None, "break_date": None, "break_close": None,
            "break_volume_ratio": None}


def _quality(symmetry: float, depth_atr: float, st: dict, age: int) -> int:
    """0-100: how clean the shape is, how big the move, volume on the break, recency."""
    q = 35.0 * max(0.0, min(1.0, symmetry))
    q += 25.0 * max(0.0, min(1.0, depth_atr / 4.0))
    vr = st.get("break_volume_ratio")
    if st.get("status") == "confirmed":
        q += 15.0
        if vr is not None:
            q += 15.0 * max(0.0, min(1.0, (vr - 0.8) / 1.2))  # 2.0× volume = full marks
    else:
        q += 10.0
    q += 10.0 * max(0.0, 1.0 - age / RECENT_PIVOT_MAX_AGE)
    return int(round(min(100.0, q)))


def _row(symbol: str, name: str, candles: list[dict], st: dict, neckline: float, target: float,
         stop_hint: float, points: list[dict], symmetry: float, depth_atr: float,
         last_pivot_idx: int, extra: Optional[dict] = None) -> Optional[dict]:
    n = len(candles)
    last_close = float(candles[-1]["close"])
    bullish = PATTERNS[name]["direction"] == "bullish"
    # A pattern whose measured move has already been reached is a finished
    # trade, not a signal — do not report it.
    if (bullish and last_close >= target) or (not bullish and last_close <= target):
        return None
    span = target - neckline
    progress = round(max(0.0, (last_close - neckline) / span) * 100.0, 1) if span else None
    row = {
        "symbol": symbol,
        "pattern": name,
        "label": PATTERNS[name]["label"],
        "direction": PATTERNS[name]["direction"],
        "status": st["status"],
        "neckline": round(neckline, 4),
        "target": round(target, 4),
        "stop_hint": round(stop_hint, 4),
        "last_close": round(last_close, 4),
        "distance_to_neckline_pct": round((neckline / last_close - 1.0) * 100.0, 2),
        "target_pct": round((target / last_close - 1.0) * 100.0, 2),
        "break_date": st.get("break_date"),
        "break_volume_ratio": st.get("break_volume_ratio"),
        # Share of the measured move already travelled since the neckline
        # (confirmed patterns only; 0 = at the neckline, 100 = at target).
        "move_progress_pct": progress if st["status"] == "confirmed" else None,
        "quality": max(0, _quality(symmetry, depth_atr, st, n - 1 - last_pivot_idx)
                       - (int(progress // 5) if (st["status"] == "confirmed" and progress) else 0)),
        "points": points,
        "start_date": points[0]["time"] if points else None,
        "as_of": str(candles[-1].get("time")),
    }
    if extra:
        row.update(extra)
    return row  # None when the measured move is already complete (see above)


def _pt(candles: list[dict], idx: int, price: float, label: str) -> dict:
    return {"time": str(candles[idx].get("time")), "index": idx, "price": round(price, 4), "label": label}


# ── individual patterns (pure functions over candles) ────────────────────────


def _multi_bottom(symbol: str, candles: list[dict], closes: list[float], sl: list[tuple[int, float]],
                  sh: list[tuple[int, float]], atr: float, count: int) -> Optional[dict]:
    """Double (count=2) or triple (count=3) bottom."""
    tol = 1.2 * atr
    lows = [p for p in sl if p[0] >= len(candles) - LOOKBACK]
    if len(lows) < count:
        return None
    for start in range(len(lows) - count, -1, -1):
        seq = lows[start:start + count]
        if any(seq[i + 1][0] - seq[i][0] < MIN_SPACING for i in range(count - 1)):
            continue
        prices = [p[1] for p in seq]
        if max(prices) - min(prices) > tol:
            continue
        # Intervening lows must not undercut the pattern lows by more than tol.
        inner_lows = _between(sl, seq[0][0], seq[-1][0])
        if any(p[1] < min(prices) - tol for p in inner_lows):
            continue
        peaks = []
        for i in range(count - 1):
            mids = _between(sh, seq[i][0], seq[i + 1][0])
            if not mids:
                break
            peaks.append(max(mids, key=lambda p: p[1]))
        if len(peaks) != count - 1:
            continue
        neckline = max(p[1] for p in peaks)
        depth = neckline - sum(prices) / count
        if depth < 2.0 * atr:
            continue  # bounce too small to be a real base
        st = _status(candles, closes, seq[-1][0], lambda j: neckline, True, min(prices) - tol)
        if st is None:
            continue
        symmetry = 1.0 - (max(prices) - min(prices)) / tol
        points = []
        for i, p in enumerate(seq):
            points.append(_pt(candles, p[0], p[1], f"low {i + 1}"))
            if i < len(peaks):
                points.append(_pt(candles, peaks[i][0], peaks[i][1], "neck"))
        points.sort(key=lambda p: p["index"])
        name = "double_bottom" if count == 2 else "triple_bottom"
        return _row(symbol, name, candles, st, neckline, neckline + depth, min(prices) - 0.5 * atr,
                    points, symmetry, depth / atr, seq[-1][0], {"depth_pct": round(depth / neckline * 100, 2)})
    return None


def _multi_top(symbol: str, candles: list[dict], closes: list[float], sl: list[tuple[int, float]],
               sh: list[tuple[int, float]], atr: float, count: int) -> Optional[dict]:
    tol = 1.2 * atr
    highs = [p for p in sh if p[0] >= len(candles) - LOOKBACK]
    if len(highs) < count:
        return None
    for start in range(len(highs) - count, -1, -1):
        seq = highs[start:start + count]
        if any(seq[i + 1][0] - seq[i][0] < MIN_SPACING for i in range(count - 1)):
            continue
        prices = [p[1] for p in seq]
        if max(prices) - min(prices) > tol:
            continue
        inner_highs = _between(sh, seq[0][0], seq[-1][0])
        if any(p[1] > max(prices) + tol for p in inner_highs):
            continue
        troughs = []
        for i in range(count - 1):
            mids = _between(sl, seq[i][0], seq[i + 1][0])
            if not mids:
                break
            troughs.append(min(mids, key=lambda p: p[1]))
        if len(troughs) != count - 1:
            continue
        neckline = min(p[1] for p in troughs)
        depth = sum(prices) / count - neckline
        if depth < 2.0 * atr:
            continue
        st = _status(candles, closes, seq[-1][0], lambda j: neckline, False, max(prices) + tol)
        if st is None:
            continue
        symmetry = 1.0 - (max(prices) - min(prices)) / tol
        points = []
        for i, p in enumerate(seq):
            points.append(_pt(candles, p[0], p[1], f"high {i + 1}"))
            if i < len(troughs):
                points.append(_pt(candles, troughs[i][0], troughs[i][1], "neck"))
        points.sort(key=lambda p: p["index"])
        name = "double_top" if count == 2 else "triple_top"
        return _row(symbol, name, candles, st, neckline, neckline - depth, max(prices) + 0.5 * atr,
                    points, symmetry, depth / atr, seq[-1][0], {"depth_pct": round(depth / neckline * 100, 2)})
    return None


def _head_shoulders(symbol: str, candles: list[dict], closes: list[float], sl: list[tuple[int, float]],
                    sh: list[tuple[int, float]], atr: float, inverse: bool) -> Optional[dict]:
    """Regular H&S (three highs, bearish) or inverse (three lows, bullish)."""
    tol = 1.5 * atr
    outer = sl if inverse else sh          # shoulders + head live on these
    inner = sh if inverse else sl          # neckline points live on these
    pts = [p for p in outer if p[0] >= len(candles) - LOOKBACK]
    if len(pts) < 3:
        return None
    for i in range(len(pts) - 3, -1, -1):
        s1, head, s2 = pts[i], pts[i + 1], pts[i + 2]
        if head[0] - s1[0] < MIN_SPACING or s2[0] - head[0] < MIN_SPACING:
            continue
        if inverse:
            if not (head[1] < s1[1] - atr and head[1] < s2[1] - atr):
                continue
        else:
            if not (head[1] > s1[1] + atr and head[1] > s2[1] + atr):
                continue
        if abs(s1[1] - s2[1]) > tol:
            continue
        t1c = _between(inner, s1[0], head[0])
        t2c = _between(inner, head[0], s2[0])
        if not t1c or not t2c:
            continue
        t1 = (max if inverse else min)(t1c, key=lambda p: p[1])
        t2 = (max if inverse else min)(t2c, key=lambda p: p[1])
        # The neckline must be close to horizontal: a steep one, extrapolated
        # weeks forward, produces a fantasy trigger level far from price.
        if abs(t2[1] - t1[1]) > 2.0 * atr:
            continue
        slope = (t2[1] - t1[1]) / (t2[0] - t1[0]) if t2[0] != t1[0] else 0.0

        def level_at(j: int, _t1=t1, _slope=slope) -> float:
            return _t1[1] + _slope * (j - _t1[0])

        neck_at_head = level_at(head[0])
        depth = abs(head[1] - neck_at_head)
        if depth < 2.0 * atr:
            continue
        invalid = (head[1] - tol) if inverse else (head[1] + tol)
        st = _status(candles, closes, s2[0], level_at, inverse, invalid)
        if st is None:
            continue
        neck_now = level_at(len(candles) - 1)
        target = neck_now + depth if inverse else neck_now - depth
        stop_hint = (head[1] - 0.5 * atr) if inverse else (head[1] + 0.5 * atr)
        symmetry = 1.0 - abs(s1[1] - s2[1]) / tol
        points = [
            _pt(candles, s1[0], s1[1], "left shoulder"), _pt(candles, t1[0], t1[1], "neck"),
            _pt(candles, head[0], head[1], "head"), _pt(candles, t2[0], t2[1], "neck"),
            _pt(candles, s2[0], s2[1], "right shoulder"),
        ]
        name = "inverse_head_shoulders" if inverse else "head_shoulders"
        return _row(symbol, name, candles, st, neck_now, target, stop_hint, points, symmetry,
                    depth / atr, s2[0], {"neckline_slope_per_bar": round(slope, 5),
                                        "depth_pct": round(depth / neck_now * 100, 2)})
    return None


def _cup_handle(symbol: str, candles: list[dict], closes: list[float], sl: list[tuple[int, float]],
                sh: list[tuple[int, float]], atr: float) -> Optional[dict]:
    """Simplified cup with handle: two rims within tolerance 30-130 bars apart,
    a rounded bottom 12-50% deep between them, then a shallow handle
    (<= 35% of cup depth, 5-25 bars) and price near/above the rim."""
    n = len(candles)
    tol = 1.5 * atr
    highs = [p for p in sh if p[0] >= n - LOOKBACK - 30]
    if len(highs) < 2:
        return None
    lows_all = [_f(c.get("low")) or 0.0 for c in candles]
    for j in range(len(highs) - 1, 0, -1):
        right = highs[j]
        if n - 1 - right[0] > RECENT_PIVOT_MAX_AGE:
            continue
        for i in range(j - 1, -1, -1):
            left = highs[i]
            span = right[0] - left[0]
            if span < 30:
                continue
            if span > 130:
                break
            if abs(left[1] - right[1]) > tol:
                continue
            rim = min(left[1], right[1])
            bottom_idx = min(range(left[0], right[0] + 1), key=lambda x: lows_all[x])
            bottom = lows_all[bottom_idx]
            depth_pct = (rim - bottom) / rim * 100.0
            if not (12.0 <= depth_pct <= 50.0):
                continue
            # Rounded, not a V: the bottom should sit in the middle 60% of the cup.
            pos = (bottom_idx - left[0]) / span
            if not (0.2 <= pos <= 0.8):
                continue
            # Handle: after the right rim, a pullback no deeper than 35% of the cup.
            handle = lows_all[right[0] + 1:] if right[0] + 1 < n else []
            handle_len = len(handle)
            if handle_len < 5 or handle_len > 25:
                continue
            handle_low = min(handle)
            if (rim - handle_low) > 0.35 * (rim - bottom) or handle_low < rim - 0.35 * (rim - bottom):
                continue
            st = _status(candles, closes, right[0], lambda k, _rim=rim: _rim, True, handle_low - tol)
            if st is None:
                continue
            depth = rim - bottom
            symmetry = 1.0 - abs(left[1] - right[1]) / tol
            points = [
                _pt(candles, left[0], left[1], "left rim"), _pt(candles, bottom_idx, bottom, "cup low"),
                _pt(candles, right[0], right[1], "right rim"),
                _pt(candles, right[0] + 1 + handle.index(handle_low), handle_low, "handle low"),
            ]
            return _row(symbol, "cup_handle", candles, st, rim, rim + depth, handle_low - 0.5 * atr,
                        points, symmetry, depth / atr, right[0],
                        {"depth_pct": round(depth_pct, 2), "cup_bars": span, "handle_bars": handle_len})
    return None


# ── public API ───────────────────────────────────────────────────────────────


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "other")
        out[k] = out.get(k, 0) + 1
    return out


#: Only detections at/above this quality are journaled as Scorecard signals —
#: keeps low-grade candlestick noise from flooding the track record.
JOURNAL_MIN_QUALITY = 50


def detect(symbol: str, candles_in: Optional[list[dict]] = None) -> dict:
    """All patterns currently visible on one symbol's daily chart."""
    try:
        sym = str(symbol or "").upper().strip().split(":")[-1]
        candles: list[dict]
        if candles_in is None:
            from app.services import leaders

            candles = leaders.daily_candles(sym)
        else:
            candles = candles_in
        if len(candles) < 60:
            return {"symbol": sym, "patterns": [], "error": "not enough daily history (need 60+ bars)"}
        atr = _atr(candles)
        if not atr or atr <= 0:
            return {"symbol": sym, "patterns": [], "error": "ATR unavailable"}
        closes = [float(c["close"]) for c in candles]
        sh, sl = swing_points(candles)
        found: list[dict] = []
        for fn in (
            lambda: _multi_bottom(sym, candles, closes, sl, sh, atr, 3),
            lambda: _multi_bottom(sym, candles, closes, sl, sh, atr, 2),
            lambda: _head_shoulders(sym, candles, closes, sl, sh, atr, True),
            lambda: _cup_handle(sym, candles, closes, sl, sh, atr),
            lambda: _multi_top(sym, candles, closes, sl, sh, atr, 3),
            lambda: _multi_top(sym, candles, closes, sl, sh, atr, 2),
            lambda: _head_shoulders(sym, candles, closes, sl, sh, atr, False),
        ):
            try:
                row = fn()
            except Exception as exc:  # noqa: BLE001 — one pattern failing must not hide the others
                logger.warning("pattern check failed for %s: %s", sym, exc)
                row = None
            if row:
                found.append(row)
        # A triple bottom contains a double bottom — keep the richer one only.
        names = {r["pattern"] for r in found}
        if "triple_bottom" in names:
            found = [r for r in found if r["pattern"] != "double_bottom"]
        if "triple_top" in names:
            found = [r for r in found if r["pattern"] != "double_top"]
        # Trendline shapes, candlesticks and price-action events.
        from app.services import pattern_action, pattern_candles, pattern_geometry

        for module in (pattern_geometry, pattern_candles, pattern_action):
            try:
                for r in module.detect(candles, atr):
                    r["symbol"] = sym
                    found.append(r)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s failed for %s: %s", module.__name__, sym, exc)
        from app.services.pattern_catalog import enrich

        found = [enrich(r) for r in found]
        # Drop confirmed shapes whose measured move is already complete.
        found = [r for r in found if not (
            r.get("status") == "confirmed" and r.get("move_progress_pct") is not None
            and r["move_progress_pct"] >= 100.0)]
        found.sort(key=lambda r: (r["status"] == "confirmed", r["quality"]), reverse=True)
        return {"symbol": sym, "patterns": found, "atr14": round(atr, 4),
                "as_of": str(candles[-1].get("time")), "bars": len(candles),
                "by_category": _count_by(found, "category"),
                "by_direction": _count_by(found, "direction")}
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "patterns": [], "error": str(exc)}


def compute(universe: str = "EGX100", persist: bool = False, min_quality: int = 0) -> dict:
    """Scan a universe. Never raises."""
    try:
        from app.services import leaders

        started = time.monotonic()
        uni = (universe or "EGX100").upper()
        symbols = universe_symbols(uni)
        rows: list[dict] = []
        skipped = 0
        for sym in symbols:
            candles = leaders.daily_candles(sym)
            if len(candles) < 60:
                skipped += 1
                continue
            res = detect(sym, candles)
            for r in res.get("patterns") or []:
                if r["quality"] >= min_quality:
                    rows.append(r)
            time.sleep(_FETCH_PAUSE)
        min_value = float(settings.min_daily_value_egp)
        for r in rows:
            candles = leaders.daily_candles(r["symbol"])
            vals = sorted(float(c["close"]) * (_f(c.get("volume")) or 0.0) for c in candles[-20:])
            r["median_value_20d"] = round(vals[len(vals) // 2], 0) if vals else None
            r["liquid"] = None if r["median_value_20d"] is None else r["median_value_20d"] >= min_value
        rows.sort(key=lambda r: (r["status"] == "confirmed", r["quality"]), reverse=True)
        date = datetime.now(CAIRO).strftime("%Y-%m-%d")
        if persist and rows:
            _persist(date, uni, rows)
        confirmed = sum(1 for r in rows if r["status"] == "confirmed")
        return {
            "rows": rows, "universe": uni, "date": date, "as_of": _now_iso(),
            "scanned": len(symbols), "skipped_no_data": skipped,
            "found": len(rows), "confirmed": confirmed, "forming": len(rows) - confirmed,
            "by_category": _count_by(rows, "category"),
            "elapsed_s": round(time.monotonic() - started, 1),
            "basis": (
                "Swing points must dominate 5 bars each side; equal levels within ~1.2-1.5 ATR14; "
                "pattern depth >= 2 ATR; last pivot within 60 sessions. CONFIRMED = a close beyond the "
                "neckline within the last 15 sessions (volume ratio vs 20-day average shown); "
                "FORMING = shape complete, neckline not yet broken. Target = measured move from the "
                "neckline. Finder, not judge: the break with volume is the signal."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("patterns.compute failed")
        return {"error": str(exc)}


def _persist(date: str, uni: str, rows: list[dict]) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO pattern_hits (date, universe, symbol, pattern, category, status, quality, "
        " payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(date, uni, r["symbol"], r["pattern"], r.get("category"), r["status"], r["quality"], json.dumps(r),
          _now_iso()) for r in rows],
    )
    # Confirmed, directional, decent-quality patterns become scanner hits so
    # the Scorecard grades them.
    confirmed = [r for r in rows if r["status"] == "confirmed" and r["quality"] >= JOURNAL_MIN_QUALITY
                 and r.get("direction") in ("bullish", "bearish")]
    if confirmed:
        db.executemany(
            "INSERT OR IGNORE INTO scanner_hits (date, scanner, symbol, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(date, f"pattern_{r['pattern']}", r["symbol"],
              json.dumps({k: r[k] for k in ("neckline", "target", "quality", "break_date", "direction")}),
              _now_iso()) for r in confirmed],
        )


def latest(universe: str = "EGX100", status: Optional[str] = None,
           category: Optional[str] = None) -> dict:
    """Most recently stored scan (fast path for the UI)."""
    try:
        uni = (universe or "EGX100").upper()
        d = db.query("SELECT MAX(date) AS d FROM pattern_hits WHERE universe = ?", (uni,))
        date = d[0].get("d") if d else None
        if not date:
            return {"rows": [], "universe": uni, "date": None, "stored": False}
        sql = "SELECT payload_json FROM pattern_hits WHERE universe = ? AND date = ?"
        params: list[Any] = [uni, date]
        if status in ("forming", "confirmed"):
            sql += " AND status = ?"
            params.append(status)
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY (status = 'confirmed') DESC, quality DESC"
        rows = []
        for r in db.query(sql, params):
            try:
                rows.append(json.loads(r["payload_json"]))
            except (TypeError, ValueError):
                continue
        return {"rows": rows, "universe": uni, "date": date, "stored": True,
                "found": len(rows), "confirmed": sum(1 for r in rows if r["status"] == "confirmed"),
                "by_category": _count_by(rows, "category")}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def catalog() -> dict:
    """Every pattern the app knows, with tiers and the EGX Scorecard stats so far."""
    try:
        from app.services import scorecard
        from app.services.pattern_catalog import CATEGORIES, catalog as _catalog

        stats: dict[str, dict] = {}
        card = scorecard.scorecard()
        if isinstance(card, dict) and "error" not in card:
            for name, sc in (card.get("scanners") or {}).items():
                if str(name).startswith("pattern_"):
                    h10 = (sc.get("horizons") or {}).get("10") or {}
                    stats[name] = {"graded": sc.get("hits_graded"), "n_10d": h10.get("n"),
                                   "win_rate_10d": h10.get("win_rate"), "beat_rate_10d": h10.get("beat_rate"),
                                   "avg_excess_10d": h10.get("avg_excess"), "weight": sc.get("weight")}
        rows = _catalog(stats)
        return {"patterns": rows, "categories": CATEGORIES, "count": len(rows),
                "detected": sum(1 for r in rows if r["detected"]),
                "basis": ("Reliability/frequency tiers are qualitative priors from the classic Western "
                          "references (Bulkowski, Nison, Wyckoff practice). egx_stats are the app's own "
                          "Scorecard grades of CONFIRMED detections on EGX — the numbers that matter here.")}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
