"""Per-stock services for the EGX Decision Engine.

Composes single-symbol views from the `tradingview_mcp.core` package:
full technical analysis, trade plan, Fibonacci levels, multi-timeframe
alignment, smart-money read, news/sentiment, and the multi-agent debate.

All public functions return plain dicts and never raise: failures come back
as ``{"error": "..."}`` (or as an ``error`` sub-key for composite sections)
per the project contract.
"""
from __future__ import annotations

import os
from typing import Any, Callable, List

from tradingview_mcp.core.services import egx_service
from tradingview_mcp.core.services.marketaux_service import (
    analyze_sentiment,
    fetch_news_summary,
)
from tradingview_mcp.core.services.multi_agent_service import run_multi_agent_analysis
from tradingview_mcp.core.services.screener_service import (
    analyze_coin,
    run_multi_timeframe_analysis,
)
from tradingview_mcp.core.services.smart_money_service import analyze_smart_money

from app import calendar_egx, db
from app.config import settings

_EXCHANGE = "egx"  # lowercase key used by tradingview_mcp validators/screeners


def _bare(symbol: str) -> str:
    """Normalize any input ('comi', 'EGX:COMI') to a bare upper ticker."""
    return (symbol or "").strip().upper().split(":")[-1]


def _full(symbol: str) -> str:
    """Fully-qualified TradingView symbol with the EGX prefix."""
    return f"EGX:{_bare(symbol)}"


def _as_of() -> str:
    """ISO timestamp in Cairo local time."""
    try:
        return calendar_egx.now_cairo().isoformat()
    except Exception:  # pragma: no cover — calendar module owned elsewhere
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> dict:
    """Run a core-library call, mapping any failure to an error dict."""
    try:
        out = fn(*args, **kwargs)
        if isinstance(out, dict):
            return out
        return {"error": f"Unexpected result type from {fn.__name__}: {type(out).__name__}"}
    except Exception as exc:
        return {"error": str(exc)}


def _score_history(bare: str) -> List[dict]:
    """Last 90 snapshot rows for a symbol (newest first); [] on any failure."""
    try:
        return db.query(
            "SELECT date, timeframe, price, change_pct, volume, rsi, bbw, "
            "       rating, signal, score "
            "FROM snapshots WHERE symbol = ? "
            "ORDER BY date DESC, id DESC LIMIT 90",
            (bare,),
        )
    except Exception:
        return []


def _in_watchlist(bare: str) -> bool:
    try:
        rows = db.query("SELECT 1 FROM watchlist WHERE symbol = ?", (bare,))
        return bool(rows)
    except Exception:
        return False


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plan_levels(plan: dict) -> dict:
    """Entry/stop/targets from an egx_service trade plan (scenario or flat shape)."""
    out: dict[str, float | None] = {"entry": None, "stop": None, "t1": None, "t2": None}
    ts = plan.get("trade_setup") if isinstance(plan, dict) else None
    if not isinstance(ts, dict) or ts.get("error"):
        return out
    scen = None
    scenarios = ts.get("scenarios")
    primary = ts.get("primary_scenario")
    if isinstance(scenarios, dict) and isinstance(primary, str):
        scen = scenarios.get(primary)
    if isinstance(scen, dict):
        targets_raw = scen.get("targets")
        targets = targets_raw if isinstance(targets_raw, dict) else {}
        out.update(entry=_num(scen.get("entry")), stop=_num(scen.get("stop_loss")),
                   t1=_num(targets.get("target_1")), t2=_num(targets.get("target_2")))
        return out
    ep_raw = ts.get("entry_points")
    entry_points = ep_raw if isinstance(ep_raw, dict) else {}
    targets_raw = ts.get("targets")
    targets = targets_raw if isinstance(targets_raw, dict) else {}
    out.update(
        entry=_num(entry_points.get("pullback_entry")) or _num(entry_points.get("breakout_entry")),
        stop=_num(ts.get("stop_loss")),
        t1=_num(targets.get("target_1")), t2=_num(targets.get("target_2")),
    )
    return out


def _plan_checks(bare: str, analysis: dict, trade_plan: dict) -> list[str]:
    """EGX-reality warnings for a trade plan: price-limit bands and liquidity.

    Plans place stops/targets by ATR and indicator levels with no awareness
    that EGX halts moves at the daily band — a stop further away than one
    limit-down session can be gapped straight through with no fill.
    """
    checks: list[str] = []
    try:
        band = float(settings.price_band_pct)
        price = None
        if isinstance(analysis, dict):
            price_data = analysis.get("price_data")
            if isinstance(price_data, dict):
                price = _num(price_data.get("current_price"))
        levels = _plan_levels(trade_plan if isinstance(trade_plan, dict) else {})
        if price and price > 0:
            stop = levels.get("stop")
            if stop is not None and stop < price:
                dist = (price - stop) / price * 100.0
                if dist > band:
                    checks.append(
                        f"Stop is {dist:.1f}% below the current price — beyond one "
                        f"±{band:.0f}% limit session; a limit-down open can gap through "
                        "it with no fill. Size for gap risk, not just stop distance."
                    )
            for name in ("t1", "t2"):
                target = levels.get(name)
                if target is not None and target > price:
                    dist = (target - price) / price * 100.0
                    if dist > band:
                        checks.append(
                            f"Target {name[-1]} is {dist:.1f}% above the current price — "
                            f"more than one ±{band:.0f}% limit session away; treat it as "
                            "a multi-day swing target."
                        )
        # Stops parked just above tested support / targets just under tested
        # resistance are the two most common plan mistakes — say so.
        try:
            from app.services import levels as _levels

            lv = _levels.compute(bare)
            checks.extend(_levels.plan_checks(lv, levels.get("stop"), [levels.get("t1"), levels.get("t2")]))
        except Exception:  # noqa: BLE001 — advisory only
            pass

        from app.services.market import median_daily_value

        liquidity = median_daily_value(bare)
        if liquidity is not None and liquidity < settings.min_daily_value_egp:
            checks.append(
                f"Illiquid: 20-day median traded value ~{liquidity:,.0f} EGP "
                f"(floor {settings.min_daily_value_egp:,.0f}). Exit liquidity is the "
                "real risk — spreads and slippage will eat the plan's R:R."
            )
    except Exception:  # checks are advisory — never break the detail payload
        return checks
    return checks


# ── Public API ─────────────────────────────────────────────────────────────────

def detail(symbol: str, timeframe: str = "1D") -> dict:
    """Composite single-stock view.

    Runs full TA (``analyze_coin``), the EGX trade plan, and Fibonacci
    analysis — each independently, so one upstream failure only degrades its
    own section to ``{"error": ...}`` — plus local score history from the
    snapshots table and the watchlist membership flag.
    """
    try:
        bare = _bare(symbol)
        if not bare:
            return {"error": "symbol is required"}

        analysis = _call(analyze_coin, bare, _EXCHANGE, timeframe)
        trade_plan = _call(egx_service.generate_egx_trade_plan, bare, timeframe)
        fibonacci = _call(egx_service.analyze_egx_fibonacci, bare, timeframe=timeframe)

        return {
            "symbol": bare,
            "timeframe": timeframe,
            "analysis": analysis,
            "trade_plan": trade_plan,
            "fibonacci": fibonacci,
            "plan_checks": _plan_checks(bare, analysis, trade_plan),
            "score_history": _score_history(bare),
            "in_watchlist": _in_watchlist(bare),
            "as_of": _as_of(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def mtf(symbol: str) -> dict:
    """Multi-timeframe alignment (1W → 1D → 4h → 1h → 15m) for one EGX stock."""
    try:
        bare = _bare(symbol)
        if not bare:
            return {"error": "symbol is required"}
        return _call(run_multi_timeframe_analysis, _full(bare), _EXCHANGE)
    except Exception as exc:
        return {"error": str(exc)}


def smart_money(symbol: str) -> dict:
    """Smart-money read (MCDX-style, banker oscillator, volume-flow composite)."""
    try:
        bare = _bare(symbol)
        if not bare:
            return {"error": "symbol is required"}
        return _call(analyze_smart_money, bare, "EGX")
    except Exception as exc:
        return {"error": str(exc)}


def news(symbol: str) -> dict:
    """News summary + news-based sentiment via Marketaux.

    Degrades gracefully: without a MARKETAUX_API_TOKEN a top-level error is
    returned instead of empty sections.
    """
    try:
        bare = _bare(symbol)
        if not bare:
            return {"error": "symbol is required"}
        if not os.environ.get("MARKETAUX_API_TOKEN"):
            return {"error": "MARKETAUX_API_TOKEN not configured", "symbol": bare}

        return {
            "symbol": bare,
            "news": _call(fetch_news_summary, symbol=bare, category="stocks"),
            "sentiment": _call(analyze_sentiment, bare),
            "as_of": _as_of(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def debate(symbol: str, timeframe: str = "1D") -> dict:
    """Rule-based signal summary (deterministic indicator checklists + consensus).

    Despite the historical name, this is not an AI debate — see
    ``briefs.llm_debate`` for the genuinely adversarial LLM version.
    """
    try:
        bare = _bare(symbol)
        if not bare:
            return {"error": "symbol is required"}
        return _call(run_multi_agent_analysis, _full(bare), _EXCHANGE, timeframe)
    except Exception as exc:
        return {"error": str(exc)}
