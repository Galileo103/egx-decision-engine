"""Support & resistance zones from the daily chart.

Levels come from four sources, merged and ranked:
  * swing highs/lows over the last year, clustered within 0.75 x ATR — a
    zone's strength grows with how many times it was tested, how recently,
    and how much volume traded at those touches;
  * the 52-week high and low;
  * round numbers near the price (traders anchor on them);
  * moving averages (SMA50 / SMA200) as dynamic levels.

The result names the nearest support and resistance, says where price sits
(at support / at resistance / mid-range / breaking out) and hands the trade
plan two checks: a stop parked just above a tested support belongs below it,
and a target sitting just under a tested resistance is optimistic.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.pattern_common import atr as _atr, f as _f, sma as _sma, swing_points

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

CLUSTER_ATR = 0.75      # swing points within this many ATR form one zone
AT_LEVEL_ATR = 1.0      # "at support/resistance" when within this many ATR
LOOKBACK = 250


def _round_step(price: float) -> float:
    """Psychological step for the price magnitude (17.8 → 1; 120 → 5; 1.4 → 0.1)."""
    if price <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(price))
    rel = price / mag
    return mag * (0.1 if rel < 2 else (0.25 if rel < 5 else 0.5))


def compute(symbol: str, candles: Optional[list[dict]] = None) -> dict:
    """Levels for one symbol. Never raises."""
    try:
        sym = str(symbol or "").upper().strip().split(":")[-1]
        if candles is None:
            from app.services import leaders

            candles = leaders.daily_candles(sym)
        if len(candles) < 60:
            return {"symbol": sym, "error": "not enough daily history (need 60+ bars)", "supports": [],
                    "resistances": []}
        window = candles[-LOOKBACK:]
        n = len(window)
        closes = [float(c["close"]) for c in window]
        highs = [_f(c.get("high")) or 0.0 for c in window]
        lows = [_f(c.get("low")) or 0.0 for c in window]
        vols = [_f(c.get("volume")) or 0.0 for c in window]
        price = closes[-1]
        atr = _atr(window) or max(price * 0.02, 1e-9)
        avg_vol = (sum(vols[-60:]) / max(1, len(vols[-60:]))) or 1.0

        sh, sl = swing_points(window, k=3)
        pts = [(i, p, "high") for i, p in sh] + [(i, p, "low") for i, p in sl]
        pts.sort(key=lambda t: t[1])
        clusters: list[dict] = []
        for i, p, kind in pts:
            if clusters and abs(p - clusters[-1]["prices"][-1]) <= CLUSTER_ATR * atr:
                cl = clusters[-1]
            else:
                cl = {"prices": [], "idx": [], "kinds": [], "vol": []}
                clusters.append(cl)
            cl["prices"].append(p)
            cl["idx"].append(i)
            cl["kinds"].append(kind)
            cl["vol"].append(vols[i])
        levels: list[dict] = []
        for cl in clusters:
            w = [max(v / avg_vol, 0.2) for v in cl["vol"]]
            level = sum(p * wi for p, wi in zip(cl["prices"], w)) / sum(w)
            touches = len(cl["prices"])
            last_idx = max(cl["idx"])
            recency = 1.0 - (n - 1 - last_idx) / n          # 1 = touched today, 0 = a year ago
            vol_w = min(2.0, sum(w) / touches)                # volume at the touches vs normal
            strength = touches * 1.0 + recency * 1.5 + vol_w * 0.5
            levels.append({
                "level": round(level, 4), "source": "swings", "touches": touches,
                "last_touch": str(window[last_idx]["time"]), "recency": round(recency, 2),
                "volume_weight": round(vol_w, 2), "strength": round(strength, 2),
                "kinds": {"highs": cl["kinds"].count("high"), "lows": cl["kinds"].count("low")},
            })
        hi52, lo52 = max(highs), min(lows)
        levels.append({"level": round(hi52, 4), "source": "52w high", "touches": 1, "strength": 2.0,
                       "last_touch": str(window[highs.index(hi52)]["time"])})
        levels.append({"level": round(lo52, 4), "source": "52w low", "touches": 1, "strength": 2.0,
                       "last_touch": str(window[lows.index(lo52)]["time"])})
        step = _round_step(price)
        base = math.floor(price / step) * step
        for k in range(-3, 4):
            rn = round(base + k * step, 4)
            if rn > 0 and abs(rn - price) / price <= 0.15:
                levels.append({"level": rn, "source": "round number", "touches": 0, "strength": 0.6,
                               "last_touch": None})
        for name, per in (("SMA50", 50), ("SMA200", 200)):
            s = _sma(closes, per)
            if s:
                levels.append({"level": round(s, 4), "source": name, "touches": 0, "strength": 1.2,
                               "last_touch": None, "dynamic": True})

        # Merge near-duplicates (a swing zone sitting on a round number).
        levels.sort(key=lambda l: l["level"])
        merged: list[dict] = []
        for lv in levels:
            if merged and abs(lv["level"] - merged[-1]["level"]) <= 0.35 * atr:
                keep = merged[-1] if merged[-1]["strength"] >= lv["strength"] else lv
                keep = dict(keep)
                keep["strength"] = round(merged[-1]["strength"] + lv["strength"] * 0.5, 2)
                keep["source"] = merged[-1]["source"] if merged[-1]["source"] == keep["source"] else keep["source"] + " + " + (lv["source"] if keep is not lv else merged[-1]["source"])
                merged[-1] = keep
            else:
                merged.append(dict(lv))
        for lv in merged:
            lv["distance_pct"] = round((lv["level"] / price - 1.0) * 100.0, 2)
            lv["distance_atr"] = round((lv["level"] - price) / atr, 2)
        supports = sorted([l for l in merged if l["level"] < price], key=lambda l: -l["level"])
        resistances = sorted([l for l in merged if l["level"] >= price], key=lambda l: l["level"])
        # Round numbers are anchors, not walls: the "nearest" levels used for
        # position and room must be tested zones, 52-week extremes or averages.
        meaningful = lambda l: l["source"] != "round number"  # noqa: E731
        near_s = next((l for l in supports if meaningful(l)), supports[0] if supports else None)
        near_r = next((l for l in resistances if meaningful(l)), resistances[0] if resistances else None)
        # Strongest tested zones (swing clusters with >= 2 touches) for the chart.
        key_levels = sorted([l for l in merged if l.get("touches", 0) >= 2], key=lambda l: -l["strength"])[:6]

        if near_r and (near_r["level"] - price) <= AT_LEVEL_ATR * atr and near_r.get("touches", 0) >= 2:
            where, note = "at resistance", (f"Price is within {near_r['distance_atr']:+.1f} ATR of a resistance "
                                            f"tested {near_r['touches']}x at {near_r['level']:.2f}. Buying here "
                                            "means buying into sellers; wait for the break or the pullback.")
        elif near_s and (price - near_s["level"]) <= AT_LEVEL_ATR * atr and near_s.get("touches", 0) >= 2:
            where, note = "at support", (f"Price sits on a support tested {near_s['touches']}x at "
                                         f"{near_s['level']:.2f} ({near_s['distance_atr']:+.1f} ATR). The classic "
                                         "low-risk spot: a stop just below it keeps the risk small.")
        elif not resistances or (near_r and near_r["source"] == "round number" and not any(
                l.get("touches", 0) >= 1 for l in resistances)):
            where, note = "breaking out", "No tested resistance overhead within the last year — price is in open air."
        else:
            where, note = "mid-range", (f"Price is between support {near_s['level']:.2f} ({near_s['source']}) and "
                                        f"resistance {near_r['level']:.2f} ({near_r['source']})."
                                        if near_s and near_r else "Price is between levels.")
        return {
            "symbol": sym, "price": round(price, 4), "atr14": round(atr, 4),
            "supports": supports[:6], "resistances": resistances[:6], "key_levels": key_levels,
            "nearest_support": near_s, "nearest_resistance": near_r,
            "room_up_pct": round((near_r["level"] / price - 1) * 100, 2) if near_r else None,
            "room_down_pct": round((1 - near_s["level"] / price) * 100, 2) if near_s else None,
            "position": where, "note": note,
            "as_of": str(window[-1]["time"]),
            "basis": ("Zones = clusters of swing highs/lows (window 3) within 0.75 ATR over the last year, "
                      "strength = touches + recency + volume at the touches; plus 52-week extremes, round "
                      "numbers near price, SMA50/SMA200."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("levels.compute failed")
        return {"symbol": symbol, "error": str(exc), "supports": [], "resistances": []}


def plan_checks(levels: dict, stop: Optional[float], targets: list[Optional[float]]) -> list[str]:
    """Advisory sentences about a stop/targets relative to tested zones."""
    out: list[str] = []
    try:
        if not levels or "error" in levels:
            return out
        atr = float(levels.get("atr14") or 0) or 1e-9
        tested = [l for l in levels.get("supports", []) + levels.get("resistances", []) if l.get("touches", 0) >= 2]
        if stop is not None:
            for l in tested:
                if 0 < stop - l["level"] <= 0.75 * atr:
                    out.append(f"Your stop {stop:.2f} sits just ABOVE a support tested {l['touches']}x at "
                               f"{l['level']:.2f} — the level will likely be probed before it holds. Put the "
                               f"stop below it (about {l['level'] - 0.5 * atr:.2f}).")
                    break
        for i, t in enumerate(targets, 1):
            if t is None:
                continue
            for l in tested:
                if 0 < l["level"] - t <= 0.75 * atr or 0 <= t - l["level"] <= 0.25 * atr:
                    out.append(f"Target {i} ({t:.2f}) sits right at a resistance tested {l['touches']}x at "
                               f"{l['level']:.2f}. Expect sellers there — consider taking profit a little "
                               f"before it ({l['level'] - 0.3 * atr:.2f}).")
                    break
    except Exception:  # noqa: BLE001
        return out
    return out
