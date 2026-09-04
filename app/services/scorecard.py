"""Signal Scorecard — grade every stored scanner hit by what the stock did next.

The Candidates screen counts how many scanners flagged a name. That is
evidence by volume, not by track record. This module turns the ``scanner_hits``
journal into a track record: for each hit it records the close on the hit
date and the return 5, 10 and 20 sessions later, against EGX30 over the same
window. Per-scanner beat rates then feed back into the Candidates ranking as
weights — but only once a scanner has MIN_SAMPLE graded hits, because a 60%
hit rate on 5 trades is noise.

Grading is incremental and rate-limit friendly: each run grades the oldest
ungraded / partially graded hits first, bounded by MAX_PER_RUN.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

HORIZONS: tuple[int, ...] = (5, 10, 20)
#: Graded hits a scanner needs before its beat rate is allowed to move weights.
MIN_SAMPLE = 20
#: Horizon whose beat rate drives the Candidates weight.
WEIGHT_HORIZON = 10
MAX_PER_RUN = 120
_WEIGHT_FLOOR, _WEIGHT_CAP = 0.5, 1.5
#: Live scanner -> replayed candle rule that stands in for it until the live
#: scanner has MIN_SAMPLE graded hits of its own. The live scanners are
#: TradingView screens that cannot be re-run on history; these rules are
#: the same trades expressed on daily candles (see rules_backtest.ENTRY_RULES).
#: Fallback "random entry beats EGX30" rate when no baseline has been measured
#: yet (edge.compute stores the real one — on EGX it is ~44%, not 50%, because
#: single-stock returns are skewed: most sessions lag the index, a few fly).
DEFAULT_BASELINE_RATE = 0.5
PROXY_FOR: dict[str, str] = {
    "squeeze": "squeeze_breakout",
    "momentum": "momentum_3",
    "volume_breakout": "range_breakout",
}
_weights_cache: tuple[float, dict[str, float]] | None = None
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _today() -> str:
    return datetime.now(CAIRO).strftime("%Y-%m-%d")


# ── grading ──────────────────────────────────────────────────────────────────


def _pending_hits(limit: int) -> list[dict]:
    """Hits with no outcome row, or whose 20-day return is still open and were
    not already re-graded today."""
    today = _today()
    return db.query(
        "SELECT h.id AS hit_id, h.date, h.scanner, h.symbol, h.source, o.ret_20, o.graded_at "
        "FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
        "WHERE h.symbol IS NOT NULL AND h.symbol != '' "
        "  AND (o.id IS NULL OR (o.ret_20 IS NULL AND substr(o.graded_at, 1, 10) < ?)) "
        "ORDER BY h.date ASC, h.id ASC LIMIT ?",
        (today, max(1, int(limit))),
    )


def grade_hit(hit: dict, candles: list[dict], bench: dict[str, Any]) -> Optional[dict]:
    """Pure: outcome row for one hit given the symbol's daily candles."""
    date = str(hit.get("date") or "")[:10]
    if not date or not candles:
        return None
    idx = next((i for i, c in enumerate(candles) if str(c.get("time")) >= date), None)
    if idx is None:
        return None
    try:
        entry_close = float(candles[idx]["close"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry_close <= 0:
        return None
    from app.services.leaders import benchmark_return

    out: dict[str, Any] = {
        "hit_id": hit["hit_id"], "date": date, "scanner": hit.get("scanner"),
        "symbol": hit.get("symbol"), "entry_date": str(candles[idx].get("time")),
        "entry_close": round(entry_close, 4), "source": hit.get("source") or "live",
    }
    for h in HORIZONS:
        j = idx + h
        if j < len(candles):
            close = float(candles[j]["close"])
            ret = close / entry_close - 1.0
            b = benchmark_return(bench, str(candles[idx]["time"]), str(candles[j]["time"]))
            out[f"ret_{h}"] = round(ret * 100.0, 3)
            out[f"bench_{h}"] = round(b * 100.0, 3) if b is not None else None
            out[f"excess_{h}"] = round((ret - b) * 100.0, 3) if b is not None else None
        else:
            out[f"ret_{h}"] = out[f"bench_{h}"] = out[f"excess_{h}"] = None
    return out


def _upsert(outcome: dict) -> None:
    db.execute(
        "INSERT OR REPLACE INTO signal_outcomes "
        "(hit_id, date, scanner, symbol, entry_date, entry_close, "
        " ret_5, bench_5, excess_5, ret_10, bench_10, excess_10, ret_20, bench_20, excess_20, graded_at, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            outcome["hit_id"], outcome["date"], outcome["scanner"], outcome["symbol"],
            outcome["entry_date"], outcome["entry_close"],
            outcome["ret_5"], outcome["bench_5"], outcome["excess_5"],
            outcome["ret_10"], outcome["bench_10"], outcome["excess_10"],
            outcome["ret_20"], outcome["bench_20"], outcome["excess_20"],
            _now_iso(), outcome.get("source") or "live",
        ),
    )


def grade(limit: int = MAX_PER_RUN) -> dict:
    """Grade pending hits. Returns counts; never raises."""
    global _weights_cache
    try:
        from app.services import leaders

        started = time.monotonic()
        pending = _pending_hits(limit)
        if not pending:
            return {"graded": 0, "pending": 0, "as_of": _now_iso()}
        bench = leaders.benchmark_series()
        graded = complete = skipped = 0
        by_symbol: dict[str, list[dict]] = {}
        for hit in pending:
            by_symbol.setdefault(str(hit["symbol"]).upper(), []).append(hit)
        for symbol, hits in by_symbol.items():
            candles = leaders.daily_candles(symbol)
            if not candles:
                skipped += len(hits)
                continue
            for hit in hits:
                outcome = grade_hit(hit, candles, bench)
                if outcome is None:
                    skipped += 1
                    continue
                _upsert(outcome)
                graded += 1
                if outcome.get("ret_20") is not None:
                    complete += 1
        with _lock:
            _weights_cache = None
        remaining = db.query(
            "SELECT COUNT(*) AS n FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
            "WHERE o.id IS NULL OR o.ret_20 IS NULL"
        )
        return {
            "graded": graded, "fully_graded_20d": complete, "skipped_no_data": skipped,
            "still_open": remaining[0]["n"] if remaining else None,
            "benchmark": bench.get("source"),
            "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("scorecard.grade failed")
        return {"error": str(exc)}


# ── aggregation ──────────────────────────────────────────────────────────────


def invalidate_weights() -> None:
    """Drop the cached Candidates weights (after grading or a replay)."""
    global _weights_cache
    with _lock:
        _weights_cache = None


def signal_direction(scanner: str) -> str:
    """'bullish' | 'bearish' | 'neutral' — bearish signals are graded on the stock FALLING."""
    name = str(scanner or "")
    if name.startswith("pattern_"):
        try:
            from app.services import pattern_catalog

            return str((pattern_catalog.info(name[len("pattern_"):]) or {}).get("direction") or "neutral")
        except Exception:  # noqa: BLE001
            return "neutral"
    return "bullish"   # scanners and entry rules are long ideas


def _payload_direction(payload_json: Any) -> Optional[str]:
    if not payload_json:
        return None
    try:
        import json as _json

        d = _json.loads(payload_json)
        val = str((d or {}).get("direction") or "").lower()
        return val if val in ("bullish", "bearish") else None
    except (TypeError, ValueError):
        return None


def baseline() -> dict[str, Any]:
    """Random-entry yardstick stored by edge.compute (kind='baseline'), or the default.

    {"beat_rate": fraction of random long entries that beat EGX30 at WEIGHT_HORIZON,
     "under_rate": fraction that lagged it, "avg_excess": mean excess %, "measured": bool}
    """
    try:
        rows = db.query("SELECT extra_json FROM proven_edge WHERE kind = 'baseline' AND name = ?",
                        (f"random_entry_{WEIGHT_HORIZON}d",))
        if rows:
            import json as _json

            extra = _json.loads(rows[0].get("extra_json") or "{}")
            beat = float(extra.get("beat_rate")) / 100.0
            return {"beat_rate": beat, "under_rate": float(extra.get("under_rate")) / 100.0,
                    "avg_excess": float(extra.get("avg_excess") or 0.0), "measured": True,
                    "sessions": extra.get("sessions"), "symbols": extra.get("symbols")}
    except Exception:  # noqa: BLE001 - table may not exist yet
        pass
    return {"beat_rate": DEFAULT_BASELINE_RATE, "under_rate": 1.0 - DEFAULT_BASELINE_RATE,
            "avg_excess": 0.0, "measured": False}


def _weight_from(right_rate: Optional[float], n: int, base_rate: float = DEFAULT_BASELINE_RATE) -> float:
    """1 + 2 x (right-way rate - random-entry rate), clamped. 50% vs a 50% baseline = 1.0;
    46% vs EGX's 44% baseline = 1.04 (slightly better than chance), 40% = 0.92."""
    if right_rate is None or n < MIN_SAMPLE:
        return 1.0
    return round(min(_WEIGHT_CAP, max(_WEIGHT_FLOOR, 1.0 + 2.0 * (right_rate - base_rate))), 2)


def scorecard() -> dict:
    """Per-scanner track record across horizons plus the resulting weights."""
    try:
        # The hit payload carries the per-instance direction for patterns the catalog
        # calls neutral (a breakout can be up or down; a marubozu bullish or bearish).
        rows = db.query("SELECT o.*, h.payload_json FROM signal_outcomes o "
                        "LEFT JOIN scanner_hits h ON h.id = o.hit_id")
        base = baseline()
        scanners: dict[str, dict[str, Any]] = {}
        directions: dict[str, str] = {}
        for r in rows:
            name = str(r["scanner"])
            if name not in directions:
                directions[name] = signal_direction(name)
            # Bearish signals are right when the stock FALLS: flip the sign so every
            # statistic below reads "in the signal's favour".
            row_dir = directions[name]
            if row_dir not in ("bullish", "bearish"):
                row_dir = _payload_direction(r.get("payload_json")) or "bullish"
            sign = -1.0 if row_dir == "bearish" else 1.0
            sc = scanners.setdefault(name, {"scanner": r["scanner"], "hits_graded": 0,
                                            "horizons": {}, "sources": {}, "direction": directions[name]})
            sc["hits_graded"] += 1
            src = str(r.get("source") or "live")
            sc["sources"][src] = sc["sources"].get(src, 0) + 1
            for h in HORIZONS:
                ret, exc = r.get(f"ret_{h}"), r.get(f"excess_{h}")
                if ret is None:
                    continue
                agg = sc["horizons"].setdefault(str(h), {"n": 0, "wins": 0, "beats": 0, "n_bench": 0,
                                                          "rets": [], "excess": []})
                agg["n"] += 1
                agg["rets"].append(sign * float(ret))
                if sign * float(ret) > 0:
                    agg["wins"] += 1
                if exc is not None:
                    agg["n_bench"] += 1
                    agg["excess"].append(sign * float(exc))
                    if sign * float(exc) > 0:
                        agg["beats"] += 1
        out_scanners: dict[str, Any] = {}
        weights: dict[str, float] = {}
        for name, sc in scanners.items():
            horizons: dict[str, Any] = {}
            bearish = sc.get("direction") == "bearish"
            base_rate = base["under_rate"] if bearish else base["beat_rate"]
            base_excess = -base["avg_excess"] if bearish else base["avg_excess"]
            for h, agg in sc["horizons"].items():
                rets = sorted(agg["rets"])
                excess = sorted(agg["excess"])
                se = None
                if len(excess) >= 2:
                    m = sum(excess) / len(excess)
                    var = sum((x - m) ** 2 for x in excess) / (len(excess) - 1)
                    se = round((var ** 0.5) / (len(excess) ** 0.5), 3)
                horizons[h] = {
                    "n": agg["n"],
                    "win_rate": round(agg["wins"] / agg["n"] * 100.0, 1) if agg["n"] else None,
                    "beat_rate": (round(agg["beats"] / agg["n_bench"] * 100.0, 1)
                                  if agg["n_bench"] else None),
                    "avg_return": round(sum(rets) / len(rets), 2) if rets else None,
                    "median_return": round(rets[len(rets) // 2], 2) if rets else None,
                    "avg_excess": round(sum(excess) / len(excess), 2) if excess else None,
                    "median_excess": round(excess[len(excess) // 2], 2) if excess else None,
                    "se_excess": se,
                    # versus a random entry over the same window (percentage points)
                    "beat_vs_random_pp": (round(agg["beats"] / agg["n_bench"] * 100.0 - base_rate * 100.0, 1)
                                          if agg["n_bench"] else None),
                    "excess_vs_random": (round(sum(excess) / len(excess) - base_excess, 2) if excess else None),
                    "sufficient": agg["n"] >= MIN_SAMPLE,
                }
            key = horizons.get(str(WEIGHT_HORIZON)) or {}
            beat = key.get("beat_rate")
            n = int(key.get("n") or 0)
            w = _weight_from(beat / 100.0 if beat is not None else None, n, base_rate)
            weights[name] = w
            out_scanners[name] = {
                "scanner": name, "hits_graded": sc["hits_graded"], "horizons": horizons,
                "sources": sc["sources"], "proxy": None, "direction": sc.get("direction"),
                "weight": w, "weight_basis": (
                    f"right-way rate {beat:.0f}% over {n} hits at {WEIGHT_HORIZON}d "
                    f"(random entry {base_rate * 100:.0f}%)"
                    + (" (replayed history)" if sc["sources"].get("replay") else "")
                    if beat is not None and n >= MIN_SAMPLE else
                    f"neutral 1.0 — {n}/{MIN_SAMPLE} graded hits at {WEIGHT_HORIZON}d"
                ),
            }
        # Proxy weights: a live scanner without enough graded hits of its own
        # inherits the measured weight of its replayed candle rule, labelled.
        for live, proxy in PROXY_FOR.items():
            own = out_scanners.get(live)
            own_n = int(((own or {}).get("horizons") or {}).get(str(WEIGHT_HORIZON), {}).get("n") or 0)
            if own_n >= MIN_SAMPLE:
                continue
            src = out_scanners.get(proxy)
            if not src:
                continue
            key = (src.get("horizons") or {}).get(str(WEIGHT_HORIZON)) or {}
            if int(key.get("n") or 0) < MIN_SAMPLE or key.get("beat_rate") is None:
                continue
            basis = (f"proxy: replayed '{proxy}' right-way rate {key['beat_rate']:.0f}% over {key['n']} "
                     f"signals at {WEIGHT_HORIZON}d — until '{live}' has {MIN_SAMPLE} live graded hits "
                     f"({own_n} so far)")
            if own is None:
                own = out_scanners[live] = {"scanner": live, "hits_graded": 0, "horizons": {},
                                            "sources": {}, "weight": 1.0, "weight_basis": ""}
            own["weight"] = src["weight"]
            own["weight_basis"] = basis
            own["proxy"] = proxy
            weights[live] = src["weight"]
        total_hits = db.query("SELECT COUNT(*) AS n FROM scanner_hits")
        pending = db.query(
            "SELECT COUNT(*) AS n FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
            "WHERE o.id IS NULL"
        )
        return {
            "scanners": out_scanners,
            "weights": weights,
            "min_sample": MIN_SAMPLE,
            "weight_horizon_days": WEIGHT_HORIZON,
            "proxy_for": PROXY_FOR,
            "baseline": {**base, "beat_rate_pct": round(base["beat_rate"] * 100.0, 1),
                         "under_rate_pct": round(base["under_rate"] * 100.0, 1)},
            "outcomes_by_source": _outcomes_by_source(rows),
            "hits_total": total_hits[0]["n"] if total_hits else 0,
            "hits_ungraded": pending[0]["n"] if pending else 0,
            "outcomes": len(rows),
            "basis": (
                "Each signal is graded by the stock's close-to-close return 5/10/20 sessions after "
                "the hit date, and by the excess over EGX30 for the same window; bearish signals are "
                "graded on the stock FALLING (two-way patterns such as breakouts use the direction "
                "recorded on each hit), so every number reads 'in the signal's favour'. Rates "
                f"are judged against a random entry ({base['beat_rate'] * 100:.0f}% of random long "
                "entries beat EGX30 over 10 sessions on this exchange — single-stock returns are "
                "skewed), not against 50%. A scanner's weight in the Candidates ranking = 1 + 2 × "
                f"(its {WEIGHT_HORIZON}-day right-way rate − the random-entry rate), clamped to "
                f"[{_WEIGHT_FLOOR}, {_WEIGHT_CAP}], and only after {MIN_SAMPLE} graded hits. "
                "Until a live scanner has that many, it borrows the weight of its replayed candle "
                "rule (proxy) where one exists; smart_money has none and stays neutral."
            ),
            "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _outcomes_by_source(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        src = str(r.get("source") or "live")
        out[src] = out.get(src, 0) + 1
    return out


def signal_weights() -> dict[str, float]:
    """Scanner -> weight for the Candidates ranking (cached 10 minutes)."""
    global _weights_cache
    now = time.monotonic()
    with _lock:
        if _weights_cache and now - _weights_cache[0] < 600:
            return dict(_weights_cache[1])
    card = scorecard()
    weights = card.get("weights") if isinstance(card, dict) and "error" not in card else {}
    weights = {k: float(v) for k, v in (weights or {}).items()}
    with _lock:
        _weights_cache = (now, weights)
    return dict(weights)


def outcomes(scanner: Optional[str] = None, symbol: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Individual graded hits, newest first."""
    try:
        sql = "SELECT * FROM signal_outcomes WHERE 1=1"
        params: list[Any] = []
        if scanner:
            sql += " AND scanner = ?"
            params.append(scanner)
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol.upper())
        sql += " ORDER BY date DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        return db.query(sql, params)
    except Exception as exc:  # noqa: BLE001
        logger.error("scorecard.outcomes failed: %s", exc)
        return []
