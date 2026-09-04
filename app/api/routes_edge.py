"""Proven-edge routes: the stored edge table, a background refresh, and the
historical replay that seeds the Scorecard."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import edge, replay

router = APIRouter(prefix="/api/edge", tags=["edge"])


class RefreshBody(BaseModel):
    universe: str = "EGX100"
    period: str = "3y"


class ReplayBody(BaseModel):
    universe: str = "EGX100"
    period: str = "5y"
    patterns: bool = True
    limit: Optional[int] = None


@router.get("")
async def edge_latest() -> dict[str, Any]:
    """Stored edge table — instant."""
    try:
        return await asyncio.to_thread(edge.latest)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/refresh")
async def edge_refresh(body: RefreshBody) -> dict[str, Any]:
    """Recompute the edge table in the background (minutes). Poll /status."""
    try:
        return edge.start(body.universe, body.period)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/status")
async def edge_status() -> dict[str, Any]:
    return {"edge": edge.status(), "replay": replay.status()}


@router.post("/replay")
async def replay_start(body: ReplayBody) -> dict[str, Any]:
    """Replay the app's rules and patterns over history in the background."""
    try:
        return replay.start(body.universe, body.period, body.patterns, body.limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/replay/status")
async def replay_status() -> dict[str, Any]:
    return replay.status()


@router.post("/replay/clear")
async def replay_clear() -> dict[str, Any]:
    """Delete every replayed hit and outcome; live data is untouched."""
    try:
        return await asyncio.to_thread(replay.clear)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
