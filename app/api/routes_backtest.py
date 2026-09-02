"""Backtest routes: single run, strategy comparison, walk-forward, strategy list."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import backtests

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestBody(BaseModel):
    """Body for a single-strategy backtest."""

    symbol: str
    strategy: str
    period: str = "1y"
    interval: str = "1d"
    commission_pct: float = 0.3
    slippage_pct: float = 0.1
    initial_capital: float = 100_000.0


class CompareBody(BaseModel):
    """Body for comparing all strategies on one symbol."""

    symbol: str
    period: str = "1y"
    interval: str = "1d"
    commission_pct: float = 0.3
    slippage_pct: float = 0.1
    initial_capital: float = 100_000.0


class WalkForwardBody(BaseModel):
    """Body for a walk-forward backtest."""

    symbol: str
    strategy: str
    period: str = "2y"
    interval: str = "1d"
    commission_pct: float = 0.3
    slippage_pct: float = 0.1
    initial_capital: float = 100_000.0
    n_splits: int = 3
    train_ratio: float = 0.7


@router.post("")
async def backtest_run(body: BacktestBody) -> dict[str, Any]:
    """Run one strategy backtest (symbol is mapped to Yahoo form by the service)."""
    try:
        return await asyncio.to_thread(
            backtests.run,
            body.symbol,
            body.strategy,
            body.period,
            body.interval,
            body.commission_pct,
            body.slippage_pct,
            body.initial_capital,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/compare")
async def backtest_compare(body: CompareBody) -> dict[str, Any]:
    """Compare all strategies on one symbol."""
    try:
        return await asyncio.to_thread(
            backtests.compare,
            body.symbol,
            body.period,
            body.interval,
            body.commission_pct,
            body.slippage_pct,
            body.initial_capital,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/walkforward")
async def backtest_walkforward(body: WalkForwardBody) -> dict[str, Any]:
    """Walk-forward (in/out-of-sample) backtest."""
    try:
        return await asyncio.to_thread(
            backtests.walk_forward,
            body.symbol,
            body.strategy,
            body.period,
            body.interval,
            body.commission_pct,
            body.slippage_pct,
            body.initial_capital,
            body.n_splits,
            body.train_ratio,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/strategies")
async def backtest_strategies() -> list[str]:
    """List of available strategy names."""
    try:
        return list(backtests.STRATEGIES)
    except Exception:  # noqa: BLE001
        return []
