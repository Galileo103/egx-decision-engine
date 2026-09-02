"""Market routes: EGX overview, indices, sectors, global snapshot, universe snapshot."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from app.services import market

router = APIRouter(prefix="/api/market", tags=["market"])


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
