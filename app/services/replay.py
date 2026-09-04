"""Historical replay — seed the Scorecard from years of history instead of waiting weeks.

The live Scorecard grades scanner hits as they happen; three days in, nothing
is graded and every scanner still carries a neutral weight. This module
re-runs the app's OWN candle-based rules (the entry signals of the rules
backtester) and the chart-pattern detector over every past session of a
universe, journals each historical signal into ``scanner_hits`` with
``source='replay'``, and grades it at once with ``scorecard.grade_hit`` —
close-to-close return 5/10/20 sessions later, against EGX30. Weights in the
Candidates ranking then rest on hundreds of measured outcomes.

Honesty rules:

* replayed rows are marked ``source='replay'`` and never appear in
  Candidates, Setups or the "latest scan" views — they are track record only;
* the live scanners are TradingView screens that cannot be re-run on history.
  A live scanner with too few live graded hits borrows the weight of its
  replayed PROXY rule (``scorecard.PROXY_FOR``: squeeze -> squeeze_breakout,
  momentum -> momentum_3, volume_breakout -> range_breakout), and the
  Scorecard says so. ``smart_money`` has no candle-based proxy and stays 1.0;
* signals inside the last 20 sessions are journaled but only partly graded,
  exactly like live hits — the post-close grading job finishes them;
* patterns are journaled on their BREAK date (the session the neckline was
  closed through), which is when the app would have shown "confirmed".

Runs in a background thread (``start``); ``status`` reports progress.
Detection is pure CPU on cached Yahoo candles (~0.01 s per pattern window),
so EGX100 over five years takes roughly 15-25 minutes, patterns included.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.services.bgjob import BackgroundJob
from app.symbols import universe as universe_symbols

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

#: Bars before the first evaluated signal — SMA50 + the 120-bar BBW rank need it.
WARMUP = 150
#: Candles handed to the pattern detector per window (it looks back <= 60
#: sessions for pivots; the extra is for ATR/averages and the trap-reclaim rule).
PATTERN_WINDOW = 320
_RANGE_FOR = {"1y": "1y", "2y": "2y", "3y": "5y", "5y": "5y"}

job = BackgroundJob("replay")


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


# ── signal discovery (pure) ──────────────────────────────────────────────────


def rule_hits(symbol: str, candles: list[dict]) -> list[dict]:
    """Every session on which one of the app's entry rules fired."""
    from app.services import rules_backtest as RB

    if len(candles) <= WARMUP:
        return []
    x = RB.Ind(candles)
    params = dict(RB.DEFAULTS)
    out: list[dict] = []
    for i in range(WARMUP, x.n):
        for rule, fn in RB._SIGNALS.items():
            try:
                fired = fn(x, i, params)
            except Exception:  # noqa: BLE001 - one bad bar must not kill the replay
                fired = False
            if fired:
                out.append({
                    "date": x.t[i], "scanner": rule, "symbol": symbol,
                    "payload": {"replay": True, "rule": rule, "close": round(x.c[i], 4)},
                })
    return out


def pattern_hits(symbol: str, candles: list[dict]) -> list[dict]:
    """Confirmed, directional, decent-quality patterns on the session they broke."""
    from app.services import patterns as PAT

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for i in range(60, len(candles)):
        window = candles[max(0, i - PATTERN_WINDOW + 1): i + 1]
        last = str(window[-1].get("time"))
        try:
            res = PAT.detect(symbol, window)
        except Exception:  # noqa: BLE001
            continue
        for row in (res.get("patterns") or []) if isinstance(res, dict) else []:
            if row.get("status") != "confirmed" or row.get("direction") not in ("bullish", "bearish"):
                continue
            if row.get("timeframe") == "1W":
                continue
            if (row.get("quality") or 0) < PAT.JOURNAL_MIN_QUALITY:
                continue
            if str(row.get("break_date")) != last:
                continue
            key = (last, str(row.get("pattern")))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "date": last, "scanner": f"pattern_{row['pattern']}", "symbol": symbol,
                "payload": {"replay": True, **{k: row.get(k) for k in
                                               ("neckline", "target", "quality", "break_date", "direction")}},
            })
    return out


# ── journaling + grading ─────────────────────────────────────────────────────


def _journal(hits: list[dict]) -> int:
    if not hits:
        return 0
    now = _now_iso()
    return db.executemany(
        "INSERT OR IGNORE INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
        "VALUES (?, ?, ?, ?, ?, 'replay')",
        [(h["date"], h["scanner"], h["symbol"], json.dumps(h["payload"]), now) for h in hits],
    )


def _grade_symbol(symbol: str, candles: list[dict], bench: dict) -> tuple[int, int]:
    """Grade every replayed hit of ``symbol`` that is not fully graded yet."""
    from app.services import scorecard

    rows = db.query(
        "SELECT h.id AS hit_id, h.date, h.scanner, h.symbol, h.source "
        "FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
        "WHERE h.symbol = ? AND h.source = 'replay' AND (o.id IS NULL OR o.ret_20 IS NULL)",
        (symbol,),
    )
    graded = complete = 0
    for hit in rows:
        out = scorecard.grade_hit(hit, candles, bench)
        if out is None:
            continue
        scorecard._upsert(out)
        graded += 1
        if out.get("ret_20") is not None:
            complete += 1
    return graded, complete


def run(universe: str = "EGX100", period: str = "5y", patterns: bool = True,
        limit: Optional[int] = None) -> dict:
    """Synchronous replay. Returns counts; never raises."""
    try:
        from app.services import leaders, rules_backtest as RB, scorecard

        started = time.monotonic()
        uni = (universe or "EGX100").upper()
        syms = universe_symbols(uni)
        if limit:
            syms = syms[: max(1, int(limit))]
        if not syms:
            return {"error": f"Unknown or empty universe: {uni}"}
        rng = _RANGE_FOR.get(period, "5y")
        bars = RB.PERIOD_BARS.get(period, 1250)
        bench = leaders.benchmark_series(range_="5y")
        if not bench.get("dates"):
            bench = leaders.benchmark_series()
        totals: dict[str, Any] = {
            "universe": uni, "period": period, "patterns": bool(patterns), "symbols": len(syms),
            "skipped_no_data": 0, "signals_found": 0, "new_hits": 0, "graded": 0,
            "fully_graded_20d": 0, "by_scanner": {}, "benchmark": bench.get("source"),
        }
        job.progress(phase="replaying", done=0, total=len(syms))
        for k, sym in enumerate(syms):
            job.progress(done=k, detail=sym)
            candles = leaders.daily_candles(sym, rng)
            if len(candles) < WARMUP + 30:
                totals["skipped_no_data"] += 1
                continue
            candles = candles[-(bars + 60):]
            hits = rule_hits(sym, candles)
            if patterns:
                hits += pattern_hits(sym, candles)
            for h in hits:
                totals["by_scanner"][h["scanner"]] = totals["by_scanner"].get(h["scanner"], 0) + 1
            totals["signals_found"] += len(hits)
            totals["new_hits"] += _journal(hits)
            g, c = _grade_symbol(sym, candles, bench)
            totals["graded"] += g
            totals["fully_graded_20d"] += c
            time.sleep(0.01)
        job.progress(phase="weights", done=len(syms), detail=None)
        scorecard.invalidate_weights()
        card = scorecard.scorecard()
        totals["weights"] = card.get("weights") if isinstance(card, dict) else None
        totals["elapsed_s"] = round(time.monotonic() - started, 1)
        totals["as_of"] = _now_iso()
        totals["basis"] = (
            "Each past session was scanned with the app's own entry rules (and the pattern detector "
            "on its break day); every signal was graded by the 5/10/20-session close-to-close return "
            "versus EGX30. Replayed rows carry source='replay', stay out of Candidates, and only set "
            "weights through the proxy map in the Scorecard."
        )
        return totals
    except Exception as exc:  # noqa: BLE001
        logger.exception("replay.run failed")
        return {"error": str(exc)}


def start(universe: str = "EGX100", period: str = "5y", patterns: bool = True,
          limit: Optional[int] = None) -> dict:
    return job.start(run, universe, period, patterns, limit)


def status() -> dict:
    st = job.status()
    st["stored"] = summary()
    return st


def summary() -> dict:
    """What the replay has left in the database so far."""
    try:
        rows = db.query(
            "SELECT scanner, COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last "
            "FROM scanner_hits WHERE source = 'replay' GROUP BY scanner ORDER BY n DESC"
        )
        graded = db.query(
            "SELECT COUNT(*) AS n FROM signal_outcomes WHERE source = 'replay' AND ret_20 IS NOT NULL"
        )
        return {"replayed_hits": sum(int(r["n"]) for r in rows), "by_scanner": rows,
                "fully_graded_20d": graded[0]["n"] if graded else 0}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def clear() -> dict:
    """Remove every replayed hit and its outcomes (live data untouched)."""
    try:
        outcomes = db.execute_rowcount("DELETE FROM signal_outcomes WHERE source = 'replay'")
        hits = db.execute_rowcount("DELETE FROM scanner_hits WHERE source = 'replay'")
        from app.services import scorecard
        scorecard.invalidate_weights()
        return {"removed_hits": hits, "removed_outcomes": outcomes}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
