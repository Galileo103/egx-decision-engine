"""Proven-rules scanner — the app's own candle rules as daily scanners.

The four entry rules of the rules backtester (``rules_backtest.ENTRY_RULES``)
are the trades the replay measured across five years of EGX history: the
20-day high breakout and the squeeze breakout earned a real edge, the three
rising closes and the pullback did not. This module runs those same rules on
the LAST completed daily bar of every listed EGX stock — on Yahoo candles, so
it never depends on TradingView and never rate-limits — and journals the hits
into ``scanner_hits`` under the rule's own name. Because the Scorecard already
holds thousands of replayed outcomes for these names, the hits enter the
Candidates ranking with a measured weight from day one.

Runs in the post-close job and on demand (background). Never raises.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app import db
from app.config import settings
from app.services.bgjob import BackgroundJob
from app.symbols import universe as universe_symbols

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

RULES: tuple[str, ...] = ("range_breakout", "squeeze_breakout", "momentum_3", "pullback_trend")
#: Bars needed before the rules are meaningful (SMA50 + 120-bar band-width rank).
MIN_BARS = 160
DEFAULT_UNIVERSE = "ALL"
_PAUSE_S = 0.02

job = BackgroundJob("rule_scan")


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _edge_lookup() -> dict[str, dict]:
    """Stored Proven-edge verdicts for the rules (empty when never computed)."""
    try:
        rows = db.query("SELECT name, verdict, verdict_text, n, hit_rate, edge_metric, extra_json FROM proven_edge "
                        "WHERE kind IN ('scanner', 'rule') AND name IN (%s)" % ",".join("?" * len(RULES)), RULES)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        try:
            extra = json.loads(r.get("extra_json") or "{}")
        except (TypeError, ValueError):
            extra = {}
        # prefer the signal-graded row (kind scanner) — it is what the weight uses
        cur = out.get(r["name"])
        if cur is None or extra.get("rate_vs_random_pp") is not None:
            out[r["name"]] = {"verdict": r["verdict"], "verdict_text": r["verdict_text"], "n": r["n"],
                              "hit_rate": r["hit_rate"], "edge_metric": r["edge_metric"],
                              "rate_vs_random_pp": extra.get("rate_vs_random_pp"),
                              "excess_vs_random": extra.get("excess_vs_random")}
    return out


def rule_hits_last_bar(symbol: str, candles: list[dict]) -> list[dict]:
    """Rules that fired on the last completed bar of ``candles``. Pure."""
    from app.services import rules_backtest as RB

    if len(candles) < MIN_BARS:
        return []
    x = RB.Ind(candles)
    i = x.n - 1
    params = dict(RB.DEFAULTS)
    out: list[dict] = []
    vals = sorted(x.c[k] * x.v[k] for k in range(max(0, x.n - 20), x.n))
    median_value = vals[len(vals) // 2] if vals else None
    for rule in RULES:
        fn = RB._SIGNALS.get(rule)
        if fn is None:
            continue
        try:
            fired = fn(x, i, params)
        except Exception:  # noqa: BLE001
            fired = False
        if not fired:
            continue
        prev = x.c[i - 1] if i >= 1 and x.c[i - 1] else None
        vavg, atr_i, sma50_i = x.vavg[i], x.atr[i], x.sma50[i]
        out.append({
            "symbol": symbol, "scanner": rule, "date": x.t[i],
            "price": round(x.c[i], 4),
            "change_pct": round((x.c[i] / prev - 1.0) * 100.0, 2) if prev else None,
            "volume_ratio": round(x.v[i] / vavg, 2) if vavg else None,
            "rvol": x.rvol[i],
            "atr14": round(atr_i, 4) if atr_i is not None else None,
            "sma50": round(sma50_i, 4) if sma50_i is not None else None,
            "median_value_20d": round(median_value, 0) if median_value else None,
        })
    return out


def _persist(rows: list[dict]) -> int:
    if not rows:
        return 0
    now = _now_iso()
    return db.executemany(
        "INSERT OR REPLACE INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
        "VALUES (?, ?, ?, ?, ?, 'live')",
        [(r["date"], r["scanner"], r["symbol"],
          json.dumps({k: r.get(k) for k in ("price", "change_pct", "volume_ratio", "rvol", "atr14", "sma50",
                                            "median_value_20d", "rule")}, default=str), now) for r in rows],
    )


def scan(universe: str = DEFAULT_UNIVERSE, persist: bool = True, limit: Optional[int] = None,
         rules: Optional[list[str]] = None) -> dict:
    """Run the proven rules on the last bar of every stock in ``universe``. Never raises."""
    try:
        from app.services import leaders

        started = time.monotonic()
        uni = (universe or DEFAULT_UNIVERSE).upper()
        syms = universe_symbols(uni)
        if limit:
            syms = syms[: max(1, int(limit))]
        wanted = set(rules or RULES)
        min_value = float(settings.min_daily_value_egp)
        edge = _edge_lookup()
        rows: list[dict] = []
        skipped = illiquid = 0
        job.progress(phase="scanning", done=0, total=len(syms))
        for k, sym in enumerate(syms):
            job.progress(done=k, detail=sym)
            candles = leaders.daily_candles(sym)
            if len(candles) < MIN_BARS:
                skipped += 1
                continue
            for h in rule_hits_last_bar(sym, candles):
                if h["scanner"] not in wanted:
                    continue
                h["rule"] = h["scanner"]
                mv = h.get("median_value_20d")
                if mv is not None and mv < min_value:
                    illiquid += 1
                    continue
                h["edge"] = edge.get(h["scanner"])
                rows.append(h)
            time.sleep(_PAUSE_S)
        stored = _persist(rows) if persist else 0
        by_rule: dict[str, int] = {}
        for r in rows:
            by_rule[r["scanner"]] = by_rule.get(r["scanner"], 0) + 1
        order = {"edge": 0, "marginal": 1, "negative": 2, "too_few": 3}
        rows.sort(key=lambda r: (order.get(((r.get("edge") or {}).get("verdict")) or "too_few", 9),
                                 -(r.get("volume_ratio") or 0)))
        date = rows[0]["date"] if rows else None
        return {
            "rows": rows, "date": date, "universe": uni, "scanned": len(syms), "skipped_no_data": skipped,
            "filtered_illiquid": illiquid, "hits": len(rows), "by_rule": by_rule, "stored": stored,
            "edge": edge, "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso(),
            "basis": ("The app's own four entry rules evaluated on the last completed daily bar of every "
                      "stock, on Yahoo candles (no TradingView). Hits are journaled under the rule's name, so "
                      "the Scorecard weight measured on five years of replayed history applies at once. "
                      "Illiquid names (20-day median value below the floor) are dropped."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("rule_scanner.scan failed")
        return {"error": str(exc)}


def stored_hits(date: Optional[str] = None) -> list[dict]:
    """Journaled rule hits for ``date`` (default: the latest date that has any). Live only."""
    try:
        marks = ",".join("?" * len(RULES))
        if date is None:
            d = db.query(f"SELECT MAX(date) AS d FROM scanner_hits WHERE scanner IN ({marks}) "  # noqa: S608
                         "AND COALESCE(source, 'live') = 'live'", RULES)
            date = d[0].get("d") if d else None
        if not date:
            return []
        rows = db.query(f"SELECT date, scanner, symbol, payload_json FROM scanner_hits "  # noqa: S608
                        f"WHERE date = ? AND scanner IN ({marks}) AND COALESCE(source, 'live') = 'live'",
                        (date, *RULES))
        out: list[dict] = []
        for r in rows:
            try:
                payload = json.loads(r.get("payload_json") or "{}")
            except (TypeError, ValueError):
                payload = {}
            out.append({"date": r["date"], "scanner": r["scanner"], "symbol": r["symbol"], **payload})
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("rule_scanner.stored_hits failed: %s", exc)
        return []


def latest() -> dict:
    """Most recent stored scan, with the Proven-edge verdict per rule (instant)."""
    rows = stored_hits()
    edge = _edge_lookup()
    for r in rows:
        r["edge"] = edge.get(r["scanner"])
    order = {"edge": 0, "marginal": 1, "negative": 2, "too_few": 3}
    rows.sort(key=lambda r: (order.get(((r.get("edge") or {}).get("verdict")) or "too_few", 9),
                             -(r.get("volume_ratio") or 0)))
    by_rule: dict[str, int] = {}
    for r in rows:
        by_rule[r["scanner"]] = by_rule.get(r["scanner"], 0) + 1
    return {"rows": rows, "date": rows[0]["date"] if rows else None, "hits": len(rows), "by_rule": by_rule,
            "edge": edge, "stored": True, "rules": list(RULES)}


def start(universe: str = DEFAULT_UNIVERSE) -> dict:
    return job.start(scan, universe, True, None, None)


def status() -> dict:
    return job.status()
