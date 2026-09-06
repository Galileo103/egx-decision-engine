"""Backtest the APP'S OWN rules — not textbook indicators.

Entry rules mirror the scanners the user actually trades from; exit rules
mirror the Position Guardian. Everything runs on Yahoo daily candles (so it
works while TradingView is rate-limited), long-only, one position at a time,
fixed-fractional sizing, EGX round-trip fees, conservative fills:

  * entry at the NEXT session's open after a signal (+ slippage)
  * stop checked on the bar's low, target on the bar's high; if both are
    touched the stop is assumed first; a gap through the stop fills at the open
  * trailing / breakeven / time stops are evaluated on the close

Four surfaces share the engine: single run, exit-rule comparison, stop sweep,
universe run — plus a replay of the user's real open positions under the
Guardian's rules. Every result carries a plain-language verdict and a sample-
size caveat, because eight trades prove nothing.
"""
from __future__ import annotations

import logging
import math
import statistics
import time
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from app.config import settings
from app.symbols import universe as universe_symbols

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

PERIOD_BARS = {"1y": 250, "2y": 500, "3y": 750, "5y": 1250}
MIN_TRADES_FOR_CONFIDENCE = 20

ENTRY_RULES: dict[str, dict[str, str]] = {
    "squeeze_breakout": {
        "label": "Bollinger squeeze breakout",
        "description": "Band width in the tightest 20% of the last 120 sessions, then a close above the "
                       "upper band with volume >= 1.5x its 20-day average. (The Squeeze scanner's trade.)",
    },
    "range_breakout": {
        "label": "20-day high breakout",
        "description": "Close above the prior 20-session high with volume >= 1.5x average, price above "
                       "the 50-day average. (The Volume-Breakout scanner's trade.)",
    },
    "pullback_trend": {
        "label": "Pullback in uptrend",
        "description": "20-day average above 50-day, 2-5 down closes into the 20-day average, then the "
                       "first up close. (The Guardian's 'pullback' event, traded.)",
    },
    "momentum_3": {
        "label": "Three rising closes",
        "description": "Three consecutive higher closes with price above the 20-day average and RSI14 "
                       "between 50 and 75. (The Momentum scanner's trade.)",
    },
}

EXIT_RULES: dict[str, dict[str, str]] = {
    "fixed": {
        "label": "Fixed stop & target",
        "description": "Stop 2 x ATR14 below entry; exit at +3R or at the stop. No adjustments.",
    },
    "atr_trail": {
        "label": "ATR trailing stop",
        "description": "Initial stop 2 x ATR; from day one the stop trails 2.5 x ATR below the highest close.",
    },
    "guardian": {
        "label": "Guardian rules",
        "description": "Stop 2 x ATR; at +1R the stop moves to breakeven and then trails 2.5 x ATR below "
                       "the highest close; take profit at +3R; time stop after 15 sessions inside +/-0.5R.",
    },
    "time_only": {
        "label": "Hold N sessions",
        "description": "Stop 2 x ATR for safety, otherwise sell at the close of the 20th session. A control.",
    },
}

DEFAULTS = {"stop_atr": 2.0, "trail_atr": 2.5, "target_r": 3.0, "time_stop_bars": 15,
            "hold_bars": 20, "breakeven_r": 1.0, "vol_mult": 1.5}


# ── indicators ───────────────────────────────────────────────────────────────


def _sma(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    s = 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _atr(h: list[float], l: list[float], c: list[float], n: int = 14) -> list[Optional[float]]:
    trs = []
    for i in range(len(c)):
        tr = h[i] - l[i]
        if i > 0:
            tr = max(tr, abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        trs.append(tr)
    return _sma(trs, n)


def _rsi(c: list[float], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    gains = losses = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g, lo = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            gains += g
            losses += lo
            if i == n:
                ag, al = gains / n, losses / n
                out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        else:
            ag = (ag * (n - 1) + g) / n
            al = (al * (n - 1) + lo) / n
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _bbw(c: list[float], n: int = 20, k: float = 2.0) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """(band width / middle, upper band)."""
    width: list[Optional[float]] = [None] * len(c)
    upper: list[Optional[float]] = [None] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        width[i] = (2 * k * sd) / m if m else None
        upper[i] = m + k * sd
    return width, upper


def _rvol_series(v: list[float], n: int = 20) -> list[Optional[float]]:
    """volume / median(previous n volumes) per bar; None until 10 prior bars have volume."""
    out: list[Optional[float]] = [None] * len(v)
    for i in range(1, len(v)):
        window = sorted(x for x in v[max(0, i - n):i] if x > 0)
        if len(window) < 10 or v[i] <= 0:
            continue
        med = window[len(window) // 2]
        out[i] = round(v[i] / med, 2) if med > 0 else None
    return out


def _rolling_max(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    for i in range(n, len(v)):
        out[i] = max(v[i - n:i])
    return out


def _pct_rank(v: list[Optional[float]], i: int, n: int) -> Optional[float]:
    """Percentile of v[i] within v[i-n+1..i] (0 = lowest)."""
    w = [x for x in v[max(0, i - n + 1):i + 1] if x is not None]
    if v[i] is None or len(w) < n // 2:
        return None
    return sum(1 for x in w if x < v[i]) / len(w)


class Ind:
    def __init__(self, candles: list[dict]):
        self.t = [str(c["time"]) for c in candles]
        self.o = [float(c["open"]) for c in candles]
        self.h = [float(c["high"]) for c in candles]
        self.l = [float(c["low"]) for c in candles]
        self.c = [float(c["close"]) for c in candles]
        self.v = [float(c.get("volume") or 0.0) for c in candles]
        self.sma20 = _sma(self.c, 20)
        self.sma50 = _sma(self.c, 50)
        self.atr = _atr(self.h, self.l, self.c)
        self.rsi = _rsi(self.c)
        self.bbw, self.bb_up = _bbw(self.c)
        self.hi20 = _rolling_max(self.h, 20)
        self.vavg = _sma(self.v, 20)
        # Relative volume vs the 20-bar MEDIAN (robust to one block-trade day);
        # stamped on every signal so the Scorecard can split edge by volume.
        self.rvol = _rvol_series(self.v, 20)
        self.n = len(candles)


# ── entry signals (return True when a signal closes on bar i) ────────────────


def _sig_squeeze(x: Ind, i: int, p: dict) -> bool:
    if x.bbw[i] is None or x.bb_up[i] is None or x.vavg[i] in (None, 0):
        return False
    pr = _pct_rank(x.bbw, i - 1, 120)
    return (pr is not None and pr <= 0.20 and x.c[i] > x.bb_up[i]
            and x.v[i] >= p["vol_mult"] * x.vavg[i])


def _sig_range(x: Ind, i: int, p: dict) -> bool:
    return (x.hi20[i] is not None and x.sma50[i] is not None and x.vavg[i] not in (None, 0)
            and x.c[i] > x.hi20[i] and x.c[i] > x.sma50[i] and x.v[i] >= p["vol_mult"] * x.vavg[i])


def _sig_pullback(x: Ind, i: int, p: dict) -> bool:
    if x.sma20[i] is None or x.sma50[i] is None or x.atr[i] is None or i < 6:
        return False
    if not (x.sma20[i] > x.sma50[i] and x.c[i] > x.sma50[i] and x.c[i] > x.c[i - 1]):
        return False
    down = 0
    k = i - 1
    while k > 0 and x.c[k] < x.c[k - 1]:
        down += 1
        k -= 1
    return 2 <= down <= 5 and abs(x.c[i - 1] - x.sma20[i - 1]) <= 1.0 * x.atr[i]


def _sig_momentum(x: Ind, i: int, p: dict) -> bool:
    return (i >= 3 and x.sma20[i] is not None and x.rsi[i] is not None
            and x.c[i] > x.c[i - 1] > x.c[i - 2] > x.c[i - 3]
            and x.c[i] > x.sma20[i] and 50 <= x.rsi[i] <= 75)


_SIGNALS: dict[str, Callable[[Ind, int, dict], bool]] = {
    "squeeze_breakout": _sig_squeeze, "range_breakout": _sig_range,
    "pullback_trend": _sig_pullback, "momentum_3": _sig_momentum,
}


# ── simulation ───────────────────────────────────────────────────────────────


def _fees(notional: float) -> float:
    return notional * settings.fee_pct_per_side / 100.0


def simulate(candles: list[dict], entry_rule: str, exit_rule: str, params: Optional[dict] = None,
             capital: float = 100_000.0, risk_pct: Optional[float] = None,
             slippage_pct: float = 0.1) -> dict:
    """Run one rule pair over candles. Returns trades, equity curve and metrics."""
    p = dict(DEFAULTS)
    p.update(params or {})
    sig = _SIGNALS[entry_rule]
    x = Ind(candles)
    risk_pct = settings.risk_pct if risk_pct is None else risk_pct
    equity = capital
    cash = capital
    pos: Optional[dict] = None
    trades: list[dict] = []
    curve: list[dict] = []
    slip = slippage_pct / 100.0
    start_i = 60

    for i in range(start_i, x.n):
        # ── manage the open position on this bar ─────────────────────────
        if pos is not None:
            exit_px: Optional[float] = None
            reason = None
            stop = pos["stop"]
            # Gap through the stop → filled at the open.
            if x.o[i] <= stop:
                exit_px, reason = x.o[i] * (1 - slip), "stop_gap"
            elif x.l[i] <= stop:
                exit_px, reason = stop * (1 - slip), "stop"
            elif pos["target"] is not None and x.h[i] >= pos["target"]:
                exit_px, reason = pos["target"] * (1 - slip), "target"
            if exit_px is None:
                pos["bars"] += 1
                pos["high_close"] = max(pos["high_close"], x.c[i])
                r_now = (x.c[i] - pos["entry"]) / pos["risk"]
                pos["peak_r"] = max(pos["peak_r"], r_now)
                atr = x.atr[i] or pos["atr"]
                if exit_rule == "atr_trail":
                    pos["stop"] = max(pos["stop"], pos["high_close"] - p["trail_atr"] * atr)
                elif exit_rule == "guardian":
                    if pos["peak_r"] >= p["breakeven_r"]:
                        pos["stop"] = max(pos["stop"], pos["entry"], pos["high_close"] - p["trail_atr"] * atr)
                    if pos["bars"] >= p["time_stop_bars"] and abs(r_now) < 0.5:
                        exit_px, reason = x.c[i] * (1 - slip), "time_stop"
                elif exit_rule == "time_only":
                    if pos["bars"] >= p["hold_bars"]:
                        exit_px, reason = x.c[i] * (1 - slip), "time"
            if exit_px is not None:
                qty = pos["qty"]
                proceeds = exit_px * qty
                fee = _fees(proceeds)
                cash += proceeds - fee
                pnl = (exit_px - pos["entry"]) * qty - fee - pos["entry_fee"]
                r = pnl / (pos["risk"] * qty) if pos["risk"] * qty else 0.0
                trades.append({
                    "entry_date": pos["entry_date"], "entry": round(pos["entry"], 4),
                    "exit_date": x.t[i], "exit": round(exit_px, 4), "reason": reason,
                    "qty": qty, "pnl": round(pnl, 2), "r": round(r, 2), "bars": pos["bars"],
                    "peak_r": round(pos["peak_r"], 2), "initial_stop": round(pos["initial_stop"], 4),
                })
                pos = None
        # ── new entry: signal on bar i-1 → buy at this bar's open ─────────
        if pos is None and i >= 1 and sig(x, i - 1, p) and x.atr[i - 1]:
            entry = x.o[i] * (1 + slip)
            atr = x.atr[i - 1]
            stop = entry - p["stop_atr"] * atr
            risk_ps = entry - stop
            if risk_ps <= 0:
                continue
            qty = int((equity * risk_pct / 100.0) // risk_ps)
            if qty * entry > cash:
                qty = int(cash // entry)
            if qty <= 0:
                continue
            fee = _fees(qty * entry)
            cash -= qty * entry + fee
            target = entry + p["target_r"] * risk_ps if exit_rule in ("fixed", "guardian") else None
            pos = {"entry": entry, "entry_date": x.t[i], "qty": qty, "stop": stop, "initial_stop": stop,
                   "risk": risk_ps, "target": target, "atr": atr, "bars": 0, "high_close": x.c[i],
                   "peak_r": 0.0, "entry_fee": fee}
        mark = cash + (pos["qty"] * x.c[i] if pos else 0.0)
        equity = mark
        curve.append({"time": x.t[i], "value": round(mark, 2)})

    # Close any open position at the last close (marked, flagged).
    open_trade = None
    if pos is not None:
        px = x.c[-1]
        pnl = (px - pos["entry"]) * pos["qty"] - pos["entry_fee"] - _fees(px * pos["qty"])
        open_trade = {"entry_date": pos["entry_date"], "entry": round(pos["entry"], 4), "mark": round(px, 4),
                      "pnl_open": round(pnl, 2), "r_open": round(pnl / (pos["risk"] * pos["qty"]), 2),
                      "bars": pos["bars"], "stop_now": round(pos["stop"], 4)}
    metrics = _metrics(trades, curve, capital, x)
    metrics["open_trade"] = open_trade
    return {"trades": trades, "equity": curve, "metrics": metrics,
            "bars": x.n, "from": x.t[start_i] if x.n > start_i else None, "to": x.t[-1] if x.n else None}


def _metrics(trades: list[dict], curve: list[dict], capital: float, x: Ind) -> dict:
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    rs = [t["r"] for t in trades]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    final = curve[-1]["value"] if curve else capital
    peak, mdd = -1e18, 0.0
    for pt in curve:
        peak = max(peak, pt["value"])
        mdd = max(mdd, (peak - pt["value"]) / peak if peak > 0 else 0.0)
    start_i = x.n - len(curve) if curve else 0
    bh = (x.c[-1] / x.c[start_i] - 1.0) * 100.0 if curve and x.c[start_i] else None
    years = max(len(curve) / 245.0, 1e-9)
    total_ret = (final / capital - 1.0) * 100.0
    cagr = ((final / capital) ** (1 / years) - 1.0) * 100.0 if final > 0 and years > 0.2 else None
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    # Binomial 95% CI on the win rate (normal approximation).
    wr = len(wins) / n if n else None
    ci = None
    if wr is not None and n:
        se = math.sqrt(wr * (1 - wr) / n)
        ci = [round(max(0.0, wr - 1.96 * se) * 100, 1), round(min(1.0, wr + 1.96 * se) * 100, 1)]
    return {
        "trades": n, "wins": len(wins), "losses": len(losses),
        "win_rate": round(wr * 100, 1) if wr is not None else None, "win_rate_ci95": ci,
        "avg_r": round(sum(rs) / n, 2) if n else None,
        "median_r": round(statistics.median(rs), 2) if n else None,
        "best_r": round(max(rs), 2) if n else None, "worst_r": round(min(rs), 2) if n else None,
        "expectancy_egp": round(sum(t["pnl"] for t in trades) / n, 2) if n else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (None if not wins else 99.0),
        "net_pnl": round(final - capital, 2), "final_equity": round(final, 2),
        "total_return_pct": round(total_ret, 2), "cagr_pct": round(cagr, 2) if cagr is not None else None,
        "max_drawdown_pct": round(mdd * 100, 2),
        "buy_hold_pct": round(bh, 2) if bh is not None else None,
        "avg_bars": round(sum(t["bars"] for t in trades) / n, 1) if n else None,
        "exit_reasons": reasons,
        "sufficient_sample": n >= MIN_TRADES_FOR_CONFIDENCE,
    }


# ── data + benchmark ─────────────────────────────────────────────────────────


def _candles(symbol: str, period: str) -> list[dict]:
    from app.services import leaders

    bars = PERIOD_BARS.get(period, 500)
    rng = "5y" if bars > 500 else ("2y" if bars > 250 else "1y")
    c = leaders.daily_candles(symbol, rng)
    return c[-(bars + 60):] if c else []


def _index_return(d0: Optional[str], d1: Optional[str]) -> Optional[float]:
    if not d0 or not d1:
        return None
    try:
        from app.services import leaders

        # Multi-year windows need the long benchmark; fall back to the 1y one.
        bench = leaders.benchmark_series(range_="5y")
        if not bench.get("dates") or bench["dates"][0] > d0:
            bench = leaders.benchmark_series()
        r = leaders.benchmark_return(bench, d0, d1)
        return round(r * 100.0, 2) if r is not None else None
    except Exception:  # noqa: BLE001
        return None


# ── plain-language verdict ───────────────────────────────────────────────────


def verdict(symbol: str, entry_rule: str, exit_rule: str, res: dict, capital: float,
            index_pct: Optional[float]) -> str:
    m = res["metrics"]
    n = m["trades"]
    e = ENTRY_RULES.get(entry_rule, {}).get("label", entry_rule)
    ex = EXIT_RULES.get(exit_rule, {}).get("label", exit_rule)
    span = f"from {res.get('from')} to {res.get('to')}" if res.get("from") else ""
    if n == 0:
        return (f"On {symbol} {span}, the '{e}' rule never triggered a trade. Either the setup did not "
                f"occur or the volume/trend filters were never met. Nothing to judge.")
    parts = [
        f"On {symbol} {span}, '{e}' with '{ex}' exits made {n} trade{'s' if n != 1 else ''}, "
        f"won {m['win_rate']:.0f}%, averaged {m['avg_r']:+.2f}R per trade, and turned "
        f"{capital:,.0f} into {m['final_equity']:,.0f} EGP after fees ({m['total_return_pct']:+.1f}%)."
    ]
    bench = []
    if m.get("buy_hold_pct") is not None:
        bench.append(f"just holding {symbol} returned {m['buy_hold_pct']:+.1f}%")
    if index_pct is not None:
        bench.append(f"EGX30 returned {index_pct:+.1f}%")
    if bench:
        parts.append("Over the same window " + " and ".join(bench) + ".")
    parts.append(f"The worst peak-to-trough drop in account value was {m['max_drawdown_pct']:.1f}%.")
    if not m["sufficient_sample"]:
        ci = m.get("win_rate_ci95")
        parts.append(f"Only {n} trades: the true win rate could be anywhere between "
                     f"{ci[0]:.0f}% and {ci[1]:.0f}%. Treat this as a sketch, not evidence."
                     if ci else f"Only {n} trades — treat this as a sketch, not evidence.")
    if m.get("profit_factor") is not None and n >= 5:
        pf = m["profit_factor"]
        if pf >= 99:
            parts.append("There were no losing trades at all.")
        elif pf < 0.5:
            parts.append("Losses dwarfed the gains — this rule lost money on this stock.")
        elif pf < 1.0:
            parts.append(f"Winners covered only {pf:.1f} of every 1.0 lost.")
        else:
            parts.append(f"Winners paid for losers {pf:.1f} times over.")
    return " ".join(parts)


# ── public API ───────────────────────────────────────────────────────────────


def run(symbol: str, entry_rule: str = "squeeze_breakout", exit_rule: str = "guardian",
        period: str = "2y", capital: float = 100_000.0, params: Optional[dict] = None,
        slippage_pct: float = 0.1) -> dict:
    try:
        sym = str(symbol or "").upper().strip().split(":")[-1]
        if entry_rule not in ENTRY_RULES or exit_rule not in EXIT_RULES:
            return {"error": f"unknown rule: {entry_rule}/{exit_rule}"}
        candles = _candles(sym, period)
        if len(candles) < 120:
            return {"error": f"not enough daily history for {sym} ({len(candles)} bars)"}
        res = simulate(candles, entry_rule, exit_rule, params, capital, None, slippage_pct)
        idx = _index_return(res.get("from"), res.get("to"))
        res.update({
            "symbol": sym, "entry_rule": entry_rule, "exit_rule": exit_rule, "period": period,
            "capital": capital, "index_return_pct": idx,
            "verdict": verdict(sym, entry_rule, exit_rule, res, capital, idx),
            "rules": {"entry": ENTRY_RULES[entry_rule], "exit": EXIT_RULES[exit_rule],
                      "params": {**DEFAULTS, **(params or {})}},
            "costs": {"fee_pct_per_side": settings.fee_pct_per_side, "slippage_pct": slippage_pct,
                      "risk_pct_per_trade": settings.risk_pct},
            "as_of": datetime.now(CAIRO).isoformat(),
        })
        return res
    except Exception as exc:  # noqa: BLE001
        logger.exception("rules_backtest.run failed")
        return {"error": str(exc)}


def compare_exits(symbol: str, entry_rule: str = "squeeze_breakout", period: str = "2y",
                  capital: float = 100_000.0, slippage_pct: float = 0.1) -> dict:
    """Same entries, every exit style — which way of getting out pays on this stock?"""
    try:
        sym = str(symbol or "").upper().strip().split(":")[-1]
        candles = _candles(sym, period)
        if len(candles) < 120:
            return {"error": f"not enough daily history for {sym} ({len(candles)} bars)"}
        rows = []
        for ex in EXIT_RULES:
            r = simulate(candles, entry_rule, ex, None, capital, None, slippage_pct)
            m = r["metrics"]
            rows.append({"exit_rule": ex, "label": EXIT_RULES[ex]["label"], **{k: m[k] for k in (
                "trades", "win_rate", "avg_r", "expectancy_egp", "profit_factor", "total_return_pct",
                "max_drawdown_pct", "avg_bars", "exit_reasons", "sufficient_sample")}})
        ranked = sorted(rows, key=lambda r: (r["avg_r"] if r["avg_r"] is not None else -99), reverse=True)
        best = ranked[0]
        summary = (f"On {sym}, '{ENTRY_RULES[entry_rule]['label']}' entries paid best with '{best['label']}' "
                   f"exits: {best['avg_r']:+.2f}R average over {best['trades']} trades "
                   f"({best['total_return_pct']:+.1f}% total)." if best["trades"] else
                   f"'{ENTRY_RULES[entry_rule]['label']}' never triggered on {sym} in this window.")
        if best["trades"] and not best["sufficient_sample"]:
            summary += " Few trades — the ranking could flip with one more winner or loser."
        return {"symbol": sym, "entry_rule": entry_rule, "period": period, "rows": ranked, "best": best["exit_rule"],
                "summary": summary, "as_of": datetime.now(CAIRO).isoformat()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def stop_sweep(symbol: str, entry_rule: str = "squeeze_breakout", exit_rule: str = "fixed",
               period: str = "2y", capital: float = 100_000.0,
               stops: Optional[list[float]] = None) -> dict:
    """How tight can the stop be before EGX noise eats it?"""
    try:
        sym = str(symbol or "").upper().strip().split(":")[-1]
        candles = _candles(sym, period)
        if len(candles) < 120:
            return {"error": f"not enough daily history for {sym} ({len(candles)} bars)"}
        stops = stops or [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
        rows = []
        for s in stops:
            r = simulate(candles, entry_rule, exit_rule, {"stop_atr": s}, capital)
            m = r["metrics"]
            stopped = sum(v for k, v in m["exit_reasons"].items() if k.startswith("stop"))
            rows.append({"stop_atr": s, "trades": m["trades"], "win_rate": m["win_rate"], "avg_r": m["avg_r"],
                         "expectancy_egp": m["expectancy_egp"], "total_return_pct": m["total_return_pct"],
                         "max_drawdown_pct": m["max_drawdown_pct"],
                         "stopped_out_pct": round(stopped / m["trades"] * 100, 1) if m["trades"] else None})
        valid = [r for r in rows if r["trades"]]
        best = max(valid, key=lambda r: r["expectancy_egp"] or -1e9) if valid else None
        atr_now = Ind(candles).atr[-1]
        summary = (f"On {sym} the best stop distance was {best['stop_atr']:g} x ATR "
                   f"(about {best['stop_atr'] * atr_now / candles[-1]['close'] * 100:.1f}% at today's volatility): "
                   f"{best['win_rate']:.0f}% wins, {best['avg_r']:+.2f}R average. Tighter stops get shaken out by "
                   f"normal daily range; looser ones give back too much." if best and atr_now else
                   "No trades triggered at any stop distance.")
        return {"symbol": sym, "entry_rule": entry_rule, "exit_rule": exit_rule, "period": period, "rows": rows,
                "atr_now": round(atr_now, 4) if atr_now else None, "best_stop_atr": best["stop_atr"] if best else None,
                "summary": summary, "as_of": datetime.now(CAIRO).isoformat()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def universe_run(universe: str = "EGX30", entry_rule: str = "squeeze_breakout", exit_rule: str = "guardian",
                 period: str = "2y", capital: float = 100_000.0, limit: int = 40) -> dict:
    """The same rule on every stock in a universe — distribution, not one lucky chart."""
    try:
        started = time.monotonic()
        syms = universe_symbols(universe)[: max(1, int(limit))]
        rows = []
        pooled: list[dict] = []
        skipped = 0
        for s in syms:
            candles = _candles(s, period)
            if len(candles) < 120:
                skipped += 1
                continue
            r = simulate(candles, entry_rule, exit_rule, None, capital)
            m = r["metrics"]
            pooled.extend(r["trades"])
            rows.append({"symbol": s, "trades": m["trades"], "win_rate": m["win_rate"], "avg_r": m["avg_r"],
                         "total_return_pct": m["total_return_pct"], "buy_hold_pct": m["buy_hold_pct"],
                         "max_drawdown_pct": m["max_drawdown_pct"]})
            time.sleep(0.05)
        traded = [r for r in rows if r["trades"]]
        rets = [r["total_return_pct"] for r in traded]
        n = len(pooled)
        wins = sum(1 for t in pooled if t["pnl"] > 0)
        avg_r = sum(t["r"] for t in pooled) / n if n else None
        beat_bh = sum(1 for r in traded if r["buy_hold_pct"] is not None and r["total_return_pct"] > r["buy_hold_pct"])
        rows.sort(key=lambda r: (r["total_return_pct"] if r["trades"] else -1e9), reverse=True)
        # The same trades split by the market regime on their entry date, so the
        # edge table can say "works in bull tapes, not in bear ones".
        by_regime: dict[str, dict] = {}
        try:
            from app.services import regime as _regime

            reg_series = _regime.series()
            groups: dict[str, list[dict]] = {}
            for t in pooled:
                state = reg_series.at(str(t.get("entry_date") or ""))
                if state:
                    groups.setdefault(state, []).append(t)
            for state, ts in groups.items():
                k = len(ts)
                by_regime[state] = {"trades": k, "win_rate": round(sum(1 for t in ts if t["pnl"] > 0) / k * 100, 1),
                                    "avg_r": round(sum(t["r"] for t in ts) / k, 2)}
        except Exception as exc:  # noqa: BLE001 — the split is a bonus, never a blocker
            logger.warning("universe_run regime split failed: %s", exc)
        summary = (
            f"'{ENTRY_RULES[entry_rule]['label']}' with '{EXIT_RULES[exit_rule]['label']}' exits across {len(rows)} "
            f"{universe} stocks over {period}: it traded on {len(traded)} of them, {n} trades in total, "
            f"{wins / n * 100:.0f}% winners, {avg_r:+.2f}R average. Median stock result {statistics.median(rets):+.1f}% "
            f"(best {max(rets):+.1f}%, worst {min(rets):+.1f}%); it beat simply holding the stock on {beat_bh} of "
            f"{len(traded)}. " + ("A rule that only works on a handful of names is curve-fitting; this one "
                                 + ("looks broad." if beat_bh >= len(traded) / 2 else "does not."))
            if n else f"'{ENTRY_RULES[entry_rule]['label']}' triggered no trades across {len(rows)} {universe} stocks."
        )
        return {"universe": universe, "entry_rule": entry_rule, "exit_rule": exit_rule, "period": period,
                "rows": rows, "pooled": {"trades": n, "win_rate": round(wins / n * 100, 1) if n else None,
                                         "avg_r": round(avg_r, 2) if avg_r is not None else None,
                                         "symbols_traded": len(traded), "symbols_beat_buy_hold": beat_bh,
                                         "median_return_pct": round(statistics.median(rets), 2) if rets else None,
                                         "by_regime": by_regime},
                "skipped_no_data": skipped, "summary": summary, "elapsed_s": round(time.monotonic() - started, 1),
                "as_of": datetime.now(CAIRO).isoformat()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("universe_run failed")
        return {"error": str(exc)}


def replay_positions() -> dict:
    """Replay each OPEN position from its entry date under the Guardian's rules,
    next to what actually holding it has done and what EGX30 did."""
    try:
        from app.services import portfolio

        rows = []
        for pos in portfolio.list_positions("open"):
            sym = str(pos["symbol"])
            opened = str(pos.get("opened_at") or "")[:10]
            candles = _candles(sym, "1y")
            if not candles:
                rows.append({"symbol": sym, "error": "no history"})
                continue
            entry = float(pos["entry"])
            stop0 = float(pos.get("initial_stop") or pos.get("stop") or 0) or None
            after = [c for c in candles if str(c["time"]) > opened]
            x = Ind(candles)
            i0 = x.n - len(after)
            atr = x.atr[i0 - 1] if i0 > 0 and x.atr[i0 - 1] else (x.atr[-1] or 0.0)
            risk = (entry - stop0) if stop0 and stop0 < entry else 2.0 * atr
            stop = entry - risk
            hi = entry
            peak_r = 0.0
            exit_px = exit_reason = exit_date = None
            bars = 0
            for k in range(i0, x.n):
                if x.l[k] <= stop:
                    exit_px, exit_reason, exit_date = (min(x.o[k], stop)), "stop", x.t[k]
                    break
                if x.h[k] >= entry + 3 * risk:
                    exit_px, exit_reason, exit_date = entry + 3 * risk, "target_3R", x.t[k]
                    break
                bars += 1
                hi = max(hi, x.c[k])
                r_now = (x.c[k] - entry) / risk if risk else 0.0
                peak_r = max(peak_r, r_now)
                a = x.atr[k] or atr
                if peak_r >= 1.0:
                    stop = max(stop, entry, hi - 2.5 * a)
                if bars >= 15 and abs(r_now) < 0.5:
                    exit_px, exit_reason, exit_date = x.c[k], "time_stop", x.t[k]
                    break
            last = x.c[-1]
            qty = float(pos["qty"])
            actual_pnl = (last - entry) * qty
            plan_px = exit_px if exit_px is not None else last
            plan_pnl = (plan_px - entry) * qty
            idx = _index_return(opened, x.t[-1])
            rows.append({
                "symbol": sym, "opened": opened, "entry": entry, "qty": qty, "sessions": len(after),
                "last": last, "actual_pnl": round(actual_pnl, 2), "actual_pct": round((last / entry - 1) * 100, 2),
                "actual_r": round((last - entry) / risk, 2) if risk else None,
                "plan_status": exit_reason or "still holding",
                "plan_exit": round(plan_px, 4) if exit_px is not None else None, "plan_exit_date": exit_date,
                "plan_pnl": round(plan_pnl, 2), "plan_stop_now": round(stop, 4), "peak_r": round(peak_r, 2),
                "index_pct": idx, "risk_basis": "your initial stop" if (stop0 and stop0 < entry) else "2 x ATR at entry",
            })
        acted = [r for r in rows if r.get("plan_status") not in (None, "still holding") and "error" not in r]
        summary = (f"Under the Guardian's rules, {len(acted)} of {len(rows)} open positions would already have been "
                   f"closed ({', '.join(r['symbol'] + ' by ' + r['plan_status'] for r in acted)}). "
                   + ("The others are still inside their plan." if len(acted) < len(rows) else "")
                   if rows else "No open positions to replay.")
        return {"rows": rows, "summary": summary, "as_of": datetime.now(CAIRO).isoformat()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
