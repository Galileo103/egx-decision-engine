"""Screener routes: scanner registry, single-scanner runs, merged candidates."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query, Request

from app.services import screeners

router = APIRouter(prefix="/api/screener", tags=["screener"])


def _coerce(value: str) -> Any:
    """Coerce a query-string value to int/float/bool where it obviously is one."""
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


@router.get("/list")
async def screener_list() -> dict[str, Any]:
    """Scanner registry: key -> {label, description, params}."""
    try:
        return screeners.SCANNERS
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/run/{key}")
async def screener_run(key: str, request: Request) -> dict[str, Any]:
    """Run one scanner; all query params are passed through as its params dict."""
    try:
        params = {k: _coerce(v) for k, v in request.query_params.items()}
        return await asyncio.to_thread(screeners.run_scanner, key, params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/candidates")
async def screener_candidates(
    timeframe: str = Query("1D"),
    persist: bool = Query(False),
) -> dict[str, Any]:
    """Flagship merged candidate list across the core scanners."""
    try:
        return await asyncio.to_thread(screeners.candidates, timeframe, persist)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
