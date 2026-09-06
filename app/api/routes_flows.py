"""Investor-type flow routes: summary, history, paste ingestion, deletion."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import flows

router = APIRouter(prefix="/api/flows", tags=["flows"])


class PasteBody(BaseModel):
    text: str
    date: Optional[str] = None      # YYYY-MM-DD; default = last trading day
    scope: str = "all"              # all | securities | bonds (which radio was selected on the EGX page)


@router.get("")
async def flows_summary(scope: str = Query("all")) -> dict[str, Any]:
    """Latest session, 5/20-session sums and streaks, series for the chart."""
    try:
        return await asyncio.to_thread(flows.summary, scope)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/history")
async def flows_history(days: int = Query(60, ge=1, le=400), scope: str = Query("all")) -> dict[str, Any]:
    try:
        return {"rows": await asyncio.to_thread(flows.history, days, scope), "scope": scope}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/parse")
async def flows_parse(body: PasteBody) -> dict[str, Any]:
    """Dry run: parse the paste and show what would be stored."""
    try:
        return await asyncio.to_thread(flows.parse_egx_text, body.text)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/paste")
async def flows_paste(body: PasteBody) -> dict[str, Any]:
    """Parse the pasted EGX investor-type page and store the session."""
    try:
        return await asyncio.to_thread(flows.record, body.text, body.date, body.scope)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.delete("/{date}")
async def flows_delete(date: str, scope: str = Query("all")) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(flows.delete, date, scope)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
