"""Stock routes: detail, MTF, smart money, news, debate, history — plus watchlist CRUD."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from tradingview_mcp.core.services import yahoo_finance_service

from app import calendar_egx, db, symbols
from app.services import history, stocks

router = APIRouter(prefix="/api/stocks", tags=["stocks"])
watchlist_router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# ── Stocks ───────────────────────────────────────────────────────────────────

@router.get("/{symbol}")
async def stock_detail(symbol: str, timeframe: str = Query("1D")) -> dict[str, Any]:
    """Composite stock detail: full TA, trade plan, fibonacci, score history."""
    try:
        return await asyncio.to_thread(stocks.detail, symbol, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/mtf")
async def stock_mtf(symbol: str) -> dict[str, Any]:
    """Multi-timeframe alignment analysis."""
    try:
        return await asyncio.to_thread(stocks.mtf, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/smart-money")
async def stock_smart_money(symbol: str) -> dict[str, Any]:
    """Smart-money (institutional flow) analysis."""
    try:
        return await asyncio.to_thread(stocks.smart_money, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/news")
async def stock_news(symbol: str) -> dict[str, Any]:
    """News + sentiment (requires MARKETAUX_API_TOKEN; degrades gracefully)."""
    try:
        return await asyncio.to_thread(stocks.news, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/debate")
async def stock_debate(symbol: str, timeframe: str = Query("1D")) -> dict[str, Any]:
    """Multi-agent bull/bear debate analysis."""
    try:
        return await asyncio.to_thread(stocks.debate, symbol, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/history")
async def stock_history(
    symbol: str,
    range: str = Query("1y", alias="range"),
    interval: str = Query("1d"),
) -> dict[str, Any]:
    """OHLCV candle history via Yahoo chart API (cached)."""
    try:
        return await asyncio.to_thread(history.get_history, symbol, range, interval)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/levels")
async def stock_levels(symbol: str) -> dict[str, Any]:
    """Support & resistance zones (tested swing clusters, 52w extremes, round numbers, SMAs)."""
    try:
        from app.services import levels

        return await asyncio.to_thread(levels.compute, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/checklist")
async def stock_checklist(symbol: str) -> dict[str, Any]:
    """Six-pillar decision checklist: trend, S/R, volume, price action, patterns, risk plan."""
    try:
        from app.services import checklist

        return await asyncio.to_thread(checklist.checklist, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/{symbol}/patterns")
async def stock_patterns(symbol: str) -> dict[str, Any]:
    """Chart patterns (double/triple bottom/top, head & shoulders, cup) on the daily chart."""
    try:
        from app.services import patterns

        return await asyncio.to_thread(patterns.detect, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Watchlist ────────────────────────────────────────────────────────────────

class WatchlistAdd(BaseModel):
    """Body for adding a watchlist entry."""

    symbol: str
    note: str = ""


def _normalize(symbol: str) -> str:
    """Uppercase and strip an optional EGX: prefix."""
    sym = symbol.strip().upper()
    if sym.startswith("EGX:"):
        sym = sym[4:]
    return sym


def _enrich_watchlist(rows: list[dict[str, Any]]) -> None:
    """Attach live price/change to watchlist rows in place; tolerate any failure."""
    if not rows:
        return
    try:
        yahoo_map = {row["symbol"]: symbols.tv_to_yahoo(row["symbol"]) for row in rows}
        quotes = yahoo_finance_service.get_prices_bulk(list(yahoo_map.values()))
        by_symbol: dict[str, dict[str, Any]] = {}
        for quote in quotes:
            if isinstance(quote, dict) and quote.get("symbol"):
                by_symbol[str(quote["symbol"]).upper()] = quote
        for row in rows:
            quote = by_symbol.get(yahoo_map[row["symbol"]].upper())
            if quote and not quote.get("error"):
                row["price"] = quote.get("price")
                row["change"] = quote.get("change")
                row["change_pct"] = quote.get("change_pct")
                row["market_state"] = quote.get("market_state")
    except Exception:  # noqa: BLE001 — enrichment is best-effort
        pass


@watchlist_router.get("")
async def watchlist_get() -> dict[str, Any]:
    """List watchlist entries, enriched with live prices where available."""
    try:
        rows = await asyncio.to_thread(
            db.query, "SELECT symbol, note, added_at FROM watchlist ORDER BY added_at DESC"
        )
        await asyncio.to_thread(_enrich_watchlist, rows)
        return {"watchlist": rows}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@watchlist_router.post("")
async def watchlist_add(body: WatchlistAdd) -> dict[str, Any]:
    """Add (or update the note of) a watchlist symbol."""
    try:
        sym = _normalize(body.symbol)
        if not sym:
            return {"error": "symbol is required"}
        added_at = calendar_egx.now_cairo().isoformat()
        await asyncio.to_thread(
            db.execute,
            "INSERT OR REPLACE INTO watchlist(symbol, note, added_at) VALUES (?, ?, ?)",
            (sym, body.note, added_at),
        )
        return {"ok": True, "symbol": sym}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@watchlist_router.delete("/{symbol}")
async def watchlist_delete(symbol: str) -> dict[str, Any]:
    """Remove a symbol from the watchlist."""
    try:
        sym = _normalize(symbol)
        await asyncio.to_thread(
            db.execute, "DELETE FROM watchlist WHERE symbol = ?", (sym,)
        )
        return {"ok": True, "symbol": sym}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
