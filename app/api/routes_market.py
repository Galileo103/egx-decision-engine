"""Market routes: EGX overview, indices, sectors, global snapshot, universe snapshot."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from app import calendar_egx
from app.services import market

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/session")
async def market_session() -> dict[str, Any]:
    """Session state plus the last session whose closing bar should be final.

    The pages compare a card's ``as_of`` against ``last_completed_session`` to
    say plainly when a card is missing the session just traded, instead of
    showing a bare date the reader has to date-check themselves.
    """
    try:
        state = calendar_egx.session_state()
        state["last_completed_session"] = (
            calendar_egx.last_completed_session().strftime("%Y-%m-%d")
        )
        return state
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/regime")
async def market_regime(history: int = Query(0, ge=0, le=1500)) -> dict[str, Any]:
    """Today's market regime (bull / neutral / bear) with its plain-language sentence;
    ``history=N`` adds the last N daily rows for a strip chart."""
    try:
        from app.services import regime

        out = await asyncio.to_thread(regime.current)
        if history:
            out["history"] = await asyncio.to_thread(regime.history, history)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/regime/refresh")
async def market_regime_refresh() -> dict[str, Any]:
    """Recompute the last year of regime rows now (post-close does this automatically)."""
    try:
        from app.services import regime

        return await asyncio.to_thread(regime.update_today)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/overview")
async def market_overview(
    timeframe: str = Query("1D"),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """EGX market overview with breadth and session state."""
    try:
        return await asyncio.to_thread(market.overview, timeframe, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/index/{index}")
async def market_index(index: str, timeframe: str = Query("1D")) -> dict[str, Any]:
    """Technical analysis of an EGX index (EGX30/EGX70/EGX100...)."""
    try:
        return await asyncio.to_thread(market.index_analysis, index, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/sectors")
async def market_sectors(timeframe: str = Query("1D")) -> dict[str, Any]:
    """Sector scanner across all EGX sectors."""
    try:
        return await asyncio.to_thread(market.sectors, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/sector/{name}")
async def market_sector_detail(name: str, timeframe: str = Query("1D")) -> dict[str, Any]:
    """Detailed scan of a single EGX sector."""
    try:
        return await asyncio.to_thread(market.sector_detail, name, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/global")
async def market_global() -> dict[str, Any]:
    """Global markets snapshot (indices, crypto, FX, ETFs)."""
    try:
        return await asyncio.to_thread(market.global_snapshot)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/snapshot")
async def market_snapshot(
    universe: str = Query("EGX100"),
    timeframe: str = Query("1D"),
) -> dict[str, Any]:
    """Persist a per-symbol snapshot of the universe into the snapshots table."""
    try:
        return await asyncio.to_thread(market.snapshot_universe, universe, timeframe)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
