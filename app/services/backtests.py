"""Backtesting services for the EGX Decision Engine.

Thin, defensive wrappers over ``tradingview_mcp.core.services.backtest_service``.
The core functions take YAHOO symbols (EGX tickers become ``SYM.CA``), so every
entry point here maps the TradingView-style symbol via ``app.symbols.tv_to_yahoo``
before delegating.

Core error results (``{"error": ...}``) are propagated as-is; unexpected
exceptions are converted to ``{"error": str(exc)}`` — nothing raises.
"""
from __future__ import annotations

import json
import logging

from tradingview_mcp.core.services.backtest_service import (
    compare_strategies,
    run_backtest,
    walk_forward_backtest,
)

from app.config import settings
from app.symbols import tv_to_yahoo

logger = logging.getLogger(__name__)

# EGX session realities for Sharpe annualization: ~245 trading days/year
# (Sun-Thu minus ~13 holidays), 4.5-hour session (10:00-14:30 Cairo).
_EGX_DAYS_PER_YEAR = 245
_EGX_HOURS_PER_DAY = 4.5


def _egx_metric_kwargs(interval: str) -> dict:
    """EGP risk-free rate + EGX bar-count annualization for the engine."""
    periods = (
        int(_EGX_DAYS_PER_YEAR * _EGX_HOURS_PER_DAY)
        if interval == "1h"
        else _EGX_DAYS_PER_YEAR
    )
    return {
        "risk_free_rate": settings.risk_free_rate_pct / 100.0,
        "periods_per_year": periods,
    }


def _persist_run(kind: str, symbol: str, strategy: str | None,
                 period: str, interval: str, params: dict, result: dict) -> None:
    """Store every run so results are reproducible — Yahoo silently revises
    EGX history, so yesterday's numbers cannot otherwise be re-derived.
    Equity curves are dropped from the stored copy to keep the DB lean;
    params and the full trade log/metrics are kept."""
    try:
        from app import db
        from app.calendar_egx import now_cairo

        slim = {k: v for k, v in result.items() if k != "equity_curve"} \
            if isinstance(result, dict) else {"result": result}
        db.execute(
            "INSERT INTO backtest_runs (ts, kind, symbol, strategy, period, interval, "
            "params_json, result_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now_cairo().isoformat(), kind, str(symbol).upper(), strategy,
             period, interval, json.dumps(params, default=str),
             json.dumps(slim, default=str)),
        )
    except Exception as exc:
        logger.warning("persisting backtest run failed: %s", exc)


def _annotate(result: dict, symbol: str, initial_capital: float | None = None) -> dict:
    if isinstance(result, dict):
        result.setdefault("requested_symbol", str(symbol).upper())
        if "error" not in result:
            result.setdefault(
                "assumptions_note",
                f"Sharpe uses EGP risk-free {settings.risk_free_rate_pct:.1f}%/yr and "
                f"EGX session annualization ({_EGX_DAYS_PER_YEAR}d/yr, {_EGX_HOURS_PER_DAY}h/d). "
                "Prices are dividend/split-adjusted where Yahoo provides adjclose.",
            )
            # Every trade in the engine deploys 100% of capital; on a thin EGX
            # name that fill assumption (and the flat slippage) is fantasy —
            # say so next to the results instead of letting them flatter.
            try:
                from app.services.market import median_daily_value

                liquidity = median_daily_value(symbol)
                if liquidity and initial_capital and initial_capital > 0.10 * liquidity:
                    result.setdefault(
                        "liquidity_warning",
                        f"Backtest deploys {initial_capital:,.0f} EGP per trade but "
                        f"{str(symbol).upper()}'s 20-day median daily value is only "
                        f"~{liquidity:,.0f} EGP — real fills would move the price; "
                        "results are optimistic. Consider slippage ≥0.5%/side.",
                    )
            except Exception:
                pass
    return result

# Literal strategy names from backtest_service._STRATEGY_MAP (9 strategies).
STRATEGIES: list[str] = [
    "rsi",
    "bollinger",
    "macd",
    "ema_cross",
    "supertrend",
    "donchian",
    "rsi_pullback",
    "keltner_breakout",
    "triple_ema",
]


def run(
    symbol: str,
    strategy: str,
    period: str = "1y",
    interval: str = "1d",
    commission_pct: float = 0.3,
    slippage_pct: float = 0.1,
    initial_capital: float = 100_000,
) -> dict:
    """Backtest one strategy on one EGX symbol.

    Args:
        symbol:          EGX symbol (e.g. 'COMI' or 'EGX:COMI'); mapped to Yahoo.
        strategy:        One of ``STRATEGIES``.
        period:          Yahoo range ('1mo','3mo','6mo','1y','2y').
        interval:        '1d' or '1h'.
        commission_pct:  Per-side commission percent (EGX default 0.3).
        slippage_pct:    Per-side slippage percent.
        initial_capital: Starting capital in EGP.

    Returns:
        Full backtest dict (metrics, trade log, equity curve) or ``{"error": ...}``.
    """
    try:
        yahoo_symbol = tv_to_yahoo(symbol)
        result = run_backtest(
            symbol=yahoo_symbol,
            strategy=strategy,
            period=period,
            initial_capital=float(initial_capital),
            commission_pct=float(commission_pct),
            slippage_pct=float(slippage_pct),
            interval=interval,
            include_trade_log=True,
            include_equity_curve=True,
            **_egx_metric_kwargs(interval),
        )
        result = _annotate(result, symbol, float(initial_capital))
        _persist_run("single", symbol, strategy, period, interval,
                     {"commission_pct": commission_pct, "slippage_pct": slippage_pct,
                      "initial_capital": initial_capital}, result)
        return result
    except Exception as exc:
        logger.warning("run_backtest(%s, %s) failed: %s", symbol, strategy, exc)
        return {"error": str(exc)}


def compare(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    commission_pct: float = 0.3,
    slippage_pct: float = 0.1,
    initial_capital: float = 100_000,
) -> dict:
    """Run all strategies on one EGX symbol and rank them.

    Returns the core ``compare_strategies`` payload (ranking, winner,
    buy-and-hold benchmark) or ``{"error": ...}``.
    """
    try:
        yahoo_symbol = tv_to_yahoo(symbol)
        result = compare_strategies(
            symbol=yahoo_symbol,
            period=period,
            initial_capital=float(initial_capital),
            commission_pct=float(commission_pct),
            slippage_pct=float(slippage_pct),
            interval=interval,
            **_egx_metric_kwargs(interval),
        )
        result = _annotate(result, symbol, float(initial_capital))
        _persist_run("compare", symbol, None, period, interval,
                     {"commission_pct": commission_pct, "slippage_pct": slippage_pct,
                      "initial_capital": initial_capital}, result)
        return result
    except Exception as exc:
        logger.warning("compare_strategies(%s) failed: %s", symbol, exc)
        return {"error": str(exc)}


def walk_forward(
    symbol: str,
    strategy: str,
    period: str = "2y",
    interval: str = "1d",
    commission_pct: float = 0.3,
    slippage_pct: float = 0.1,
    initial_capital: float = 100_000,
    n_splits: int = 3,
    train_ratio: float = 0.7,
) -> dict:
    """Walk-forward (train/test fold) backtest for overfitting detection.

    Returns the core ``walk_forward_backtest`` payload (per-fold results,
    robustness score, verdict) or ``{"error": ...}``.
    """
    try:
        yahoo_symbol = tv_to_yahoo(symbol)
        result = walk_forward_backtest(
            symbol=yahoo_symbol,
            strategy=strategy,
            period=period,
            initial_capital=float(initial_capital),
            commission_pct=float(commission_pct),
            slippage_pct=float(slippage_pct),
            n_splits=int(n_splits),
            train_ratio=float(train_ratio),
            interval=interval,
            **_egx_metric_kwargs(interval),
        )
        result = _annotate(result, symbol, float(initial_capital))
        _persist_run("walkforward", symbol, strategy, period, interval,
                     {"commission_pct": commission_pct, "slippage_pct": slippage_pct,
                      "initial_capital": initial_capital, "n_splits": n_splits,
                      "train_ratio": train_ratio}, result)
        return result
    except Exception as exc:
        logger.warning("walk_forward_backtest(%s, %s) failed: %s", symbol, strategy, exc)
        return {"error": str(exc)}
