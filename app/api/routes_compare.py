"""Compare route: two to four stocks side by side with a ranked verdict."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from app.services import compare

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("")
async def compare_symbols(symbols: str = Query("", description="Comma-separated, 2 to 4 symbols")) -> dict[str, Any]:
    syms = [s for s in (symbols or "").replace(";", ",").split(",") if s.strip()]
    try:
        return await asyncio.to_thread(compare.compare, syms)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
