"""Market-level services for the EGX Decision Engine.

Wraps `tradingview_mcp.core` market functions with a short in-memory TTL
cache (60s — enough to survive an intraday dashboard refresh storm without
hammering the upstream screener) and adds session/breadth context.

All public functions return plain dicts and never raise: failures come back
as ``{"error": "..."}`` per the project contract.
"""
from __future__ import annotations

import bisect
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from tradingview_mcp.core.services import egx_service, yahoo_finance_service
from tradingview_mcp.core.services.indicators import compute_metrics, compute_stock_score
from tradingview_mcp.core.services.screener_provider import resilient_get_multiple_analysis
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER

from app import calendar_egx, db
from app import symbols as symbols_mod

# ── In-memory TTL cache ────────────────────────────────────────────────────────

_CACHE_TTL_S = 60.0
_cache: Dict[Tuple, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_BATCH_SIZE = 200
_EGX_SCREENER = EXCHANGE_SCREENER.get("egx", "egypt")


def _cache_get(key: Tuple) -> Optional[Any]:
    """Return a cached payload if present and younger than the TTL."""
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        ts, payload = hit
        if (time.time() - ts) > _CACHE_TTL_S:
            _cache.pop(key, None)
            return None
        return payload


def _cache_set(key: Tuple, payload: Any) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), payload)


def _as_of() -> str:
    """ISO timestamp in Cairo local time."""
    try:
        return calendar_egx.now_cairo().isoformat()
    except Exception:  # pragma: no cover — calendar module owned elsewhere
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


def _session() -> dict:
    try:
        return calendar_egx.session_state()
    except Exception as exc:
        return {"error": str(exc)}


# ── Public API ─────────────────────────────────────────────────────────────────

def overview(timeframe: str = "1D", limit: int = 10) -> dict:
    """EGX market overview: gainers/losers/most-active + breadth + session.

    Wraps ``egx_service.get_egx_market_overview`` and enriches the payload
    with a normalized ``breadth`` block, the current EGX ``session`` state,
    and an ``as_of`` timestamp. Cached for 60s.
    """
    try:
        key = ("overview", timeframe, limit)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        data = egx_service.get_egx_market_overview(timeframe=timeframe, limit=limit)
        if not isinstance(data, dict):
            return {"error": f"Unexpected overview payload type: {type(data).__name__}"}
        if "error" in data:
            return data

        stats = data.get("market_stats") or {}
        advancers = int(stats.get("advancing") or 0)
        decliners = int(stats.get("declining") or 0)
        unchanged = int(stats.get("unchanged") or 0)
        total = advancers + decliners + unchanged
        data["breadth"] = {
            "advancers": advancers,
            "decliners": decliners,
            "unchanged": unchanged,
            "pct_advancing": round(advancers / total * 100, 1) if total else 0.0,
        }
        data["session"] = _session()
        data["as_of"] = _as_of()
        _cache_set(key, data)
        return data
    except Exception as exc:
        return {"error": str(exc)}


def index_analysis(index: str = "EGX30", timeframe: str = "1D") -> dict:
    """Constituent-level analysis of an EGX index (EGX30/EGX70/EGX100/...)."""
    try:
        key = ("index", index.strip().upper(), timeframe)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        data = egx_service.analyze_egx_index(index=index, timeframe=timeframe)
        if not isinstance(data, dict):
            return {"error": f"Unexpected index payload type: {type(data).__name__}"}
        if "error" in data:
            return data

        data["as_of"] = _as_of()
        _cache_set(key, data)
        return data
    except Exception as exc:
        return {"error": str(exc)}


def sectors(timeframe: str = "1D") -> dict:
    """Full EGX sector-rotation scan (heatmap, top picks, rotation signals)."""
    try:
        key = ("sectors", timeframe)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        data = egx_service.run_egx_sector_scanner(timeframe=timeframe)
        if not isinstance(data, dict):
            return {"error": f"Unexpected sectors payload type: {type(data).__name__}"}
        if "error" in data:
            return data

        data["as_of"] = _as_of()
        _cache_set(key, data)
        return data
    except Exception as exc:
        return {"error": str(exc)}


def sector_detail(sector: str, timeframe: str = "1D") -> dict:
    """Per-stock detail for one EGX sector (or the sector list when empty)."""
    try:
        data = egx_service.scan_egx_sector(sector=sector or "", timeframe=timeframe)
        if not isinstance(data, dict):
            return {"error": f"Unexpected sector payload type: {type(data).__name__}"}
        if "error" not in data:
            data["as_of"] = _as_of()
        return data
    except Exception as exc:
        return {"error": str(exc)}


def global_snapshot() -> dict:
    """Global macro snapshot (US indices, crypto, FX, ETFs) via Yahoo."""
    try:
        data = yahoo_finance_service.get_market_snapshot()
        if not isinstance(data, dict):
            return {"error": f"Unexpected snapshot payload type: {type(data).__name__}"}
        data["as_of"] = _as_of()
        return data
    except Exception as exc:
        return {"error": str(exc)}


# ── Universe snapshot persistence ──────────────────────────────────────────────

def _normalized_universe(universe_name: str) -> List[str]:
    """Resolve a universe name to a deduplicated, EGX-prefixed symbol list."""
    raw = symbols_mod.universe(universe_name)
    seen: set = set()
    out: List[str] = []
    for s in raw or []:
        sym = (s or "").strip().upper()
        if not sym:
            continue
        full = sym if ":" in sym else f"EGX:{sym}"
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def _fetch_universe_indicators(symbols: List[str], timeframe: str) -> Tuple[Dict[str, dict], int]:
    """Batch-fetch TA indicators for a symbol list (batches of 200, EGX screener).

    Returns (symbol -> indicators dict, batches_failed). Indicator dicts are
    shallow-copied so cached provider objects are never mutated.
    """
    fetched: Dict[str, dict] = {}
    batches_failed = 0
    for i in range(0, len(symbols), _BATCH_SIZE):
        batch = symbols[i : i + _BATCH_SIZE]
        try:
            analysis = resilient_get_multiple_analysis(
                screener=_EGX_SCREENER, interval=timeframe, symbols=batch
            )
        except Exception:
            batches_failed += 1
            continue
        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                fetched[sym] = dict(data.indicators)
            except Exception:
                continue
    return fetched, batches_failed


def _get_currency(symbol: str) -> str:
    try:
        from tradingview_mcp.core.data.egx_sectors import get_currency

        return get_currency(symbol) or "EGP"
    except Exception:
        return "EGP"


def median_daily_value(symbol: str, days: int = 20) -> Optional[float]:
    """Median daily traded value (price × volume, EGP) over recent snapshots.

    Returns None when fewer than 5 usable rows exist — early on the snapshots
    table is thin, and "unknown" must never be read as "illiquid".
    """
    try:
        bare = str(symbol or "").strip().upper().split(":")[-1]
        if not bare:
            return None
        rows = db.query(
            "SELECT price, volume FROM snapshots WHERE symbol = ? AND timeframe = '1D' "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (bare, int(days)),
        )
        vals = sorted(
            float(r["price"]) * float(r["volume"])
            for r in rows
            if r.get("price") and r.get("volume")
        )
        if len(vals) < 5:
            return None
        mid = len(vals) // 2
        med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
        return round(med, 0)
    except Exception:
        return None


#: Yahoo symbol for the EGX 30 price index.
_EGX30_YAHOO = "^CASE30"


def snapshot_egx30_index() -> dict:
    """Persist one EGX30 index-level row per session into ``snapshots``.

    Stored under symbol 'EGX30' so the portfolio page can answer the one
    question that tempers overtrading: did all this activity beat simply
    holding the index? Runs in the post-close job; safe to call repeatedly
    (INSERT OR REPLACE on the session date).
    """
    try:
        quote = yahoo_finance_service.get_price(_EGX30_YAHOO)
        if not isinstance(quote, dict) or "error" in quote or quote.get("price") is None:
            err = quote.get("error") if isinstance(quote, dict) else "no data"
            return {"error": f"EGX30 index quote unavailable: {err}"}
        price = float(quote["price"])
        now = calendar_egx.now_cairo()
        date_str = calendar_egx.last_trading_day(now.date()).strftime("%Y-%m-%d")
        db.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(symbol, date, timeframe, price, created_at) VALUES (?, ?, ?, ?, ?)",
            ("EGX30", date_str, "1D", price, now.isoformat()),
        )
        return {"saved": 1, "symbol": "EGX30", "date": date_str, "price": price,
                "source": str(quote.get("price_source") or "yahoo")}
    except Exception as exc:
        return {"error": str(exc)}


def snapshot_universe(universe_name: str = "EGX100", timeframe: str = "1D") -> dict:
    """Snapshot every symbol in a universe into the ``snapshots`` table.

    Batch-fetches indicators (200 symbols per screener call), computes
    metrics + composite stock score (with cross-sectional change percentile
    ranks, mirroring egx_service), and persists one row per symbol via
    INSERT OR REPLACE keyed on (symbol, date, timeframe). Date is the most
    recent trading session (Cairo), so holiday/weekend runs never fabricate
    rows for non-trading dates.

    Returns ``{"saved": n, "date": ..., ...}`` or ``{"error": ...}``.
    """
    try:
        prefixed = _normalized_universe(universe_name)
        if not prefixed:
            return {"error": f"Unknown or empty universe: {universe_name}"}

        fetched, batches_failed = _fetch_universe_indicators(prefixed, timeframe)
        if not fetched:
            return {
                "error": f"No data returned for universe {universe_name}",
                "universe": universe_name,
                "timeframe": timeframe,
                "batches_failed": batches_failed,
            }

        # Cross-sectional percentile ranks of today's change, for scoring.
        changes: Dict[str, float] = {}
        for sym, ind in fetched.items():
            o = ind.get("open")
            c = ind.get("close")
            if o and c and o > 0:
                changes[sym] = ((c - o) / o) * 100
        ordered = sorted(changes.values())
        n_changes = len(ordered)

        def _pct_rank(val: float) -> float:
            if n_changes == 0:
                return 0.5
            return bisect.bisect_left(ordered, val) / n_changes

        now = calendar_egx.now_cairo()
        # Stamp rows with the session the data belongs to, not the wall-clock
        # date — a manual snapshot on a Friday/holiday otherwise fabricates
        # rows for a non-trading date and pads signal/score history.
        date_str = calendar_egx.last_trading_day(now.date()).strftime("%Y-%m-%d")
        created_at = now.isoformat()

        saved = 0
        skipped = 0
        pending: list[tuple] = []
        for sym, ind in fetched.items():
            metrics = compute_metrics(ind)
            if not metrics:
                skipped += 1
                continue

            score: Optional[float] = None
            score_json: Optional[str] = None
            try:
                rank = _pct_rank(changes[sym]) if sym in changes else None
                result = compute_stock_score(
                    ind, change_pct_rank=rank, currency=_get_currency(sym)
                )
                if result:
                    score = result.get("score")
                    score_json = json.dumps(
                        {
                            "score": result.get("score"),
                            "grade": result.get("grade"),
                            "trend_state": result.get("trend_state"),
                            "breakdown": result.get("breakdown"),
                            "signals": result.get("signals"),
                            "penalties": result.get("penalties"),
                        },
                        default=str,
                    )
            except Exception:
                pass  # score stays NULL — row is still worth persisting

            rsi_raw = ind.get("RSI")
            rsi = round(float(rsi_raw), 2) if isinstance(rsi_raw, (int, float)) else None
            bare = sym.split(":", 1)[-1]

            pending.append((
                bare,
                date_str,
                timeframe,
                metrics.get("price"),
                metrics.get("change"),
                ind.get("volume"),
                rsi,
                metrics.get("bbw"),
                metrics.get("rating"),
                metrics.get("signal"),
                score,
                score_json,
                created_at,
            ))

        # One transaction for the whole universe: no partial dates on a crash,
        # one lock hold instead of ~380, and no fsync storm against live reads.
        db_error: Optional[str] = None
        if pending:
            try:
                db.executemany(
                    "INSERT OR REPLACE INTO snapshots "
                    "(symbol, date, timeframe, price, change_pct, volume, rsi, bbw, "
                    " rating, signal, score, score_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    pending,
                )
                saved = len(pending)
            except Exception as exc:
                # A DB failure is NOT the same as thin metrics — report it.
                db_error = str(exc)

        if db_error:
            return {
                "error": f"snapshot persistence failed: {db_error}",
                "universe": universe_name,
                "timeframe": timeframe,
                "total_fetched": len(fetched),
            }

        return {
            "saved": saved,
            "skipped": skipped,
            "date": date_str,
            "universe": universe_name,
            "timeframe": timeframe,
            "total_fetched": len(fetched),
            "batches_failed": batches_failed,
            "as_of": created_at,
        }
    except Exception as exc:
        return {"error": str(exc)}
