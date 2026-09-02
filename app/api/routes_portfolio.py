"""Portfolio routes: position sizing, positions CRUD, performance."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings
from app.services import portfolio

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class SizeBody(BaseModel):
    """Body for position sizing; account/risk default from settings."""

    entry: float
    stop: float
    account: Optional[float] = None
    risk_pct: Optional[float] = None
    symbol: Optional[str] = None  # enables the liquidity (% of ADV) check


class OpenPositionBody(BaseModel):
    """Body for opening a position."""

    symbol: str
    qty: float
    entry: float
    stop: float
    target1: Optional[float] = None
    target2: Optional[float] = None
    plan: Optional[dict[str, Any]] = None
    note: str = ""
    allow_override: bool = False  # explicit consent to exceed the open-heat cap


class ClosePositionBody(BaseModel):
    """Body for closing a position."""

    exit_price: float
    plan_followed: Optional[bool] = None  # journaling: did you follow the plan?


@router.post("/size")
async def portfolio_size(body: SizeBody) -> dict[str, Any]:
    """Compute position size from account, risk %, entry and stop."""
    try:
        account = body.account if body.account is not None else settings.account_size
        risk_pct = body.risk_pct if body.risk_pct is not None else settings.risk_pct
        return await asyncio.to_thread(
            portfolio.size_position, account, risk_pct, body.entry, body.stop, body.symbol
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/positions")
async def portfolio_positions(status: str = Query("all")) -> Any:
    """List positions filtered by status: all | open | closed."""
    try:
        return await asyncio.to_thread(portfolio.list_positions, status)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/positions")
async def portfolio_open(body: OpenPositionBody) -> dict[str, Any]:
    """Open a new position."""
    try:
        return await asyncio.to_thread(
            portfolio.open_position,
            body.symbol,
            body.qty,
            body.entry,
            body.stop,
            body.target1,
            body.target2,
            body.plan,
            body.note,
            body.allow_override,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/positions/{position_id}/close")
async def portfolio_close(position_id: int, body: ClosePositionBody) -> dict[str, Any]:
    """Close a position at the given exit price."""
    try:
        return await asyncio.to_thread(
            portfolio.close_position, position_id, body.exit_price, body.plan_followed
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/config")
async def portfolio_config() -> dict[str, Any]:
    """Sizing defaults for the frontend — kills hardcoded account sizes."""
    return {
        "account_size": settings.account_size,
        "risk_pct": settings.risk_pct,
        "fee_pct_per_side": settings.fee_pct_per_side,
        "max_open_heat_pct": portfolio.MAX_OPEN_HEAT_PCT,
    }


@router.get("/performance")
async def portfolio_performance() -> dict[str, Any]:
    """Portfolio performance: mark-to-market, realized PnL, win rate, open risk."""
    try:
        return await asyncio.to_thread(portfolio.performance)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
