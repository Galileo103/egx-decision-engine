"""Portfolio routes: position sizing, positions CRUD, performance."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings
from app.services import guardian, portfolio

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
    stop: Optional[float] = None  # omitted → filled from the trade plan
    target1: Optional[float] = None
    target2: Optional[float] = None
    plan: Optional[dict[str, Any]] = None
    note: str = ""
    allow_override: bool = False  # explicit consent to exceed the open-heat cap
    raised_stop: bool = False     # existing winner: stop already above cost


class UpdatePositionBody(BaseModel):
    """Body for adjusting an open position's current stop / targets / note."""

    stop: Optional[float] = None
    target1: Optional[float] = None
    target2: Optional[float] = None
    note: Optional[str] = None
    initial_stop: Optional[float] = None   # once, only while the record has none


class FillBody(BaseModel):
    """Body for buying more / selling part of an open position."""

    qty: float          # positive = bought more, negative = sold some
    price: float        # fill price
    note: str = ""


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
            body.raised_stop,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.delete("/positions/{position_id}")
async def portfolio_delete(position_id: int) -> dict[str, Any]:
    """Erase a position recorded by mistake (duplicate/typo). Not a sale — nothing is realized."""
    try:
        return await asyncio.to_thread(portfolio.delete_position, position_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/positions/{position_id}/fill")
async def portfolio_fill(position_id: int, body: FillBody) -> dict[str, Any]:
    """Add shares (blended entry) or sell part (realized PnL) of an open position."""
    try:
        return await asyncio.to_thread(
            portfolio.adjust_position, position_id, body.qty, body.price, body.note
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/fills")
async def portfolio_fills(
    position_id: Optional[int] = Query(None), limit: int = Query(200)
) -> Any:
    """Fill journal (buys / partial sells), newest first."""
    try:
        return await asyncio.to_thread(portfolio.position_fills, position_id, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/plan-defaults/{symbol}")
async def portfolio_plan_defaults(
    symbol: str, entry: Optional[float] = Query(None)
) -> dict[str, Any]:
    """Stop / targets / note for a new position, from the stock's own trade plan."""
    try:
        return await asyncio.to_thread(portfolio.plan_defaults, symbol, entry)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/positions/{position_id}/update")
async def portfolio_update(position_id: int, body: UpdatePositionBody) -> dict[str, Any]:
    """Adjust the current stop / targets / note of an open position (e.g. act on TIGHTEN_STOP)."""
    try:
        return await asyncio.to_thread(
            portfolio.update_position, position_id, body.stop, body.target1, body.target2, body.note,
            body.initial_stop,
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


@router.get("/guardian")
async def portfolio_guardian() -> dict[str, Any]:
    """Live exit verdicts for every open position (read-only: no persist, no Telegram)."""
    try:
        return await asyncio.to_thread(guardian.evaluate, False, False)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


class GuardianRunBody(BaseModel):
    """Body for an explicit guardian run (a body makes the POST non-CSRF-able)."""

    notify: bool = True


@router.post("/guardian/run")
async def portfolio_guardian_run(body: GuardianRunBody) -> dict[str, Any]:
    """Run the guardian now: persist today's verdicts and push actionable ones to Telegram."""
    try:
        return await asyncio.to_thread(guardian.evaluate, True, body.notify)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/guardian/history")
async def portfolio_guardian_history(
    position_id: Optional[int] = Query(None), limit: int = Query(60)
) -> Any:
    """Stored guardian verdicts, newest first; optionally for one position."""
    try:
        return await asyncio.to_thread(guardian.history, position_id, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
