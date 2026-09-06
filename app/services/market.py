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
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from tradingview_mcp.core.services import egx_service, yahoo_finance_service
from tradingview_mcp.core.services.indicators import compute_metrics, compute_stock_score
from tradingview_mcp.core.services.screener_provider import resilient_get_multiple_analysis
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER

from app import calendar_egx, db
from app import symbols as symbols_mod

logger = logging.getLogger(__name__)

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


def _num(value: Any) -> Optional[float]:
    """Float or None — rejects NaN, which SQLite stores but arithmetic poisons."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


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


#: The Egypt row: one tile per instrument. ``spot`` is a TradingView symbol
#: (screener, symbol) — the price a TradingView user sees on UKOIL / XAUUSD /
#: XAGUSD / DXY; ``futures`` is the Yahoo front-month contract shown alongside.
#: ``spot_fallback`` is a Yahoo symbol used when TradingView is unavailable;
#: ``futures_tv`` is the TradingView front-month contract used when Yahoo misses.
EGYPT_INSTRUMENTS: tuple[dict, ...] = (
    {"key": "usdegp", "name": "USD / EGP", "unit": "EGP per dollar",
     "spot": ("forex", "FX_IDC:USDEGP"), "spot_fallback": "EGP=X", "futures": None},
    {"key": "dxy", "name": "Dollar index", "unit": "DXY",
     "spot": ("cfd", "TVC:DXY"), "spot_fallback": "DX-Y.NYB", "futures": None},
    {"key": "brent", "name": "Brent oil", "unit": "USD / barrel",
     "spot": ("cfd", "FX:UKOIL"), "spot_fallback": None, "futures": "BZ=F",
     "futures_tv": ("futures", "NYMEX:BZ1!")},
    {"key": "gold", "name": "Gold", "unit": "USD / oz",
     "spot": ("cfd", "TVC:GOLD"), "spot_fallback": None, "futures": "GC=F",
     "futures_tv": ("futures", "COMEX:GC1!")},
    {"key": "silver", "name": "Silver", "unit": "USD / oz",
     "spot": ("cfd", "TVC:SILVER"), "spot_fallback": None, "futures": "SI=F",
     "futures_tv": ("futures", "COMEX:SI1!")},
)

#: Ticker -> what it is. Shown to the reader instead of the raw Yahoo code.
GLOBAL_LABELS: Dict[str, Dict[str, str]] = {
    "FX_IDC:USDEGP": {"name": "USD / EGP", "unit": "EGP per dollar",
                     "what": "Egyptian pounds per US dollar (TradingView spot). Up = the pound weakened. The "
                             "single biggest driver of EGX earnings, foreign flows and import-cost names."},
    "TVC:DXY": {"name": "Dollar index", "unit": "DXY",
                "what": "US dollar against six major currencies. A rising DXY pulls money out of emerging "
                        "markets and pressures the pound; a falling DXY is a tailwind for EGX."},
    "DX-Y.NYB": {"name": "Dollar index", "unit": "DXY",
                 "what": "US dollar against six major currencies (Yahoo). A rising DXY pulls money out of "
                         "emerging markets and pressures the pound."},
    "FX:UKOIL": {"name": "Brent oil", "unit": "USD / barrel",
                 "what": "Brent crude spot (TradingView UKOIL). Moves petrochemical, energy and fertiliser "
                         "names, and Egypt's import bill. The futures figure is the front-month contract."},
    "TVC:GOLD": {"name": "Gold", "unit": "USD / oz",
                 "what": "Gold spot (TradingView XAUUSD). Local savers switch between gold, dollars and "
                         "stocks; a gold spike often means risk-off. Futures usually trade a little above spot."},
    "TVC:SILVER": {"name": "Silver", "unit": "USD / oz",
                   "what": "Silver spot (TradingView XAGUSD). Follows gold with more swing."},
    "EGP=X": {"name": "USD / EGP", "unit": "EGP per dollar",
              "what": "Egyptian pounds per US dollar. Up = the pound weakened. The single biggest driver "
                      "of EGX earnings, foreign flows and import-cost names."},
    "BZ=F": {"name": "Brent oil", "unit": "USD / barrel",
             "what": "Brent crude futures. Moves petrochemical, energy and fertiliser names, and Egypt's "
                     "import bill."},
    "GC=F": {"name": "Gold", "unit": "USD / oz",
             "what": "Gold futures. Local savers switch between gold, dollars and stocks; a gold spike "
                     "often means risk-off."},
    "SI=F": {"name": "Silver", "unit": "USD / oz",
             "what": "Silver futures. Follows gold with more swing; a metals read for the same crowd."},
    "^GSPC": {"name": "S&P 500", "unit": "index", "what": "500 largest US companies — the world's risk barometer."},
    "^DJI": {"name": "Dow Jones", "unit": "index", "what": "30 large US industrials."},
    "^IXIC": {"name": "Nasdaq", "unit": "index", "what": "US technology-heavy index."},
    "^VIX": {"name": "VIX fear index", "unit": "index",
             "what": "Expected US volatility. Above 20 = nervous markets, foreign money leaves emerging markets first."},
    "BTC-USD": {"name": "Bitcoin", "unit": "USD", "what": "Largest crypto asset — a global risk-appetite gauge."},
    "ETH-USD": {"name": "Ether", "unit": "USD", "what": "Second-largest crypto asset."},
    "SOL-USD": {"name": "Solana", "unit": "USD", "what": "Crypto asset."},
    "BNB-USD": {"name": "BNB", "unit": "USD", "what": "Crypto asset."},
    "EURUSD=X": {"name": "EUR / USD", "unit": "dollars per euro", "what": "Euro against the dollar."},
    "GBPUSD=X": {"name": "GBP / USD", "unit": "dollars per pound", "what": "Sterling against the dollar."},
    "JPYUSD=X": {"name": "JPY / USD", "unit": "dollars per yen", "what": "Yen against the dollar."},
    "SPY": {"name": "S&P 500 ETF", "unit": "USD", "what": "Tradable S&P 500 fund."},
    "QQQ": {"name": "Nasdaq-100 ETF", "unit": "USD", "what": "Tradable Nasdaq-100 fund."},
    "GLD": {"name": "Gold ETF", "unit": "USD", "what": "Gold-backed fund (about a tenth of an ounce per share)."},
}

GROUP_LABELS: Dict[str, str] = {
    "egypt": "Egypt & commodities", "indices": "US indices", "etfs": "US funds",
    "fx": "Currencies", "crypto": "Crypto",
}
GROUP_ORDER: tuple[str, ...] = ("egypt", "indices", "etfs", "fx", "crypto")


def _tv_spot_quotes(pairs: List[Tuple[str, str]]) -> Dict[str, dict]:
    """{symbol: {price, change_pct}} from TradingView for (screener, symbol) pairs.
    One scanner call per screener; failures leave symbols out (never raises)."""
    out: Dict[str, dict] = {}
    by_screener: Dict[str, List[str]] = {}
    for screener, sym in pairs:
        by_screener.setdefault(screener, []).append(sym)
    for screener, syms in by_screener.items():
        try:
            res = resilient_get_multiple_analysis(screener=screener, interval="1d", symbols=syms)
        except Exception:  # noqa: BLE001 - TradingView pause: fall back to Yahoo below
            continue
        analyses = res[0] if isinstance(res, tuple) else res
        for sym, a in (analyses or {}).items():
            ind = getattr(a, "indicators", None)
            if ind is None and isinstance(a, dict):
                ind = a.get("indicators")
            if not isinstance(ind, dict) or ind.get("close") is None:
                continue
            chg = ind.get("change")
            out[str(sym).upper()] = {"price": round(float(ind["close"]), 4),
                                     "change_pct": round(float(chg), 2) if chg is not None else None}
    return out


def _yahoo_quote(sym: str) -> Optional[dict]:
    try:
        q = yahoo_finance_service.get_price(sym)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(q, dict) or "error" in q or q.get("price") is None:
        return None
    return {"symbol": str(q.get("symbol") or sym).upper(), "price": q.get("price"),
            "change_pct": q.get("change_pct"), "currency": q.get("currency")}


def egypt_row() -> List[dict]:
    """Spot (TradingView) and futures (Yahoo) side by side for the Egypt tiles.

    Each tile: the spot quote is primary (what a TradingView chart shows); the
    front-month futures quote rides along as ``futures``. When TradingView is
    pausing, the Yahoo fallback (or the futures quote itself) becomes primary and
    ``source`` says so — a tile never silently changes meaning.
    """
    spots = _tv_spot_quotes([i["spot"] for i in EGYPT_INSTRUMENTS if i.get("spot")])
    rows: List[dict] = []
    for inst in EGYPT_INSTRUMENTS:
        screener, tv_sym = inst["spot"]
        spot = spots.get(tv_sym.upper())
        futures = _yahoo_quote(inst["futures"]) if inst.get("futures") else None
        if futures:
            futures["source"] = "Yahoo futures (front month)"
            futures["kind"] = "futures"
        elif inst.get("futures_tv"):
            tv_fut = _tv_spot_quotes([inst["futures_tv"]]).get(inst["futures_tv"][1].upper())
            if tv_fut:
                futures = {"symbol": inst["futures_tv"][1], "price": tv_fut["price"],
                           "change_pct": tv_fut["change_pct"], "currency": "USD",
                           "source": "TradingView futures (front month)", "kind": "futures"}
        primary: Optional[dict] = None
        if spot:
            primary = {"symbol": tv_sym, "price": spot["price"], "change_pct": spot["change_pct"],
                       "currency": "USD" if inst["key"] != "usdegp" else "EGP",
                       "source": "TradingView spot", "kind": "spot"}
        elif inst.get("spot_fallback"):
            fb = _yahoo_quote(inst["spot_fallback"])
            if fb:
                primary = {**fb, "source": "Yahoo (TradingView unavailable)", "kind": "spot"}
        if primary is None and futures:
            primary = {**futures, "source": "Yahoo futures (spot unavailable)"}
            futures = None
        if primary is None:
            continue
        row = _labelled(primary)
        row["name"], row["unit"] = inst["name"], inst["unit"]
        if not row.get("what"):
            row["what"] = (GLOBAL_LABELS.get(tv_sym) or {}).get("what")
        row["key"] = inst["key"]
        row["futures"] = futures
        rows.append(row)
    return rows


def _labelled(row: dict) -> dict:
    sym = str(row.get("symbol") or "").upper()
    meta = GLOBAL_LABELS.get(sym) or {}
    out = dict(row)
    out["name"] = meta.get("name") or sym
    out["unit"] = meta.get("unit")
    out["what"] = meta.get("what")
    return out


def global_snapshot() -> dict:
    """Global macro snapshot via Yahoo: the core library's US indices / crypto / FX /
    ETF groups, plus an Egypt-relevant group (USD/EGP, Brent, gold, silver). Every
    row carries a readable ``name``, a ``unit`` and a one-line ``what`` so the UI
    never has to show a bare Yahoo ticker.
    """
    try:
        data = yahoo_finance_service.get_market_snapshot()
        if not isinstance(data, dict):
            return {"error": f"Unexpected snapshot payload type: {type(data).__name__}"}
        data["egypt"] = egypt_row()
        for group in GROUP_ORDER:
            rows = data.get(group)
            if isinstance(rows, list) and group != "egypt":
                data[group] = [_labelled(r) for r in rows if isinstance(r, dict)]
        data["groups"] = [{"key": g, "label": GROUP_LABELS.get(g, g), "rows": data.get(g) or []}
                          for g in GROUP_ORDER if isinstance(data.get(g), list)]
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


def held_and_watched_symbols() -> List[str]:
    """Open-position + watchlist symbols, EGX-prefixed. Never raises.

    The Guardian's thesis check compares today's snapshot with the one you
    bought on; a held stock outside the scanned universe had no snapshot at
    all, so the check silently never ran. Every snapshot now includes what
    you hold and watch, whatever the universe.
    """
    out: List[str] = []
    try:
        rows = (db.query("SELECT symbol FROM positions WHERE status = 'open'")
                + db.query("SELECT symbol FROM watchlist"))
    except Exception:  # noqa: BLE001 - tables may not exist in a fresh DB
        return out
    for r in rows:
        sym = str(r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        full = sym if ":" in sym else f"EGX:{sym}"
        if full not in out:
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


def session_bar(symbol: str, timeframe: str = "1D") -> Optional[dict]:
    """The just-closed session's candle for `symbol`, from the snapshots table.

    Yahoo publishes an EGX daily bar roughly a full session late (a session's
    bar shows up as an all-null row and only fills the next day), so the Yahoo
    series is always missing the session the user is actually deciding on. The
    snapshot written at 15:00 by the post-close job already holds that session's
    TradingView OHLCV; this returns it in history.py's candle shape so
    leaders.daily_candles can graft it on.

    Returns None unless a row exists for the last COMPLETED session carrying a
    full, self-consistent OHLC. A partial or half-written row must never reach
    the pattern and level detectors dressed as a real bar.
    """
    bare = str(symbol).split(":", 1)[-1].upper()
    try:
        session = calendar_egx.last_completed_session().strftime("%Y-%m-%d")
        rows = db.query(
            "SELECT date, price, open, high, low, volume FROM snapshots "
            "WHERE symbol = ? AND date = ? AND timeframe = ? LIMIT 1",
            (bare, session, timeframe),
        )
    except Exception as exc:
        logger.warning("session_bar(%s) lookup failed: %s", symbol, exc)
        return None
    if not rows:
        return None
    row = rows[0]
    o, h, low, c = (_num(row.get("open")), _num(row.get("high")),
                    _num(row.get("low")), _num(row.get("price")))
    if None in (o, h, low, c):
        return None
    if min(o, h, low, c) <= 0 or h < low:  # type: ignore[type-var]
        return None
    vol = _num(row.get("volume"))
    return {
        "time": session,
        "open": round(o, 4),      # type: ignore[arg-type]
        "high": round(h, 4),      # type: ignore[arg-type]
        "low": round(low, 4),     # type: ignore[arg-type]
        "close": round(c, 4),     # type: ignore[arg-type]
        "volume": vol if vol is not None else 0.0,
        "source": "tv_snapshot",
    }


def snapshot_symbol(symbol: str, timeframe: str = "1D") -> dict:
    """On-demand snapshot of ONE symbol's just-closed session from TradingView.

    For a stock outside the nightly snapshot universe this is what lets the
    Yahoo-lag graft (`session_bar`) work at all. Refuses to run while the
    session is open: TradingView's bar is then a moving partial, and stamping
    it as the session's close would poison every downstream computation.

    When the session's row already exists (written by the nightly job) only
    price/change/volume/OHLC are refreshed. Score and the rank-dependent fields
    are left alone — a one-symbol call has no cross-section to rank against,
    and rewriting them would make the same stock score differently depending on
    whether someone pressed a button.
    """
    bare = str(symbol).split(":", 1)[-1].upper()
    try:
        if calendar_egx.is_market_open():
            return {"skipped": "session open — TradingView's bar is still moving", "symbol": bare}
        full = f"EGX:{bare}"
        fetched, batches_failed = _fetch_universe_indicators([full], timeframe)
        ind = fetched.get(full) or (next(iter(fetched.values())) if fetched else None)
        if not ind:
            return {"error": f"TradingView returned no data for {bare}", "symbol": bare,
                    "batches_failed": batches_failed}
        metrics = compute_metrics(ind) or {}
        price = _num(metrics.get("price"))
        if price is None:
            return {"error": f"TradingView bar for {bare} has no price", "symbol": bare}
        now = calendar_egx.now_cairo()
        session = calendar_egx.last_completed_session(now).strftime("%Y-%m-%d")
        o, h, low = _num(ind.get("open")), _num(ind.get("high")), _num(ind.get("low"))
        vol = _num(ind.get("volume"))
        existing = db.query(
            "SELECT id FROM snapshots WHERE symbol = ? AND date = ? AND timeframe = ?",
            (bare, session, timeframe),
        )
        if existing:
            db.execute(
                "UPDATE snapshots SET price = ?, change_pct = ?, volume = ?, open = ?, high = ?, low = ? "
                "WHERE id = ?",
                (price, metrics.get("change"), vol, o, h, low, existing[0]["id"]),
            )
            action = "updated"
        else:
            score: Optional[float] = None
            score_json: Optional[str] = None
            try:
                result = compute_stock_score(ind, change_pct_rank=None, currency=_get_currency(full))
                if result:
                    score = result.get("score")
                    score_json = json.dumps(
                        {k: result.get(k) for k in
                         ("score", "grade", "trend_state", "breakdown", "signals", "penalties")},
                        default=str,
                    )
            except Exception:
                pass  # score stays NULL — the bar is still worth persisting
            rsi_raw = ind.get("RSI")
            rsi = round(float(rsi_raw), 2) if isinstance(rsi_raw, (int, float)) else None
            db.execute(
                "INSERT INTO snapshots "
                "(symbol, date, timeframe, price, change_pct, volume, rsi, bbw, rating, signal, "
                " score, score_json, created_at, open, high, low) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (bare, session, timeframe, price, metrics.get("change"), vol, rsi, metrics.get("bbw"),
                 metrics.get("rating"), metrics.get("signal"), score, score_json, now.isoformat(),
                 o, h, low),
            )
            action = "inserted"
        return {"symbol": bare, "date": session, "action": action, "price": price,
                "open": o, "high": h, "low": low, "volume": vol,
                "ohlc_complete": None not in (o, h, low), "as_of": now.isoformat()}
    except Exception as exc:
        return {"error": str(exc), "symbol": bare}


def snapshot_universe(universe_name: str = "EGX100", timeframe: str = "1D",
                      include_held: bool = True) -> dict:
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
        extra_held = 0
        if include_held:
            for full in held_and_watched_symbols():
                if full not in prefixed:
                    prefixed.append(full)
                    extra_held += 1

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
                _num(ind.get("open")),
                _num(ind.get("high")),
                _num(ind.get("low")),
            ))

        # One transaction for the whole universe: no partial dates on a crash,
        # one lock hold instead of ~380, and no fsync storm against live reads.
        db_error: Optional[str] = None
        if pending:
            try:
                db.executemany(
                    "INSERT OR REPLACE INTO snapshots "
                    "(symbol, date, timeframe, price, change_pct, volume, rsi, bbw, "
                    " rating, signal, score, score_json, created_at, open, high, low) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            "held_or_watched_added": extra_held,
            "batches_failed": batches_failed,
            "as_of": created_at,
        }
    except Exception as exc:
        return {"error": str(exc)}
