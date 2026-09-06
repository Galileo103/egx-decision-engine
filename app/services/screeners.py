"""Screener services for the EGX Decision Engine.

Wraps the tradingview_mcp core scanners behind a uniform registry
(``SCANNERS``), a single dispatcher (``run_scanner``) and the flagship
``candidates()`` aggregation that merges hits across scanners, scores the
top merged symbols and ranks them.

All scanners run against EGX:
- batched scanners (volume breakout, smart volume, bollinger squeeze,
  consecutive candles) take the lowercase exchange key ``"egx"`` — that is
  how ``EXCHANGE_SCREENER``/``load_symbols`` resolve the "egypt" screener;
- ``analyze_coin`` takes ``"EGX"`` (case-insensitive helpers downstream);
- ``scan_egx_smart_money`` / ``screen_egx_stocks`` are EGX-only already.

No function in this module raises: failures are returned as
``{"error": ...}`` payloads (or, inside ``candidates()``, collected into a
``"scanner_errors"`` list).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from tradingview_mcp.core.errors import PartialDataError
from tradingview_mcp.core.services.egx_service import screen_egx_stocks
from tradingview_mcp.core.services.scanner_service import (
    smart_volume_scan,
    volume_breakout_scan,
)
from tradingview_mcp.core.services.screener_service import (
    analyze_coin,
    fetch_bollinger_analysis,
    scan_consecutive_candles,
)
from tradingview_mcp.core.services.smart_money_service import scan_egx_smart_money

logger = logging.getLogger(__name__)

# Lowercase key used by the batched core scanners (EXCHANGE_SCREENER["egx"]
# -> "egypt" screener; the uppercase form would fall back to "crypto").
_EGX_LOWER = "egx"
# Exchange identifier for single-symbol analysis (validators lowercase it).
_EGX_UPPER = "EGX"

# Bound on the number of merged symbols that get the expensive per-symbol
# analyze_coin() scoring pass inside candidates().
_SCORE_TOP_N = 15


# ── Registry ───────────────────────────────────────────────────────────────────

SCANNERS: dict[str, dict] = {
    "squeeze": {
        "label": "Bollinger Squeeze",
        "description": (
            "Stocks with compressed Bollinger Band width (BBW below bbw_max) — "
            "low-volatility coils that often precede expansion moves."
        ),
        "params": {"timeframe": "1D", "limit": 50, "bbw_max": 0.04},
    },
    "volume_breakout": {
        "label": "Volume Breakout",
        "description": (
            "Simultaneous volume surge (volume_multiplier x 20-bar average) "
            "and price move of at least price_change_min percent."
        ),
        "params": {
            "timeframe": "1D",
            "volume_multiplier": 2.0,
            "price_change_min": 3.0,
            "limit": 25,
        },
    },
    "smart_volume": {
        "label": "Smart Volume",
        "description": (
            "Volume breakouts filtered by RSI regime (oversold / overbought / "
            "neutral / any) with a trading recommendation per hit."
        ),
        "params": {
            "min_volume_ratio": 2.0,
            "min_price_change": 2.0,
            "rsi_range": "any",
            "limit": 20,
        },
    },
    "momentum": {
        "label": "Momentum Candles",
        "description": (
            "Strong directional candle today (body dominance, trend alignment, "
            "healthy RSI), then verified against real daily history: only "
            "symbols with candle_count consecutive closes in the pattern "
            "direction survive."
        ),
        "params": {
            "timeframe": "1D",
            "pattern_type": "bullish",
            "candle_count": 3,
            "min_growth": 1.0,
            "limit": 25,
        },
    },
    "smart_money": {
        "label": "Smart Money Flow",
        "description": (
            "EGX index constituents ranked by smart-money evidence "
            "(volume-flow composite, MCDX-style banker read, oscillator)."
        ),
        "params": {"index": "EGX30", "limit": 10, "period": "6mo", "min_score": 0.0},
    },
    "custom": {
        "label": "EGX Stock Screen",
        "description": (
            "Full EGX ranking engine: stock score, grade, trade setups and "
            "quality — screen_egx_stocks passthrough."
        ),
        "params": {"timeframe": "1D", "min_score": 55, "index_filter": "", "limit": 20},
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Current time as ISO string (Cairo when available, UTC otherwise)."""
    try:
        from app.calendar_egx import now_cairo

        return now_cairo().isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _coerce_params(defaults: dict[str, Any], provided: dict[str, Any]) -> dict[str, Any]:
    """Merge user params onto registry defaults, casting to the default's type.

    Unknown keys are ignored; values that fail to cast keep the default.
    """
    merged: dict[str, Any] = dict(defaults)
    for name, default in defaults.items():
        if name not in provided or provided[name] is None:
            continue
        value = provided[name]
        try:
            if isinstance(default, bool):
                merged[name] = str(value).strip().lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                merged[name] = int(float(value))
            elif isinstance(default, float):
                merged[name] = float(value)
            else:
                merged[name] = str(value)
        except (TypeError, ValueError):
            logger.warning("Scanner param %r=%r not coercible; using default %r",
                           name, value, default)
    return merged


def _bare_symbol(symbol: Optional[str]) -> str:
    """'EGX:COMI' / 'comi' -> 'COMI'."""
    if not symbol:
        return ""
    sym = str(symbol).strip().upper()
    if ":" in sym:
        sym = sym.split(":", 1)[-1]
    return sym


def _row_price_change(key: str, row: dict) -> tuple[Optional[float], Optional[float]]:
    """Best-effort (price, change_pct) extraction from one scanner row."""
    try:
        if key in ("squeeze", "volume_breakout", "smart_volume"):
            indicators = row.get("indicators") or {}
            return indicators.get("close"), row.get("changePercent")
        if key == "momentum":
            return row.get("price"), row.get("current_change")
        if key == "smart_money":
            return row.get("last_close"), None
        if key == "custom":
            return row.get("price"), row.get("change_pct")
        if key in ("range_breakout", "squeeze_breakout", "momentum_3", "pullback_trend"):
            return row.get("price"), row.get("change_pct")   # rule_scanner payload
    except Exception:
        pass
    return None, None


# ── Per-scanner runners ────────────────────────────────────────────────────────
# Each returns {"results": [...], "meta": {...}} or {"error": ...}.

def _run_squeeze(p: dict) -> dict:
    rows = fetch_bollinger_analysis(
        _EGX_LOWER,
        timeframe=p["timeframe"],
        limit=int(p["limit"]),
        bbw_filter=float(p["bbw_max"]),
    )
    return {"results": list(rows), "meta": {"bbw_max": p["bbw_max"]}}


def _run_volume_breakout(p: dict) -> dict:
    rows = volume_breakout_scan(
        _EGX_LOWER,
        timeframe=p["timeframe"],
        volume_multiplier=float(p["volume_multiplier"]),
        price_change_min=float(p["price_change_min"]),
        limit=int(p["limit"]),
    )
    return {"results": list(rows), "meta": {}}


def _run_smart_volume(p: dict) -> dict:
    rows = smart_volume_scan(
        _EGX_LOWER,
        min_volume_ratio=float(p["min_volume_ratio"]),
        min_price_change=float(p["min_price_change"]),
        rsi_range=str(p["rsi_range"]),
        limit=int(p["limit"]),
    )
    return {"results": list(rows), "meta": {}}


#: Cap on per-run Yahoo history lookups for consecutive-candle verification.
_MOMENTUM_VERIFY_MAX = 15


def _verify_consecutive(rows: list[dict], candle_count: int, pattern_type: str) -> tuple[list[dict], int]:
    """Check the scanner's single-bar hits against real daily history.

    The core scan inspects one completed bar; the "consecutive candles" claim
    is only true if the last ``candle_count`` daily closes actually step in
    the pattern's direction with matching bodies. Verified rows are kept and
    tagged, failures are dropped; rows beyond the Yahoo budget or with
    unavailable history are kept tagged ``consecutive_verified: None``.
    """
    if candle_count < 2 or pattern_type not in ("bullish", "bearish"):
        return rows, 0
    from app.services import history

    kept: list[dict] = []
    dropped = 0
    checked = 0
    for row in rows:
        sym = _bare_symbol(row.get("symbol"))
        if not sym or checked >= _MOMENTUM_VERIFY_MAX:
            row["consecutive_verified"] = None
            kept.append(row)
            continue
        checked += 1
        h = history.get_history(sym, "3mo", "1d")
        candles = h.get("candles") if isinstance(h, dict) else None
        if not candles or len(candles) < candle_count + 1:
            row["consecutive_verified"] = None
            kept.append(row)
            continue
        recent = candles[-candle_count:]
        prev_close = candles[-candle_count - 1]["close"]
        if pattern_type == "bullish":
            steps = all(recent[i]["close"] > recent[i - 1]["close"] for i in range(1, len(recent)))
            bodies = all(c["close"] > c["open"] for c in recent)
            ok = steps and bodies and recent[0]["close"] > prev_close
        else:
            steps = all(recent[i]["close"] < recent[i - 1]["close"] for i in range(1, len(recent)))
            bodies = all(c["close"] < c["open"] for c in recent)
            ok = steps and bodies and recent[0]["close"] < prev_close
        if ok:
            row["consecutive_verified"] = True
            kept.append(row)
        else:
            dropped += 1
    return kept, dropped


def _run_momentum(p: dict) -> dict:
    res = scan_consecutive_candles(
        _EGX_LOWER,
        p["timeframe"],
        str(p["pattern_type"]),
        int(p["candle_count"]),
        float(p["min_growth"]),
        int(p["limit"]),
    )
    if not isinstance(res, dict):
        return {"error": f"Unexpected momentum scan result: {res!r}"}
    if "error" in res:
        return {"error": res["error"]}
    rows = list(res.get("data") or [])
    dropped = 0
    if str(p["timeframe"]).upper() == "1D":
        rows, dropped = _verify_consecutive(
            rows, int(p["candle_count"]), str(p["pattern_type"])
        )
    meta = {k: v for k, v in res.items() if k != "data"}
    meta["consecutive_dropped"] = dropped
    return {"results": rows, "meta": meta}


def _run_smart_money(p: dict) -> dict:
    res = scan_egx_smart_money(
        index=str(p["index"]),
        limit=int(p["limit"]),
        period=str(p["period"]),
        min_score=float(p["min_score"]),
    )
    if not isinstance(res, dict):
        return {"error": f"Unexpected smart-money scan result: {res!r}"}
    if "error" in res:
        return {"error": res["error"]}
    meta = {k: v for k, v in res.items() if k != "rows"}
    return {"results": list(res.get("rows") or []), "meta": meta}


def _run_custom(p: dict) -> dict:
    res = screen_egx_stocks(
        timeframe=str(p["timeframe"]),
        min_score=int(p["min_score"]),
        index_filter=str(p["index_filter"]),
        limit=int(p["limit"]),
    )
    if not isinstance(res, dict):
        return {"error": f"Unexpected EGX screen result: {res!r}"}
    if "error" in res:
        return {"error": res["error"]}
    results: list[dict] = []
    for row in res.get("qualified_trades") or []:
        results.append({**row, "bucket": "qualified"})
    for row in res.get("watchlist") or []:
        results.append({**row, "bucket": "watchlist"})
    meta = {k: v for k, v in res.items() if k not in ("qualified_trades", "watchlist")}
    return {"results": results, "meta": meta}


_DISPATCH: dict[str, Callable[[dict], dict]] = {
    "squeeze": _run_squeeze,
    "volume_breakout": _run_volume_breakout,
    "smart_volume": _run_smart_volume,
    "momentum": _run_momentum,
    "smart_money": _run_smart_money,
    "custom": _run_custom,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def run_scanner(key: str, params: Optional[dict] = None) -> dict:
    """Run one registered scanner against EGX.

    Args:
        key:    Registry key from ``SCANNERS``.
        params: Optional overrides for the scanner's registered params
                (string values from query strings are coerced).

    Returns:
        ``{"scanner": key, "results": [...], "as_of": iso, "params": {...}}``
        plus scanner-specific ``"meta"``; ``"partial": True`` with a note when
        a batched scan aborted early but salvaged rows; or an error payload
        ``{"scanner": key, "error": ..., "as_of": iso}``. Never raises.
    """
    as_of = _now_iso()
    spec = SCANNERS.get(key)
    if spec is None:
        return {
            "scanner": key,
            "error": f"Unknown scanner '{key}'. Available: {', '.join(SCANNERS)}",
            "as_of": as_of,
        }

    merged = _coerce_params(spec["params"], params or {})

    try:
        outcome = _DISPATCH[key](merged)
    except PartialDataError as exc:
        # Batched scan aborted mid-flight but collected usable rows.
        return {
            "scanner": key,
            "results": list(getattr(exc, "rows", None) or []),
            "as_of": as_of,
            "params": merged,
            "partial": True,
            "note": str(exc),
        }
    except Exception as exc:  # BatchExecutionError, ScreenerServiceError, ...
        logger.warning("Scanner %s failed: %s", key, exc)
        return {"scanner": key, "error": str(exc), "as_of": as_of, "params": merged}

    if "error" in outcome:
        return {"scanner": key, "error": outcome["error"], "as_of": as_of, "params": merged}

    result = {
        "scanner": key,
        "results": outcome.get("results") or [],
        "as_of": as_of,
        "params": merged,
    }
    if outcome.get("meta"):
        result["meta"] = outcome["meta"]
    return result


# Default parameterisation used by candidates() for each contributing scanner.
# smart_money min_score is on the composite's 0-100 scale — 58 is the
# ACCUMULATION threshold; the old 0.5 was no filter at all, which handed the
# top-15 EGX30 names a free hit every day.
_CANDIDATE_RUNS: dict[str, dict[str, Any]] = {
    "squeeze": {"limit": 40, "bbw_max": 0.04},
    "volume_breakout": {"volume_multiplier": 1.8, "price_change_min": 2.0, "limit": 25},
    "smart_money": {"index": "EGX30", "limit": 15, "period": "6mo", "min_score": 58.0},
    "momentum": {"pattern_type": "bullish", "candle_count": 3, "min_growth": 1.0, "limit": 25},
}

# Signal families for candidate ranking. volume_breakout and momentum measure
# the SAME daily bar (a big up-day on volume trips both), so a raw hit count
# double-counts one piece of evidence; ranking counts distinct families.
_SCANNER_FAMILY: dict[str, str] = {
    "squeeze": "coil",
    "volume_breakout": "thrust",
    "momentum": "thrust",
    "smart_money": "flow",
    # The app's own candle rules (rule_scanner): a squeeze BREAKOUT is the coil
    # resolving, so it shares the coil family; the two thrust rules read the
    # same bar as volume_breakout/momentum; the pullback is its own idea.
    "squeeze_breakout": "coil",
    "range_breakout": "thrust",
    "momentum_3": "thrust",
    "pullback_trend": "pullback",
}


def _family_count(scanners: list[str]) -> int:
    return len({_SCANNER_FAMILY.get(s, s) for s in scanners})


def _evidence_weight(scanners: list[str], weights: dict[str, float]) -> float:
    """Track-record-weighted evidence: one term per signal FAMILY, using the
    best-performing scanner's weight inside that family (1.0 = no record yet).

    With no scorecard data every family weighs 1.0, so this equals
    ``_family_count`` and the ranking is unchanged until proof accumulates.
    """
    per_family: dict[str, float] = {}
    for s in scanners:
        fam = _SCANNER_FAMILY.get(s, s)
        w = float(weights.get(s, 1.0))
        per_family[fam] = max(per_family.get(fam, 0.0), w)
    return round(sum(per_family.values()), 2)


def _signal_weights(regime: Optional[str] = None, rvol_bucket: Optional[str] = None) -> dict[str, float]:
    try:
        from app.services import scorecard

        return scorecard.signal_weights(regime, rvol_bucket)
    except Exception as exc:  # noqa: BLE001 — ranking must never depend on the scorecard being healthy
        logger.warning("signal weights unavailable: %s", exc)
        return {}


def _rvol_bucket(value: Any) -> Optional[str]:
    from app.services.pattern_common import rvol_bucket

    return rvol_bucket(value)


def _rvol_for(symbol: str) -> Optional[float]:
    """Relative volume of the last completed session from the shared candle cache
    (None when the candles are not cached and cannot be fetched)."""
    try:
        from app.services import leaders
        from app.services.pattern_common import rvol

        return rvol(leaders.daily_candles(symbol))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rvol unavailable for %s: %s", symbol, exc)
        return None


def _weights_by_bucket(regime: Optional[str], base: dict[str, float]) -> dict[str, dict[str, float]]:
    """{bucket: weights} for the three relative-volume buckets ('' = unknown -> base)."""
    from app.services.pattern_common import RVOL_BUCKETS

    out: dict[str, dict[str, float]] = {"": base}
    for b in RVOL_BUCKETS:
        out[b] = _signal_weights(regime, b)
    return out


def _current_regime() -> Optional[str]:
    """Today's market regime for regime-conditional weights; None when unknown."""
    try:
        from app.services import regime

        return regime.current_state()
    except Exception as exc:  # noqa: BLE001
        logger.warning("regime unavailable: %s", exc)
        return None


def candidates(timeframe: str = "1D", persist: bool = False) -> dict:
    """Merged multi-scanner candidate list — the flagship screen.

    Runs squeeze + volume_breakout + smart_money + momentum with sane
    defaults, merges hits by symbol, scores the top ``_SCORE_TOP_N`` merged
    symbols via ``analyze_coin`` (stock score / signal / grade) and ranks by
    (hit_count, score).

    Args:
        timeframe: TradingView interval for the timeframe-aware scanners.
        persist:   When True, write one ``scanner_hits`` row per
                   (scanner, symbol) hit.

    Returns:
        ``{"candidates": [...], "as_of": iso, "scanner_errors": [...]}``.
        Individual scanner failures land in ``scanner_errors`` — this
        function never raises.
    """
    as_of = _now_iso()
    scanner_errors: list[dict] = []
    try:
        merged: dict[str, dict] = {}

        for key, overrides in _CANDIDATE_RUNS.items():
            run_params = dict(overrides)
            if "timeframe" in SCANNERS[key]["params"]:
                run_params["timeframe"] = timeframe
            try:
                res = run_scanner(key, run_params)
            except Exception as exc:  # defensive: run_scanner should not raise
                scanner_errors.append({"scanner": key, "error": str(exc)})
                continue
            if res.get("error"):
                scanner_errors.append({"scanner": key, "error": res["error"]})
                continue
            for row in res.get("results") or []:
                if not isinstance(row, dict):
                    continue
                # Candidates is a BULLISH shortlist: a -4% distribution day
                # trips volume_breakout too, and merging it in by symbol would
                # count it as a bullish confirmation.
                if key == "volume_breakout" and str(row.get("breakout_type") or "").lower() == "bearish":
                    continue
                sym = _bare_symbol(row.get("symbol"))
                if not sym:
                    continue
                entry = merged.setdefault(sym, {
                    "symbol": sym,
                    "scanners": [],
                    "payloads": {},
                    "price": None,
                    "change_pct": None,
                })
                if key not in entry["scanners"]:
                    entry["scanners"].append(key)
                entry["payloads"][key] = row
                price, change = _row_price_change(key, row)
                if entry["price"] is None and price is not None:
                    entry["price"] = price
                if entry["change_pct"] is None and change is not None:
                    entry["change_pct"] = change

        # The proven-rules scanner (Yahoo candles, no TradingView) journals its
        # hits for the session in the post-close job; merge the stored hits for
        # the same session so Candidates reflects both evidence sources.
        try:
            from app import calendar_egx
            from app.services import rule_scanner

            session = calendar_egx.last_trading_day(calendar_egx.now_cairo().date()).strftime("%Y-%m-%d")
            for hit in rule_scanner.stored_hits(session):
                sym = _bare_symbol(hit.get("symbol"))
                key = str(hit.get("scanner"))
                if not sym or key not in rule_scanner.RULES:
                    continue
                entry = merged.setdefault(sym, {"symbol": sym, "scanners": [], "payloads": {},
                                                "price": None, "change_pct": None})
                if key not in entry["scanners"]:
                    entry["scanners"].append(key)
                # already journaled by rule_scanner — do not re-persist a copy
                if entry["price"] is None and hit.get("price") is not None:
                    entry["price"] = hit["price"]
                if entry["change_pct"] is None and hit.get("change_pct") is not None:
                    entry["change_pct"] = hit["change_pct"]
                if entry.get("rvol") is None and hit.get("rvol") is not None:
                    entry["rvol"] = hit["rvol"]
        except Exception as exc:  # noqa: BLE001
            scanner_errors.append({"scanner": "proven_rules", "error": str(exc)})

        # Preliminary rank to decide which symbols earn the expensive
        # per-symbol scoring pass (bounded to _SCORE_TOP_N). Distinct signal
        # FAMILIES, not raw scanner count — see _SCANNER_FAMILY.
        ranked = sorted(
            merged.values(),
            key=lambda e: (_family_count(e["scanners"]), e["change_pct"] if e["change_pct"] is not None else 0.0),
            reverse=True,
        )

        for entry in ranked[:_SCORE_TOP_N]:
            entry["score"] = None
            entry["grade"] = None
            entry["signal"] = None
            entry["rating"] = None
            try:
                analysis = analyze_coin(entry["symbol"], _EGX_UPPER, timeframe)
            except Exception as exc:
                logger.warning("analyze_coin(%s) failed: %s", entry["symbol"], exc)
                continue
            if not isinstance(analysis, dict) or "error" in analysis:
                continue
            entry["score"] = analysis.get("stock_score")
            entry["grade"] = analysis.get("grade")
            sentiment = analysis.get("market_sentiment") or {}
            entry["signal"] = sentiment.get("buy_sell_signal")
            entry["rating"] = sentiment.get("overall_rating")
            price_data = analysis.get("price_data") or {}
            if price_data.get("current_price") is not None:
                entry["price"] = price_data["current_price"]
            if price_data.get("change_percent") is not None:
                entry["change_pct"] = price_data["change_percent"]

        regime_now = _current_regime()
        weights = _signal_weights(regime_now)
        # Relative volume of the session for each merged symbol (from the rule
        # scanner's payload, else the cached candles) and the volume-aware weights:
        # a breakout on heavy volume outranks a quiet one only where the record
        # says the volume mattered (scorecard.rvol_multipliers).
        for entry in ranked:
            if entry.get("rvol") is None:
                entry["rvol"] = _rvol_for(entry["symbol"])
        weights_by_bucket = _weights_by_bucket(regime_now, weights)

        def _w(e: dict) -> dict[str, float]:
            return weights_by_bucket.get(_rvol_bucket(e.get("rvol")) or "", weights)

        def _final_key(e: dict) -> tuple:
            score = e.get("score")
            return (
                _evidence_weight(e["scanners"], _w(e)),  # proven evidence first
                _family_count(e["scanners"]),              # independent evidence
                len(e["scanners"]),                        # raw hits break family ties
                score if isinstance(score, (int, float)) else -1.0,
                e["change_pct"] if e["change_pct"] is not None else 0.0,
            )

        ranked.sort(key=_final_key, reverse=True)

        # Liquidity gate: on EGX the tightest "setups" are often flatlined
        # illiquid names. Filter candidates whose 20-day median traded value
        # is KNOWN to be below the configured floor; unknown liquidity (thin
        # snapshots table) is kept and simply reported as null.
        from app.config import settings as _settings
        from app.services.market import median_daily_value as _mdv

        min_value = float(_settings.min_daily_value_egp)
        filtered_illiquid = 0

        out_rows: list[dict] = []
        for entry in ranked:
            liquidity = _mdv(entry["symbol"])
            if liquidity is not None and liquidity < min_value:
                filtered_illiquid += 1
                continue
            out_rows.append({
                "symbol": entry["symbol"],
                "scanners": entry["scanners"],
                "hit_count": len(entry["scanners"]),
                "family_count": _family_count(entry["scanners"]),
                "evidence_weight": _evidence_weight(entry["scanners"], _w(entry)),
                "rvol": entry.get("rvol"),
                "score": entry.get("score"),
                "grade": entry.get("grade"),
                "price": entry.get("price"),
                "change_pct": entry.get("change_pct"),
                "signal": entry.get("signal"),
                "rating": entry.get("rating"),
                "liquidity_egp": liquidity,
            })

        if persist and ranked:
            _persist_hits(ranked)

        scored = ranked[:_SCORE_TOP_N]
        scores_missing = sum(1 for e in scored if e.get("score") is None)
        return {
            "candidates": out_rows,
            "as_of": as_of,
            "timeframe": timeframe,
            "scanner_errors": scanner_errors,
            "scores_missing": scores_missing,
            "scores_expected": len(scored),
            "degraded": _degraded_note(scores_missing, len(scored), live=True),
            "scored_top_n": min(_SCORE_TOP_N, len(ranked)),
            "filtered_illiquid": filtered_illiquid,
            "min_daily_value_egp": min_value,
            "signal_weights": weights, "regime": regime_now,
            "ranking_basis": (
                "Ranked by track-record-weighted evidence (sum over signal families of the "
                "scanner's Scorecard weight; 1.0 until a scanner has enough graded hits), then "
                "family count, raw hits, score, change."
            ),
        }
    except Exception as exc:
        logger.exception("candidates() failed")
        return {
            "error": str(exc),
            "candidates": [],
            "as_of": as_of,
            "scanner_errors": scanner_errors,
        }


def _degraded_note(missing: int, expected: int, live: bool) -> Optional[str]:
    """Plain-language warning when the score/signal columns are blank.

    Blank is not zero: a missing score means TradingView returned no analysis
    (usually its rate limit), and the table is then ranked by scanner evidence
    alone. Say so instead of showing dashes and letting them look like data.
    """
    if expected <= 0 or missing <= 0:
        return None
    what = "This scan" if live else "This stored scan"
    if missing >= expected:
        head = f"{what} has NO scores or signals for any of the {expected} candidates"
    else:
        head = f"{what} is missing scores for {missing} of {expected} candidates"
    return (head + " — TradingView returned no analysis (rate limit). Ranking below is by "
            "scanner evidence only; a blank score means unknown, not weak. Rescan in a minute "
            "before acting on it.")


def latest_candidates(limit: int = 20) -> dict:
    """Candidates rebuilt from the most recent persisted scanner hits — instant,
    no upstream calls. The dashboard shows this first and offers a live rescan.
    Pattern hits (``pattern_*``) are excluded: they have their own tab."""
    try:
        from app import db

        d = db.query("SELECT MAX(date) AS d FROM scanner_hits WHERE scanner NOT LIKE 'pattern_%' "
                     "AND scanner NOT LIKE 'checklist_%' AND COALESCE(source, 'live') = 'live'")
        date = d[0].get("d") if d else None
        if not date:
            return {"candidates": [], "as_of": None, "stored": True, "count": 0}
        rows = db.query(
            "SELECT scanner, symbol, payload_json FROM scanner_hits "
            "WHERE date = ? AND scanner NOT LIKE 'pattern_%' AND scanner NOT LIKE 'checklist_%' "
            "AND COALESCE(source, 'live') = 'live'",
            (date,)
        )
        merged: dict[str, dict] = {}
        for r in rows:
            sym = _bare_symbol(r.get("symbol"))
            if not sym:
                continue
            try:
                payload = json.loads(r.get("payload_json") or "{}")
            except (TypeError, ValueError):
                payload = {}
            e = merged.setdefault(sym, {"symbol": sym, "scanners": [], "price": None, "change_pct": None,
                                        "score": None, "signal": None})
            key = str(r.get("scanner"))
            if key not in e["scanners"]:
                e["scanners"].append(key)
            if isinstance(payload, dict):
                price, change = _row_price_change(key, payload)
                if e["price"] is None and price is not None:
                    e["price"] = price
                if e["change_pct"] is None and change is not None:
                    e["change_pct"] = change
                for k in ("score", "stock_score"):
                    if e["score"] is None and isinstance(payload.get(k), (int, float)):
                        e["score"] = payload.get(k)
                if e["signal"] is None and isinstance(payload.get("signal"), str):
                    e["signal"] = payload.get("signal")
                if e.get("rvol") is None and isinstance(payload.get("rvol"), (int, float)):
                    e["rvol"] = payload.get("rvol")
        regime_now = _current_regime()
        weights = _signal_weights(regime_now)
        weights_by_bucket = _weights_by_bucket(regime_now, weights)
        out = []
        for e in merged.values():
            e["hit_count"] = len(e["scanners"])
            e["family_count"] = _family_count(e["scanners"])
            if e.get("rvol") is None:
                e["rvol"] = _rvol_for(e["symbol"])
            e["evidence_weight"] = _evidence_weight(
                e["scanners"], weights_by_bucket.get(_rvol_bucket(e.get("rvol")) or "", weights))
            out.append(e)
        out.sort(key=lambda e: (e["evidence_weight"], e["family_count"], e["hit_count"],
                                e["score"] if isinstance(e.get("score"), (int, float)) else -1.0),
                 reverse=True)
        shown = out[:max(1, int(limit))]
        scores_missing = sum(1 for e in shown if e.get("score") is None)
        return {"candidates": shown, "as_of": date, "stored": True,
                "count": len(out), "signal_weights": weights, "regime": regime_now,
                "scores_missing": scores_missing, "scores_expected": len(shown),
                "degraded": _degraded_note(scores_missing, len(shown), live=False)}
    except Exception as exc:
        return {"error": str(exc), "candidates": [], "stored": True}


def _persist_hits(entries: list[dict]) -> None:
    """Write one scanner_hits row per (scanner, symbol) hit. Best effort."""
    try:
        from app.calendar_egx import last_trading_day, now_cairo
        from app.db import execute

        now = now_cairo()
        # Stamp hits with the SESSION the data belongs to (same policy as
        # snapshots): a manual Friday run then dedupes against Thursday's
        # scheduled run instead of minting rows for a non-trading date.
        today = last_trading_day(now.date()).strftime("%Y-%m-%d")
        created = now.isoformat()
        for entry in entries:
            for scanner_key, payload in (entry.get("payloads") or {}).items():
                try:
                    # OR REPLACE + the unique (date, scanner, symbol) index:
                    # a manual run and the scheduled post-close run on the same
                    # day update one row instead of duplicating the whole day.
                    execute(
                        "INSERT OR REPLACE INTO scanner_hits "
                        "(date, scanner, symbol, payload_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (today, scanner_key, entry["symbol"],
                         json.dumps(payload, default=str), created),
                    )
                except Exception as exc:
                    logger.warning("Persist scanner hit %s/%s failed: %s",
                                   scanner_key, entry["symbol"], exc)
    except Exception as exc:
        logger.warning("Persisting scanner hits failed entirely: %s", exc)
