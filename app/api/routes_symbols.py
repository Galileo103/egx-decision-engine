"""Symbol catalog routes — powers the top-bar autocomplete."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from app.services import catalog

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("")
async def list_symbols() -> dict[str, Any]:
    """Every EGX ticker with its company name, sector and index membership."""
    try:
        return await asyncio.to_thread(catalog.list_symbols)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "symbols": []}


@router.post("/refresh")
async def refresh_symbols() -> dict[str, Any]:
    """Re-fetch company names from TradingView and rewrite the bundled catalog."""
    try:
        return await asyncio.to_thread(catalog.refresh)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
