"""Shared helpers for the pattern detectors (no I/O, no imports from siblings)."""
from __future__ import annotations

from typing import Any, Callable, Optional


def f(v: Any) -> Optional[float]:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def atr(candles: list[dict], period: int = 14) -> Optional[float]:
    trs: list[float] = []
    prev: Optional[float] = None
    for c in candles:
        h, l, cl = f(c.get("high")), f(c.get("low")), f(c.get("close"))
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


def swing_points(candles: list[dict], k: int = 5) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """(swing highs, swing lows) as (index, price); a point must dominate k bars each side."""
    highs = [f(c.get("high")) or 0.0 for c in candles]
    lows = [f(c.get("low")) or 0.0 for c in candles]
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


def vol_ratio(candles: list[dict], idx: int, lookback: int = 20) -> Optional[float]:
    vols = [f(c.get("volume")) or 0.0 for c in candles[max(0, idx - lookback):idx]]
    v = f(candles[idx].get("volume"))
    if v is None or not vols or sum(vols) == 0:
        return None
    return round(v / (sum(vols) / len(vols)), 2)


def sma(values: list[float], n: int, idx: Optional[int] = None) -> Optional[float]:
    end = len(values) if idx is None else idx + 1
    if end < n or n <= 0:
        return None
    window = values[end - n:end]
    return sum(window) / n


def fit_line(points: list[tuple[int, float]]) -> Optional[tuple[float, float, float]]:
    """Least-squares line through (x, y) points → (slope, intercept, max abs residual)."""
    if len(points) < 2:
        return None
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if sxx == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx
    intercept = my - slope * mx
    resid = max(abs(p[1] - (slope * p[0] + intercept)) for p in points)
    return slope, intercept, resid


def point(candles: list[dict], idx: int, price: float, label: str) -> dict:
    return {"time": str(candles[idx].get("time")), "index": idx, "price": round(price, 4), "label": label}


def trend_before(closes: list[float], idx: int, bars: int = 10) -> Optional[float]:
    """Net % move over the ``bars`` sessions ending at idx (context for reversals)."""
    if idx - bars < 0 or closes[idx - bars] <= 0:
        return None
    return (closes[idx] / closes[idx - bars] - 1.0) * 100.0


def make_row(name: str, direction: str, status: str, candles: list[dict], *,
             level: Optional[float] = None, target: Optional[float] = None,
             stop_hint: Optional[float] = None, points: Optional[list[dict]] = None,
             quality: int = 50, break_index: Optional[int] = None,
             extra: Optional[dict] = None) -> dict:
    """Uniform detection row. ``level`` is the neckline / trigger line."""
    last_close = float(candles[-1]["close"])
    row: dict[str, Any] = {
        "pattern": name,
        "direction": direction,
        "status": status,
        "neckline": round(level, 4) if level is not None else None,
        "target": round(target, 4) if target is not None else None,
        "stop_hint": round(stop_hint, 4) if stop_hint is not None else None,
        "last_close": round(last_close, 4),
        "distance_to_neckline_pct": (round((level / last_close - 1.0) * 100.0, 2)
                                     if level else None),
        "target_pct": round((target / last_close - 1.0) * 100.0, 2) if target else None,
        "break_date": str(candles[break_index].get("time")) if break_index is not None else None,
        "break_volume_ratio": vol_ratio(candles, break_index) if break_index is not None else None,
        "move_progress_pct": None,
        "quality": int(max(0, min(100, quality))),
        "points": points or [],
        "start_date": (points[0]["time"] if points else None),
        "as_of": str(candles[-1].get("time")),
    }
    if status == "confirmed" and level and target and target != level:
        row["move_progress_pct"] = round(max(0.0, (last_close - level) / (target - level)) * 100.0, 1)
    if extra:
        row.update(extra)
    return row


LevelFn = Callable[[int], Optional[float]]
