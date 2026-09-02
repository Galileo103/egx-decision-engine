"""Brief routes: LLM morning brief, per-stock thesis, latest saved brief."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query

from app.services import briefs

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.post("/morning")
async def brief_morning() -> dict[str, Any]:
    """Generate and store today's morning brief."""
    try:
        return await asyncio.to_thread(briefs.morning_brief)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/thesis/{symbol}")
async def brief_thesis(symbol: str) -> dict[str, Any]:
    """Generate and store an investment thesis for one stock."""
    try:
        return await asyncio.to_thread(briefs.stock_thesis, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/debate/{symbol}")
async def brief_debate(symbol: str) -> dict[str, Any]:
    """Generate and store an adversarial LLM bull/bear debate for one stock."""
    try:
        return await asyncio.to_thread(briefs.llm_debate, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/latest")
async def brief_latest(
    kind: str = Query("morning"),
    symbol: Optional[str] = Query(None),
) -> dict[str, Any]:
    """Fetch the most recent stored brief of a kind (optionally per symbol)."""
    try:
        return await asyncio.to_thread(briefs.latest, kind, symbol)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
