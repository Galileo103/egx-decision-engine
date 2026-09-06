"""Compare two to four stocks side by side — "which one gets the money?"

Every row already exists somewhere in the app (buy checklist, levels-based
risk plan, Scorecard weights, Proven-edge verdicts, relative strength,
liquidity, the sell checklist for names you hold, the portfolio heat rule).
This module calls them for several symbols at once and adds the one thing a
single-stock page cannot: a ranking with a reason.

The ranking is deliberately simple and readable, not a blended score:
    1. no failing pillar beats any failing pillar (Trend / Risk plan are fatal);
    2. then the checklist verdict (setup > watch > no_setup);
    3. then reward-to-risk of the levels-based plan;
    4. then measured evidence (sum of Scorecard weights over signal families);
    5. then relative strength over one month.
The headline names the winner and says why each other name lost. Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.config import settings

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

MAX_SYMBOLS = 4
_VERDICT_RANK = {"setup": 0, "watch": 1, "no_setup": 2}
_FATAL = ("trend", "risk")


def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _edge_lookup() -> dict[str, dict]:
    try:
        rows = db.query("SELECT name, kind, verdict, n, hit_rate, edge_metric, extra_json FROM proven_edge "
                        "WHERE kind IN ('scanner', 'pattern')")
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        try:
            extra = json.loads(r.get("extra_json") or "{}")
        except (TypeError, ValueError):
            extra = {}
        out[str(r["name"])] = {"verdict": r["verdict"], "n": r["n"], "hit_rate": r["hit_rate"],
                               "excess": r["edge_metric"], "excess_vs_random": extra.get("excess_vs_random")}
    return out


def _signals_today(symbol: str) -> list[str]:
    """Live scanner / rule / pattern hits for the symbol on the latest journaled session(s)."""
    try:
        d = db.query("SELECT MAX(date) AS d FROM scanner_hits WHERE COALESCE(source,'live') = 'live' "
                     "AND scanner NOT LIKE 'checklist_%'")
        date = d[0].get("d") if d else None
        if not date:
            return []
        rows = db.query("SELECT DISTINCT scanner FROM scanner_hits WHERE symbol = ? AND date = ? "
                        "AND COALESCE(source,'live') = 'live' AND scanner NOT LIKE 'checklist_%'", (symbol, date))
        return [str(r["scanner"]) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _column(symbol: str, weights: dict[str, float], edge: dict[str, dict], held: dict[str, dict],
            open_heat_egp: float, sector_counts: dict[str, int]) -> dict:
    from app.services import checklist as CK, leaders, portfolio, screeners, sell_checklist as SC
    from app.services.rules_backtest import Ind

    col: dict[str, Any] = {"symbol": symbol}
    ck = CK.checklist(symbol)
    if not isinstance(ck, dict) or "error" in ck:
        col["error"] = (ck or {}).get("error") or "checklist unavailable"
        return col
    pillars = {p["key"]: p["status"] for p in ck.get("pillars") or []}
    texts = {p["key"]: p["text"] for p in ck.get("pillars") or []}
    fails = [k for k, v in pillars.items() if v == "fail"]
    col.update({
        "price": ck.get("price"), "verdict": ck.get("verdict"), "headline": ck.get("headline"),
        "score": ck.get("score"), "pillars": pillars, "pillar_text": texts, "fails": fails,
        "fatal_fail": any(k in _FATAL for k in fails), "risk_plan": ck.get("risk_plan") or {},
        "levels_position": ck.get("levels_position"), "as_of": ck.get("as_of"),
    })
    # Extension: how far above the 20-day average, in ATR.
    candles = leaders.daily_candles(symbol)
    if len(candles) >= 60:
        x = Ind(candles)
        price, sma20, atr = x.c[-1], x.sma20[-1], x.atr[-1]
        col["extension_atr"] = round((price - sma20) / atr, 2) if sma20 and atr else None
    else:
        col["extension_atr"] = None
    # Relative strength and liquidity.
    try:
        rs = leaders._symbol_metrics(symbol, leaders.benchmark_series())
    except Exception:  # noqa: BLE001
        rs = None
    col["rvol"] = ck.get("rvol")
    try:
        col["sector_rs"] = leaders.sector_context(symbol)
    except Exception:  # noqa: BLE001
        col["sector_rs"] = None
    col["rs"] = ({"excess_1m": rs.get("excess_1m"), "excess_3m": rs.get("excess_3m"),
                  "pct_from_52w_high": rs.get("pct_from_52w_high"), "new_high": rs.get("new_high"),
                  "median_value_20d": rs.get("median_value_20d")} if rs else None)
    # Evidence today: signals, their weights and measured verdicts.
    sigs = _signals_today(symbol)
    col["signals"] = [{"name": s, "weight": weights.get(s, 1.0), "edge": edge.get(s),
                       "kind": "pattern" if s.startswith("pattern_") else "scanner"} for s in sigs]
    # Same definition as the Candidates list: scanners and proven rules by signal
    # family. Patterns are listed as evidence but not summed — a stock with six
    # overlapping shape names would otherwise out-weigh a clean breakout.
    core = [s for s in sigs if not s.startswith("pattern_")]
    col["evidence_weight"] = screeners._evidence_weight(core, weights) if core else 0.0
    best = None
    for s in col["signals"]:
        e = s.get("edge") or {}
        if e.get("verdict") == "edge" and (best is None or (e.get("excess_vs_random") or 0) > ((best.get("edge") or {}).get("excess_vs_random") or 0)):
            best = s
    col["strongest_signal"] = best
    # Portfolio fit.
    sector = portfolio._sector_of(symbol)
    col["sector"] = sector
    col["held_in_sector"] = sector_counts.get(sector, 0) if sector else 0
    rp = col["risk_plan"]
    account = float(settings.account_size) or 0.0
    new_risk = None
    if rp.get("entry") and rp.get("stop") and rp.get("shares_at_risk_pct"):
        new_risk = (float(rp["entry"]) - float(rp["stop"])) * float(rp["shares_at_risk_pct"])
    col["heat_after_pct"] = (round((open_heat_egp + (new_risk or 0.0)) / account * 100.0, 2) if account else None)
    col["heat_cap_pct"] = portfolio.MAX_OPEN_HEAT_PCT
    # Held? then the sell side too.
    pos = held.get(symbol)
    col["held"] = bool(pos)
    if pos:
        sc = SC.sell_checklist(symbol, position=pos, candles=candles)
        col["sell"] = SC.compact(sc)
        col["position"] = {"qty": pos.get("qty"), "entry": pos.get("entry"), "stop": pos.get("stop"),
                           "target1": pos.get("target1"), "target2": pos.get("target2")}
    else:
        col["sell"] = None
        col["position"] = None
    return col


def _rank_key(c: dict) -> tuple:
    if c.get("error"):
        return (9, 9, 0.0, 0.0, 0.0)
    rr = _num((c.get("risk_plan") or {}).get("rr")) or 0.0
    rs1 = _num((c.get("rs") or {}).get("excess_1m")) or 0.0
    return (1 if c.get("fails") else 0, _VERDICT_RANK.get(str(c.get("verdict") or ""), 3), -rr,
            -(c.get("evidence_weight") or 0.0), -rs1)


def _why_lost(c: dict, winner: dict) -> str:
    if c.get("error"):
        return f"{c['symbol']}: no data ({c['error']})."
    rp = c.get("risk_plan") or {}
    if c.get("fails"):
        names = ", ".join(k.replace("_", " ") for k in c["fails"])
        tail = ""
        if "risk" in c["fails"] and rp.get("rr") is not None and rp.get("target") is not None:
            tail = (f" ({rp['rr']:.1f}R to the first resistance {float(rp['target']):.2f} — wait for a pullback "
                    f"toward support or a close above it)")
        return f"{c['symbol']} waits: {names} against it{tail}."
    if _VERDICT_RANK.get(str(c.get("verdict") or ""), 3) > _VERDICT_RANK.get(str(winner.get("verdict") or ""), 3):
        return f"{c['symbol']}: {str(c.get('verdict')).replace('_', ' ')} only ({c.get('score')}/6)."
    w_rr, c_rr = _num((winner.get("risk_plan") or {}).get("rr")), _num(rp.get("rr"))
    if w_rr is not None and c_rr is not None and c_rr < w_rr:
        return f"{c['symbol']}: same verdict but less room — {c_rr:.1f}R versus {w_rr:.1f}R."
    if (c.get("evidence_weight") or 0) < (winner.get("evidence_weight") or 0):
        return f"{c['symbol']}: same verdict and room, weaker evidence ({c.get('evidence_weight'):.2f} vs {winner.get('evidence_weight'):.2f})."
    return f"{c['symbol']}: a close second — weaker one-month strength."


def compare(symbols: list[str]) -> dict:
    """Side-by-side comparison of 2..MAX_SYMBOLS symbols. Never raises."""
    try:
        from app.services import portfolio, scorecard

        clean: list[str] = []
        for s in symbols or []:
            sym = str(s or "").upper().strip().split(":")[-1]
            if sym and sym not in clean:
                clean.append(sym)
        truncated = clean[MAX_SYMBOLS:]
        clean = clean[:MAX_SYMBOLS]
        if len(clean) < 2:
            return {"error": "Give two to four symbols to compare.", "symbols": clean}
        weights = scorecard.signal_weights()
        edge = _edge_lookup()
        positions = portfolio.list_positions("open")
        held = {str(p["symbol"]).upper(): p for p in positions}
        open_heat = 0.0
        sector_counts: dict[str, int] = {}
        for p in positions:
            e, st, q = _num(p.get("entry")) or 0.0, _num(p.get("stop")), _num(p.get("qty")) or 0.0
            if st is not None:
                open_heat += max(0.0, e - st) * q
            sec = portfolio._sector_of(str(p.get("symbol") or ""))
            if sec:
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
        cols = [_column(s, weights, edge, held, open_heat, sector_counts) for s in clean]
        ranked = sorted(cols, key=_rank_key)
        winner = ranked[0] if not ranked[0].get("error") else None
        for i, c in enumerate(ranked):
            c["rank"] = i + 1
        if winner:
            rp = winner.get("risk_plan") or {}
            why = []
            if not winner.get("fails"):
                why.append("no failing pillar")
            else:
                why.append("fewest problems")
            if rp.get("rr") is not None:
                why.append(f"{rp['rr']:.1f}R to the first target")
            if winner.get("evidence_weight"):
                why.append(f"evidence {winner['evidence_weight']:.2f}")
            if winner.get("strongest_signal"):
                ss = winner["strongest_signal"]
                why.append(f"{ss['name'].replace('_', ' ')} is a measured edge (n={ (ss.get('edge') or {}).get('n')})")
            head = f"{winner['symbol']} first: " + ", ".join(why) + "."
            if winner.get("fails"):
                head = f"No clean winner — {winner['symbol']} has the fewest problems ({', '.join(winner['fails'])} against it)."
            losers = " ".join(_why_lost(c, winner) for c in ranked[1:])
            headline = head + (" " + losers if losers else "")
        else:
            headline = "Nothing to rank — no symbol returned data."
        out = {
            "symbols": clean, "truncated": truncated, "columns": cols,
            "ranking": [c["symbol"] for c in ranked], "winner": winner["symbol"] if winner else None,
            "headline": headline, "account_size": float(settings.account_size) or None,
            "risk_pct": settings.risk_pct, "open_heat_pct": (round(open_heat / float(settings.account_size) * 100.0, 2)
                                                              if float(settings.account_size or 0) else None),
            "as_of": datetime.now(CAIRO).isoformat(),
            "basis": ("Each column is the stock's own buy checklist, levels-based risk plan, today's journaled "
                      "signals with their Scorecard weight and Proven-edge verdict, relative strength versus EGX30, "
                      "liquidity, extension above the 20-day average in ATR, sector, portfolio heat after the trade at "
                      f"{settings.risk_pct:g}% risk, and — for names you hold — the sell checklist. Ranking: no failing "
                      "pillar first, then checklist verdict, then reward-to-risk, then evidence, then one-month strength."),
        }
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("compare failed")
        return {"error": str(exc)}
