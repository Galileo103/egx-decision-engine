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

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.services.bgjob import BackgroundJob

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

#: Grading horizons in sessions. 5/10/20 suit candlesticks and short thrusts;
#: 40/60 exist because swing patterns (cups, triangles, range breakouts) play out
#: over one to three months and a 10-session verdict on them measures noise.
HORIZONS: tuple[int, ...] = (5, 10, 20, 40, 60)
#: The horizon whose column marks an outcome row as fully graded.
FINAL_HORIZON = HORIZONS[-1]
#: Graded hits a scanner needs before its beat rate is allowed to move weights.
MIN_SAMPLE = 20
#: Horizon whose beat rate drives the Candidates weight.
WEIGHT_HORIZON = 10
MAX_PER_RUN = 120
#: Regime states a signal can be split by (see services/regime.py).
REGIMES: tuple[str, ...] = ("bull", "neutral", "bear")
_WEIGHT_FLOOR, _WEIGHT_CAP = 0.5, 1.5
#: Relative-volume multiplier bounds (bucket beat rate / all-volume beat rate).
_RVOL_MULT_FLOOR, _RVOL_MULT_CAP = 0.7, 1.3
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
#: (monotonic time, {"all": {scanner: weight}, "by_regime": {state: {scanner: weight}}})
_weights_cache: tuple[float, dict[str, Any]] | None = None
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
    final = f"ret_{FINAL_HORIZON}"
    return db.query(
        f"SELECT h.id AS hit_id, h.date, h.scanner, h.symbol, h.source, o.{final}, o.graded_at "
        "FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
        "WHERE h.symbol IS NOT NULL AND h.symbol != '' "
        f"  AND (o.id IS NULL OR (o.{final} IS NULL AND substr(o.graded_at, 1, 10) < ?)) "
        "ORDER BY h.date ASC, h.id ASC LIMIT ?",
        (today, max(1, int(limit))),
    )


def _rvol_on(candles: list[dict], date: Any) -> Optional[float]:
    """Relative volume of the candle dated ``date`` (None when not found)."""
    if not date or not candles:
        return None
    d = str(date)[:10]
    idx = next((i for i, c in enumerate(candles) if str(c.get("time"))[:10] == d), None)
    if idx is None:
        return None
    from app.services.pattern_common import rvol

    return rvol(candles, idx)


def _regime_lookup(regimes: Any) -> Any:
    """Accept a RegimeSeries, a {date: state} dict, or None -> callable(date) -> state|None."""
    if regimes is None:
        return lambda _d: None
    if hasattr(regimes, "at"):
        return regimes.at
    if isinstance(regimes, dict):
        return lambda d: regimes.get(str(d)[:10])
    return lambda _d: None


def grade_hit(hit: dict, candles: list[dict], bench: dict[str, Any], regimes: Any = None) -> Optional[dict]:
    """Pure: outcome row for one hit given the symbol's daily candles.

    ``regimes`` (optional) stamps the market regime on the entry date so the
    edge table can split bull from bear tapes; None leaves the column NULL.
    """
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
        "regime": _regime_lookup(regimes)(str(candles[idx].get("time"))),
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


_OUTCOME_COLS = (["hit_id", "date", "scanner", "symbol", "entry_date", "entry_close"]
                 + [f"{k}_{h}" for h in HORIZONS for k in ("ret", "bench", "excess")]
                 + ["graded_at", "source", "regime"])
_UPSERT_SQL = (f"INSERT OR REPLACE INTO signal_outcomes ({', '.join(_OUTCOME_COLS)}) "
               f"VALUES ({', '.join('?' for _ in _OUTCOME_COLS)})")


def _outcome_params(outcome: dict) -> tuple:
    now = _now_iso()
    vals = []
    for col in _OUTCOME_COLS:
        if col == "graded_at":
            vals.append(now)
        elif col == "source":
            vals.append(outcome.get("source") or "live")
        else:
            vals.append(outcome.get(col))
    return tuple(vals)


def _upsert(outcome: dict) -> None:
    db.execute(_UPSERT_SQL, _outcome_params(outcome))


def _upsert_many(outcomes: list[dict]) -> None:
    if outcomes:
        db.executemany(_UPSERT_SQL, [_outcome_params(o) for o in outcomes])


def grade(limit: int = MAX_PER_RUN) -> dict:
    """Grade pending hits. Returns counts; never raises."""
    global _weights_cache
    try:
        from app.services import leaders, regime

        started = time.monotonic()
        pending = _pending_hits(limit)
        if not pending:
            return {"graded": 0, "pending": 0, "as_of": _now_iso()}
        bench = leaders.benchmark_series()
        regimes = regime.series()
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
                outcome = grade_hit(hit, candles, bench, regimes)
                if outcome is None:
                    skipped += 1
                    continue
                _upsert(outcome)
                graded += 1
                if outcome.get(f"ret_{FINAL_HORIZON}") is not None:
                    complete += 1
        with _lock:
            _weights_cache = None
        remaining = db.query(
            "SELECT COUNT(*) AS n FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
            f"WHERE o.id IS NULL OR o.ret_{FINAL_HORIZON} IS NULL"
        )
        return {
            "graded": graded, f"fully_graded_{FINAL_HORIZON}d": complete, "skipped_no_data": skipped,
            "still_open": remaining[0]["n"] if remaining else None,
            "benchmark": bench.get("source"),
            "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("scorecard.grade failed")
        return {"error": str(exc)}


# ── re-grade (background) ────────────────────────────────────────────────────

regrade_job = BackgroundJob("regrade")


def regrade(source: Optional[str] = None, only_incomplete: bool = True, range_: str = "5y") -> dict:
    """Re-grade stored outcomes from multi-year candles — fills the 40/60-session
    columns and the regime stamp on rows graded before those existed, without
    re-running signal detection. Slow (one Yahoo fetch per symbol); run via
    ``regrade_job``. Never raises.

    ``only_incomplete`` limits the pass to rows missing the final horizon or the
    regime; False re-grades everything (after a benchmark change, say).
    """
    global _weights_cache
    try:
        from app.services import leaders, regime

        started = time.monotonic()
        regrade_job.progress(phase="regime", done=0, total=0, detail="EGX30 history + breadth")
        reg = regime.backfill(range_, progress=regrade_job.progress)
        regimes = regime.series(force=True)
        where = ["h.symbol IS NOT NULL AND h.symbol != ''"]
        params: list[Any] = []
        if source:
            where.append("h.source = ?")
            params.append(source)
        if only_incomplete:
            # ...or hits journaled before relative volume was stamped on payloads (Task 4).
            where.append(f"(o.id IS NULL OR o.ret_{FINAL_HORIZON} IS NULL OR o.regime IS NULL "
                         "OR json_extract(h.payload_json, '$.rvol') IS NULL)")
        rows = db.query(
            "SELECT h.id AS hit_id, h.date, h.scanner, h.symbol, h.source, h.payload_json "
            "FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
            f"WHERE {' AND '.join(where)} ORDER BY h.symbol, h.date", params,
        )
        by_symbol: dict[str, list[dict]] = {}
        for hit in rows:
            by_symbol.setdefault(str(hit["symbol"]).upper(), []).append(hit)
        bench = leaders.benchmark_series(range_=range_)
        if not bench.get("dates"):
            bench = leaders.benchmark_series()
        graded = complete = skipped = with_regime = with_rvol = 0
        regrade_job.progress(phase="regrading", done=0, total=len(by_symbol))
        for k, (symbol, hits) in enumerate(by_symbol.items()):
            regrade_job.progress(done=k, detail=f"{symbol} ({len(hits)} signals)")
            candles = leaders.daily_candles(symbol, range_)
            if not candles:
                skipped += len(hits)
                continue
            batch: list[dict] = []
            rvol_updates: list[tuple] = []
            for hit in hits:
                outcome = grade_hit(hit, candles, bench, regimes)
                if outcome is None:
                    skipped += 1
                    continue
                batch.append(outcome)
                if outcome.get(f"ret_{FINAL_HORIZON}") is not None:
                    complete += 1
                if outcome.get("regime"):
                    with_regime += 1
                # Stamp relative volume on payloads journaled before Task 4 so the
                # volume split covers the whole replay, not just new hits.
                if _payload_rvol(hit.get("payload_json")) is None:
                    rv = _rvol_on(candles, outcome.get("entry_date"))
                    if rv is not None:
                        try:
                            payload = json.loads(hit.get("payload_json") or "{}") or {}
                        except (TypeError, ValueError):
                            payload = {}
                        payload["rvol"] = rv
                        rvol_updates.append((json.dumps(payload, default=str), hit["hit_id"]))
                        with_rvol += 1
            _upsert_many(batch)
            if rvol_updates:
                db.executemany("UPDATE scanner_hits SET payload_json = ? WHERE id = ?", rvol_updates)
            graded += len(batch)
        with _lock:
            _weights_cache = None
        return {
            "symbols": len(by_symbol), "regraded": graded, f"fully_graded_{FINAL_HORIZON}d": complete,
            "with_regime": with_regime, "rvol_stamped": with_rvol, "skipped_no_data": skipped,
            "regime": {k: reg.get(k) for k in ("rows", "counts", "latest", "error") if k in reg},
            "benchmark": bench.get("source"), "range": range_,
            "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("scorecard.regrade failed")
        return {"error": str(exc)}


def start_regrade(source: Optional[str] = None, only_incomplete: bool = True) -> dict:
    return regrade_job.start(regrade, source, only_incomplete)


def regrade_status() -> dict:
    return regrade_job.status()


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


def _payload_rvol(payload_json: Any) -> Optional[float]:
    """Relative volume stamped on the hit (Task 4); None for older rows."""
    if not payload_json:
        return None
    try:
        import json as _json

        v = (_json.loads(payload_json) or {}).get("rvol")
        return float(v) if isinstance(v, (int, float)) else None
    except (TypeError, ValueError):
        return None


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


def _default_baseline() -> dict[str, Any]:
    return {"beat_rate": DEFAULT_BASELINE_RATE, "under_rate": 1.0 - DEFAULT_BASELINE_RATE,
            "avg_excess": 0.0, "measured": False, "by_regime": {}}


def baseline(horizon: int = WEIGHT_HORIZON) -> dict[str, Any]:
    """Random-entry yardstick stored by edge.compute (kind='baseline'), or the default.

    {"beat_rate": fraction of random long entries that beat EGX30 at ``horizon``,
     "under_rate": fraction that lagged it, "avg_excess": mean excess %, "measured": bool,
     "by_regime": {state: {"beat_rate", "under_rate", "avg_excess", "sessions"}} (fractions)}
    """
    try:
        rows = db.query("SELECT extra_json FROM proven_edge WHERE kind = 'baseline' AND name = ?",
                        (f"random_entry_{int(horizon)}d",))
        if rows:
            import json as _json

            extra = _json.loads(rows[0].get("extra_json") or "{}")
            beat = float(extra.get("beat_rate")) / 100.0
            by_regime: dict[str, dict[str, Any]] = {}
            for state, b in (extra.get("by_regime") or {}).items():
                try:
                    by_regime[state] = {"beat_rate": float(b["beat_rate"]) / 100.0,
                                        "under_rate": float(b["under_rate"]) / 100.0,
                                        "avg_excess": float(b.get("avg_excess") or 0.0),
                                        "sessions": b.get("sessions")}
                except (KeyError, TypeError, ValueError):
                    continue
            return {"beat_rate": beat, "under_rate": float(extra.get("under_rate")) / 100.0,
                    "avg_excess": float(extra.get("avg_excess") or 0.0), "measured": True,
                    "sessions": extra.get("sessions"), "symbols": extra.get("symbols"),
                    "horizon": int(horizon), "by_regime": by_regime}
    except Exception:  # noqa: BLE001 - table may not exist yet
        pass
    return _default_baseline()


def baselines() -> dict[int, dict[str, Any]]:
    """Baseline per grading horizon (unmeasured horizons fall back to the default)."""
    return {h: baseline(h) for h in HORIZONS}


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
        bases = baselines()
        base = bases[WEIGHT_HORIZON]
        scanners: dict[str, dict[str, Any]] = {}
        directions: dict[str, str] = {}

        def _new_agg() -> dict[str, Any]:
            return {"n": 0, "wins": 0, "beats": 0, "n_bench": 0, "rets": [], "excess": []}

        def _feed(agg: dict[str, Any], sign: float, ret: float, exc: Optional[float]) -> None:
            agg["n"] += 1
            agg["rets"].append(sign * ret)
            if sign * ret > 0:
                agg["wins"] += 1
            if exc is not None:
                agg["n_bench"] += 1
                agg["excess"].append(sign * exc)
                if sign * exc > 0:
                    agg["beats"] += 1

        from app.services.pattern_common import RVOL_BUCKETS, rvol_bucket

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
                                            "horizons": {}, "regimes": {}, "rvol": {}, "sources": {},
                                            "direction": directions[name]})
            sc["hits_graded"] += 1
            src = str(r.get("source") or "live")
            sc["sources"][src] = sc["sources"].get(src, 0) + 1
            reg = r.get("regime") if r.get("regime") in REGIMES else None
            # Relative volume on the signal day, stamped in the hit payload (Task 4).
            bucket = rvol_bucket(_payload_rvol(r.get("payload_json")))
            for h in HORIZONS:
                ret, exc = r.get(f"ret_{h}"), r.get(f"excess_{h}")
                if ret is None:
                    continue
                _feed(sc["horizons"].setdefault(str(h), _new_agg()), sign, float(ret),
                      float(exc) if exc is not None else None)
                if reg:
                    _feed(sc["regimes"].setdefault(reg, {}).setdefault(str(h), _new_agg()), sign, float(ret),
                          float(exc) if exc is not None else None)
                if bucket:
                    _feed(sc["rvol"].setdefault(bucket, {}).setdefault(str(h), _new_agg()), sign, float(ret),
                          float(exc) if exc is not None else None)

        def _stats(agg: dict[str, Any], base_rate: float, base_excess: float) -> dict[str, Any]:
            rets = sorted(agg["rets"])
            excess = sorted(agg["excess"])
            se = None
            if len(excess) >= 2:
                m = sum(excess) / len(excess)
                var = sum((x - m) ** 2 for x in excess) / (len(excess) - 1)
                se = round((var ** 0.5) / (len(excess) ** 0.5), 3)
            return {
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

        def _base_for(b: dict[str, Any], bearish: bool) -> tuple[float, float]:
            rate = b["under_rate"] if bearish else b["beat_rate"]
            exc = -b["avg_excess"] if bearish else b["avg_excess"]
            return rate, exc

        out_scanners: dict[str, Any] = {}
        weights: dict[str, float] = {}
        regime_weights: dict[str, dict[str, float]] = {s: {} for s in REGIMES}
        # Volume multipliers: how much better/worse a scanner does when its signal
        # day traded heavy vs quiet, relative to its all-volume record. Measured,
        # not assumed — a rule whose heavy-volume hits do no better keeps 1.0.
        rvol_multipliers: dict[str, dict[str, float]] = {b: {} for b in RVOL_BUCKETS}
        for name, sc in scanners.items():
            horizons: dict[str, Any] = {}
            bearish = sc.get("direction") == "bearish"
            base_rate = _base_for(base, bearish)[0]
            for h, agg in sc["horizons"].items():
                hb_rate, hb_excess = _base_for(bases.get(int(h), base), bearish)
                horizons[h] = _stats(agg, hb_rate, hb_excess)
            # Same statistics split by the regime the signal fired in. The yardstick
            # is the random entry IN THAT REGIME (a bull tape lifts everything, so a
            # signal must beat the bull-tape random entry to count as edge there).
            by_regime: dict[str, Any] = {}
            for reg, hs in sc["regimes"].items():
                by_regime[reg] = {}
                for h, agg in hs.items():
                    rb = (bases.get(int(h), base).get("by_regime") or {}).get(reg) or bases.get(int(h), base)
                    rb_rate, rb_excess = _base_for(rb, bearish)
                    by_regime[reg][h] = _stats(agg, rb_rate, rb_excess)
                    by_regime[reg][h]["baseline_measured"] = bool(
                        (bases.get(int(h), base).get("by_regime") or {}).get(reg))
                key_r = by_regime[reg].get(str(WEIGHT_HORIZON)) or {}
                if int(key_r.get("n") or 0) >= MIN_SAMPLE and key_r.get("beat_rate") is not None:
                    rb = (base.get("by_regime") or {}).get(reg) or base
                    regime_weights[reg][name] = _weight_from(key_r["beat_rate"] / 100.0, int(key_r["n"]),
                                                             _base_for(rb, bearish)[0])
            key = horizons.get(str(WEIGHT_HORIZON)) or {}
            beat = key.get("beat_rate")
            n = int(key.get("n") or 0)
            w = _weight_from(beat / 100.0 if beat is not None else None, n, base_rate)
            weights[name] = w
            # Same statistics split by the relative volume of the signal day.
            by_rvol: dict[str, Any] = {}
            for bucket, hs in sc["rvol"].items():
                by_rvol[bucket] = {}
                for h, agg in hs.items():
                    hb_rate, hb_excess = _base_for(bases.get(int(h), base), bearish)
                    by_rvol[bucket][h] = _stats(agg, hb_rate, hb_excess)
                key_b = by_rvol[bucket].get(str(WEIGHT_HORIZON)) or {}
                if (int(key_b.get("n") or 0) >= MIN_SAMPLE and key_b.get("beat_rate") is not None
                        and beat is not None and n >= MIN_SAMPLE and beat > 0):
                    rvol_multipliers[bucket][name] = round(
                        min(_RVOL_MULT_CAP, max(_RVOL_MULT_FLOOR, key_b["beat_rate"] / beat)), 2)
            out_scanners[name] = {
                "scanner": name, "hits_graded": sc["hits_graded"], "horizons": horizons,
                "by_regime": by_regime, "by_rvol": by_rvol,
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
            for reg in REGIMES:
                if live not in regime_weights[reg] and proxy in regime_weights[reg]:
                    regime_weights[reg][live] = regime_weights[reg][proxy]
            for b in RVOL_BUCKETS:
                if live not in rvol_multipliers[b] and proxy in rvol_multipliers[b]:
                    rvol_multipliers[b][live] = rvol_multipliers[b][proxy]
        total_hits = db.query("SELECT COUNT(*) AS n FROM scanner_hits")
        pending = db.query(
            "SELECT COUNT(*) AS n FROM scanner_hits h LEFT JOIN signal_outcomes o ON o.hit_id = h.id "
            "WHERE o.id IS NULL"
        )
        with_regime = sum(1 for r in rows if r.get("regime") in REGIMES)
        try:
            from app.services import regime as _regime

            regime_now = _regime.current_state()
        except Exception:  # noqa: BLE001
            regime_now = None
        return {
            "scanners": out_scanners,
            "weights": weights,
            "regime_weights": regime_weights,
            "rvol_multipliers": rvol_multipliers,
            "outcomes_with_rvol": sum(1 for r in rows if _payload_rvol(r.get("payload_json")) is not None),
            "regime": regime_now,
            "horizons": list(HORIZONS),
            "min_sample": MIN_SAMPLE,
            "weight_horizon_days": WEIGHT_HORIZON,
            "proxy_for": PROXY_FOR,
            "baseline": {**base, "beat_rate_pct": round(base["beat_rate"] * 100.0, 1),
                         "under_rate_pct": round(base["under_rate"] * 100.0, 1)},
            "baselines": {str(h): {"beat_rate_pct": round(b["beat_rate"] * 100.0, 1),
                                   "avg_excess": b["avg_excess"], "measured": b["measured"]}
                          for h, b in bases.items()},
            "outcomes_by_source": _outcomes_by_source(rows),
            "outcomes_with_regime": with_regime,
            "hits_total": total_hits[0]["n"] if total_hits else 0,
            "hits_ungraded": pending[0]["n"] if pending else 0,
            "outcomes": len(rows),
            "basis": (
                "Each signal is graded by the stock's close-to-close return 5/10/20/40/60 sessions after "
                "the hit date, and by the excess over EGX30 for the same window; bearish signals are "
                "graded on the stock FALLING (two-way patterns such as breakouts use the direction "
                "recorded on each hit), so every number reads 'in the signal's favour'. Rates "
                f"are judged against a random entry ({base['beat_rate'] * 100:.0f}% of random long "
                "entries beat EGX30 over 10 sessions on this exchange — single-stock returns are "
                "skewed), not against 50%, and each horizon has its own random-entry yardstick. "
                "A scanner's weight in the Candidates ranking = 1 + 2 × "
                f"(its {WEIGHT_HORIZON}-day right-way rate − the random-entry rate), clamped to "
                f"[{_WEIGHT_FLOOR}, {_WEIGHT_CAP}], and only after {MIN_SAMPLE} graded hits. "
                "Until a live scanner has that many, it borrows the weight of its replayed candle "
                "rule (proxy) where one exists; smart_money has none and stays neutral. Every graded "
                "signal also carries the market regime (bull / neutral / bear) it fired in; when a "
                f"scanner has {MIN_SAMPLE}+ graded hits in today's regime, Candidates uses that "
                "regime-conditional weight, judged against the random entry in the same regime."
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


def signal_weights(regime: Optional[str] = None, rvol_bucket: Optional[str] = None) -> dict[str, float]:
    """Scanner -> weight for the Candidates ranking (cached 10 minutes).

    With ``regime`` ('bull' | 'neutral' | 'bear'), a scanner that has MIN_SAMPLE
    graded hits in that regime uses its regime-conditional weight; the others
    keep the all-weather one. With ``rvol_bucket`` ('lt1' | '1_1.5' | 'ge1.5'),
    each weight is multiplied by the scanner's measured volume multiplier for
    that bucket (1.0 when unmeasured) — so a breakout on heavy volume only
    outranks a quiet one where history says the volume mattered.
    """
    global _weights_cache
    now = time.monotonic()
    with _lock:
        cached = _weights_cache if _weights_cache and now - _weights_cache[0] < 600 else None
    if cached is None:
        card = scorecard()
        ok = isinstance(card, dict) and "error" not in card
        weights = {k: float(v) for k, v in ((card.get("weights") if ok else {}) or {}).items()}
        by_regime = {reg: {k: float(v) for k, v in (ws or {}).items()}
                     for reg, ws in ((card.get("regime_weights") if ok else {}) or {}).items()}
        by_rvol = {b: {k: float(v) for k, v in (ms or {}).items()}
                   for b, ms in ((card.get("rvol_multipliers") if ok else {}) or {}).items()}
        with _lock:
            _weights_cache = (now, {"all": weights, "by_regime": by_regime, "by_rvol": by_rvol})
        cached = _weights_cache
    payload = cached[1]
    out = dict(payload.get("all") or {})
    if regime and regime in (payload.get("by_regime") or {}):
        out.update(payload["by_regime"][regime])
    if rvol_bucket and rvol_bucket in (payload.get("by_rvol") or {}):
        for k, m in payload["by_rvol"][rvol_bucket].items():
            if k in out:
                out[k] = round(out[k] * m, 3)
    return out


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
