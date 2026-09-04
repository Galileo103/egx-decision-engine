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


# ── App-rules backtests (the app's own entries and Guardian exits) ───────────

from typing import Optional as _Optional  # noqa: E402

from app.services import rules_backtest  # noqa: E402


class RulesBody(BaseModel):
    """Body for an app-rules backtest."""

    symbol: str
    entry_rule: str = "squeeze_breakout"
    exit_rule: str = "guardian"
    period: str = "2y"
    initial_capital: float = 100_000.0
    slippage_pct: float = 0.1
    params: _Optional[dict[str, Any]] = None


class RulesUniverseBody(BaseModel):
    """Body for running one rule pair across a universe."""

    universe: str = "EGX30"
    entry_rule: str = "squeeze_breakout"
    exit_rule: str = "guardian"
    period: str = "2y"
    initial_capital: float = 100_000.0
    limit: int = 40


class StopSweepBody(BaseModel):
    """Body for a stop-distance sweep."""

    symbol: str
    entry_rule: str = "squeeze_breakout"
    exit_rule: str = "fixed"
    period: str = "2y"
    initial_capital: float = 100_000.0
    stops: _Optional[list[float]] = None


@router.get("/rules")
async def backtest_rules_catalog() -> dict[str, Any]:
    """Entry and exit rules the app-rules backtester knows, with plain descriptions."""
    return {"entry_rules": rules_backtest.ENTRY_RULES, "exit_rules": rules_backtest.EXIT_RULES,
            "defaults": rules_backtest.DEFAULTS, "periods": list(rules_backtest.PERIOD_BARS),
            "min_trades_for_confidence": rules_backtest.MIN_TRADES_FOR_CONFIDENCE}


@router.post("/rules")
async def backtest_rules(body: RulesBody) -> dict[str, Any]:
    """Backtest one entry rule + one exit rule on one symbol, with a plain-language verdict."""
    try:
        return await asyncio.to_thread(rules_backtest.run, body.symbol, body.entry_rule, body.exit_rule,
                                       body.period, body.initial_capital, body.params, body.slippage_pct)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/rules/exits")
async def backtest_rules_exits(body: RulesBody) -> dict[str, Any]:
    """Same entries, every exit style — which way out pays on this stock."""
    try:
        return await asyncio.to_thread(rules_backtest.compare_exits, body.symbol, body.entry_rule,
                                       body.period, body.initial_capital, body.slippage_pct)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/rules/stops")
async def backtest_rules_stops(body: StopSweepBody) -> dict[str, Any]:
    """Sweep the stop distance (in ATR multiples) for one rule pair."""
    try:
        return await asyncio.to_thread(rules_backtest.stop_sweep, body.symbol, body.entry_rule, body.exit_rule,
                                       body.period, body.initial_capital, body.stops)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/rules/universe")
async def backtest_rules_universe(body: RulesUniverseBody) -> dict[str, Any]:
    """One rule pair across a whole universe — distribution of outcomes, pooled stats."""
    try:
        return await asyncio.to_thread(rules_backtest.universe_run, body.universe, body.entry_rule,
                                       body.exit_rule, body.period, body.initial_capital, body.limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/rules/replay")
async def backtest_rules_replay() -> dict[str, Any]:
    """Replay the user's open positions under the Guardian's rules vs actual holding vs EGX30."""
    try:
        return await asyncio.to_thread(rules_backtest.replay_positions)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
