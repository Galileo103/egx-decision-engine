"""Proven-edge routes: the stored edge table, a background refresh, and the
historical replay that seeds the Scorecard."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import edge, replay, scorecard

router = APIRouter(prefix="/api/edge", tags=["edge"])


class RefreshBody(BaseModel):
    universe: str = "EGX100"
    period: str = "3y"


class ReplayBody(BaseModel):
    universe: str = "EGX100"
    period: str = "5y"
    patterns: bool = True
    limit: Optional[int] = None
    checklist: bool = False   # also replay the six-pillar BUY checklist verdicts (slower)


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
    return {"edge": edge.status(), "replay": replay.status(), "regrade": scorecard.regrade_status()}


class RegradeBody(BaseModel):
    source: Optional[str] = None       # 'replay' | 'live' | None = both
    only_incomplete: bool = True       # False re-grades every stored outcome


@router.post("/regrade")
async def regrade_start(body: RegradeBody) -> dict[str, Any]:
    """Re-grade stored outcomes in the background: fills the 40/60-session columns
    and the regime stamp without re-running detection. Poll /status."""
    try:
        return scorecard.start_regrade(body.source, body.only_incomplete)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/replay")
async def replay_start(body: ReplayBody) -> dict[str, Any]:
    """Replay the app's rules and patterns over history in the background."""
    try:
        return replay.start(body.universe, body.period, body.patterns, body.limit, body.checklist)
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
