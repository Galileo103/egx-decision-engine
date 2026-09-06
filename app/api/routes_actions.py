"""Corporate-actions routes: upcoming events, manual entry, deletion."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import corporate_actions as CA

router = APIRouter(prefix="/api/corporate-actions", tags=["corporate-actions"])


class ActionBody(BaseModel):
    symbol: str
    type: str                      # dividend | split | rights | capital_increase | bonus | other
    ex_date: str                   # YYYY-MM-DD
    amount: Optional[float] = None
    ratio: Optional[float] = None
    note: str = ""


@router.get("")
async def actions_list(symbol: Optional[str] = Query(None), days: int = Query(30, ge=0, le=400),
                       mine: bool = Query(False)) -> dict[str, Any]:
    """Upcoming events within ``days``. ``symbol`` narrows to one stock (all of its
    history is returned too); ``mine`` narrows to held + watchlist symbols."""
    try:
        if symbol:
            return {"symbol": symbol.upper(), "events": await asyncio.to_thread(CA.for_symbol, symbol),
                    "upcoming": await asyncio.to_thread(CA.upcoming, [symbol], days)}
        symbols = None
        if mine:
            from app.services import market

            symbols = [s.split(":")[-1] for s in await asyncio.to_thread(market.held_and_watched_symbols)]
        return {"upcoming": await asyncio.to_thread(CA.upcoming, symbols, days), "days": days,
                "scope": "held + watchlist" if mine else "all", "types": list(CA.TYPES)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("")
async def actions_add(body: ActionBody) -> dict[str, Any]:
    """Record an upcoming (or past) ex-date, rights issue, capital increase… by hand."""
    try:
        return await asyncio.to_thread(CA.add, body.symbol, body.type, body.ex_date, body.amount, body.ratio, body.note)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.delete("/{action_id}")
async def actions_delete(action_id: int) -> dict[str, Any]:
    """Remove a manual event (Yahoo-sourced rows cannot be deleted; they are re-derived)."""
    try:
        return await asyncio.to_thread(CA.delete, action_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
