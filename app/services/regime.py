"""Market regime — is the tape with you or against you?

Every buy decision in the app looked at one stock at a time. On EGX the index
regime decides much of a single stock's next month: a random long entry beats
EGX30 only ~44% of the time over 10 sessions, with a positive mean and a
negative median — a few names fly while most lag, and they fly in bull tapes.
This module names the tape so the other cards can consume it:

    bull     EGX30 above its 50-day average, the average rising over the last
             SLOPE_BARS sessions, and (when breadth is known) at least
             BULL_BREADTH % of EGX100 stocks above their own 50-day average
    bear     EGX30 below a falling 50-day average, or fewer than BEAR_BREADTH %
             of stocks above their 50-day while the index is not in an uptrend
    neutral  everything else (a rally on few names, a dip inside an uptrend)

One row per session is persisted to ``regime_daily`` so the Scorecard can
stamp every graded signal with the regime it fired in and the Proven-edge table
can say "this rule works in bull tapes and not in bear ones". ``update_today``
runs in the post-close job after the rule scanner (whose universe sweep leaves
every stock's candles cached, so breadth is nearly free); ``backfill`` runs
inside the re-grade job over five years.

Never raises; functions return {"error": ...} on failure.
"""
from __future__ import annotations

import bisect
import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.services.pattern_common import sma as _sma

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

STATES: tuple[str, ...] = ("bull", "neutral", "bear")
#: Breadth (% of stocks above their SMA50) needed to call an index uptrend "bull".
BULL_BREADTH = 50.0
#: Below this breadth the market is "bear" unless the index itself is in an uptrend.
BEAR_BREADTH = 35.0
#: Sessions over which the 50-day average must rise/fall to count as sloped.
SLOPE_BARS = 10
#: Universe whose members' SMA50 positions form the breadth figure.
BREADTH_UNIVERSE = "EGX100"
#: Fewer members than this with a usable SMA50 on a date -> breadth unknown that day.
MIN_BREADTH_MEMBERS = 20

_series_cache: tuple[float, "RegimeSeries"] | None = None
_lock = threading.Lock()
_SERIES_TTL = 600.0


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


# ── classification (pure) ────────────────────────────────────────────────────


def classify(close: Optional[float], sma50: Optional[float], sma50_prev: Optional[float],
             breadth_pct: Optional[float]) -> Optional[str]:
    """One of STATES, or None when the index average is not available yet.

    ``breadth_pct`` may be None (unknown): then the index alone decides, and an
    uptrend is 'bull' rather than 'neutral' — a missing breadth figure must not
    read as a weak one.
    """
    if close is None or sma50 is None:
        return None
    slope_up = sma50_prev is not None and sma50 > sma50_prev
    slope_down = sma50_prev is not None and sma50 < sma50_prev
    trend_up = close > sma50 and slope_up
    trend_down = close < sma50 and slope_down
    if trend_down:
        return "bear"
    if breadth_pct is not None and breadth_pct < BEAR_BREADTH and not trend_up:
        return "bear"
    if trend_up and (breadth_pct is None or breadth_pct >= BULL_BREADTH):
        return "bull"
    return "neutral"


def sentence(row: dict) -> str:
    """Plain-language reading of one regime row for the topbar chip and checklist."""
    state = row.get("state")
    close, s50, s200, br = row.get("index_close"), row.get("sma50"), row.get("sma200"), row.get("breadth_pct")
    where = ""
    if close is not None and s50 is not None:
        where = f"EGX30 {close:,.0f} is {'above' if close > s50 else 'below'} its 50-day average ({s50:,.0f})"
        if s200 is not None:
            where += f" and {'above' if close > s200 else 'below'} the 200-day ({s200:,.0f})"
    breadth = f"{br:.0f}% of EGX100 stocks are above their own 50-day average" if br is not None else \
        "breadth is not measured yet"
    if state == "bull":
        return f"Bull tape: {where}; {breadth} — the market is carrying most stocks."
    if state == "bear":
        return (f"Bear tape: {where}; {breadth} — most breakouts fail here, and a stock's own chart "
                "matters less than the index. New buys need a stronger reason and a smaller size.")
    if state == "neutral":
        return f"Mixed tape: {where}; {breadth} — no help from the index either way; pick by the stock's own evidence."
    return "Market regime unknown — not enough index history."


# ── series lookup ────────────────────────────────────────────────────────────


class RegimeSeries:
    """Sorted (date, state) pairs with 'state on or before this date' lookup."""

    def __init__(self, rows: list[dict]):
        rows = sorted((r for r in rows if r.get("date") and r.get("state")), key=lambda r: str(r["date"]))
        self.dates: list[str] = [str(r["date"])[:10] for r in rows]
        self.states: list[str] = [str(r["state"]) for r in rows]
        self.rows = rows

    def at(self, date: Optional[str], max_gap_days: int = 10) -> Optional[str]:
        """Regime on ``date`` (the latest row at or before it, within ``max_gap_days``)."""
        if not date or not self.dates:
            return None
        d = str(date)[:10]
        i = bisect.bisect_right(self.dates, d)
        if i == 0:
            return None
        try:
            gap = (datetime.fromisoformat(d) - datetime.fromisoformat(self.dates[i - 1])).days
        except ValueError:
            return None
        return self.states[i - 1] if gap <= max_gap_days else None

    def __len__(self) -> int:
        return len(self.dates)


def series(force: bool = False) -> RegimeSeries:
    """Every persisted regime row (cached 10 minutes). Empty series when none."""
    global _series_cache
    now = time.monotonic()
    with _lock:
        if not force and _series_cache and now - _series_cache[0] < _SERIES_TTL:
            return _series_cache[1]
    try:
        rows = db.query("SELECT date, state, index_close, sma50, sma200, breadth_pct FROM regime_daily ORDER BY date")
    except Exception as exc:  # noqa: BLE001
        logger.warning("regime.series failed: %s", exc)
        rows = []
    rs = RegimeSeries(rows)
    with _lock:
        _series_cache = (now, rs)
    return rs


def invalidate() -> None:
    global _series_cache
    with _lock:
        _series_cache = None


def state_at(date: Optional[str]) -> Optional[str]:
    """Regime on a past date, or None when unknown."""
    return series().at(date)


# ── compute ──────────────────────────────────────────────────────────────────


def _breadth_by_date(symbols: list[str], range_: str, progress: Any = None) -> dict[str, tuple[int, int]]:
    """date -> (members above SMA50, members with an SMA50) across ``symbols``."""
    from app.services import leaders

    out: dict[str, list[int]] = {}
    for k, sym in enumerate(symbols):
        if progress is not None:
            progress(done=k, detail=sym)
        candles = leaders.daily_candles(sym, range_)
        if len(candles) < 60:
            continue
        closes = [float(c["close"]) for c in candles]
        for i in range(49, len(closes)):
            s = _sma(closes, 50, i)
            if s is None:
                continue
            cell = out.setdefault(str(candles[i]["time"])[:10], [0, 0])
            cell[1] += 1
            if closes[i] > s:
                cell[0] += 1
    return {d: (v[0], v[1]) for d, v in out.items()}


def compute(range_: str = "1y", universe: str = BREADTH_UNIVERSE, persist: bool = True,
            symbols: Optional[list[str]] = None, progress: Any = None) -> dict:
    """Build (and persist) the regime row for every session in ``range_``.

    Uses the EGX30 benchmark series for the index leg and the universe members'
    daily candles for breadth. Never raises.
    """
    try:
        from app.services import leaders
        from app.symbols import universe as universe_symbols

        started = time.monotonic()
        bench = leaders.benchmark_series(range_=range_)
        dates: list[str] = list(bench.get("dates") or [])
        levels: dict[str, float] = bench.get("series") or {}
        if len(dates) < 60:
            return {"error": f"index history too short ({len(dates)} bars) — regime not computed",
                    "benchmark": bench.get("source")}
        closes = [float(levels[d]) for d in dates]
        syms = symbols if symbols is not None else universe_symbols(universe)
        breadth = _breadth_by_date(syms, range_, progress) if syms else {}
        rows: list[dict] = []
        counts = {s: 0 for s in STATES}
        for i, d in enumerate(dates):
            s50 = _sma(closes, 50, i)
            if s50 is None:
                continue
            s50_prev = _sma(closes, 50, i - SLOPE_BARS) if i >= SLOPE_BARS + 49 else None
            s200 = _sma(closes, 200, i) if i >= 199 else None
            above, total = breadth.get(d[:10], (0, 0))
            br = round(above / total * 100.0, 1) if total >= MIN_BREADTH_MEMBERS else None
            state = classify(closes[i], s50, s50_prev, br)
            if state is None:
                continue
            counts[state] += 1
            rows.append({"date": d[:10], "state": state, "index_close": round(closes[i], 2),
                         "sma50": round(s50, 2), "sma200": round(s200, 2) if s200 is not None else None,
                         "breadth_pct": br, "breadth_members": total or None,
                         "source": bench.get("source")})
        if persist and rows:
            now = _now_iso()
            db.executemany(
                "INSERT OR REPLACE INTO regime_daily (date, state, index_close, sma50, sma200, breadth_pct, "
                " breadth_members, source, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(r["date"], r["state"], r["index_close"], r["sma50"], r["sma200"], r["breadth_pct"],
                  r["breadth_members"], r["source"], now) for r in rows],
            )
            invalidate()
        latest = rows[-1] if rows else None
        return {"rows": len(rows), "range": range_, "universe": universe, "benchmark": bench.get("source"),
                "breadth_symbols": len(syms), "counts": counts, "latest": latest,
                "text": sentence(latest) if latest else None,
                "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("regime.compute failed")
        return {"error": str(exc)}


def update_today() -> dict:
    """Post-close stage: refresh the last year of regime rows (cheap once the
    universe candles are cached) and return the current row."""
    res = compute("1y")
    if "error" in res:
        return res
    return {**res, "current": current()}


def backfill(range_: str = "5y", progress: Any = None) -> dict:
    """Multi-year regime history for grading (run inside the re-grade job)."""
    return compute(range_, progress=progress)


# ── read ─────────────────────────────────────────────────────────────────────


def current() -> dict:
    """Latest regime row with its sentence, or state None when nothing is stored.

    ``stale`` is True when the row predates the last completed session — the
    post-close job has not run yet (or failed), so the reading is yesterday's.
    """
    try:
        rows = db.query("SELECT * FROM regime_daily ORDER BY date DESC LIMIT 1")
        if not rows:
            return {"state": None, "date": None, "text": sentence({}), "stale": True, "measured": False}
        row = dict(rows[0])
        stale = False
        try:
            from app import calendar_egx

            session = calendar_egx.last_completed_session().strftime("%Y-%m-%d")
            stale = str(row.get("date")) < session
        except Exception:  # noqa: BLE001
            pass
        row.update({"text": sentence(row), "stale": stale, "measured": True})
        return row
    except Exception as exc:  # noqa: BLE001
        return {"state": None, "error": str(exc), "text": sentence({}), "stale": True, "measured": False}


def current_state() -> Optional[str]:
    """Just the state string ('bull' | 'neutral' | 'bear'), or None."""
    c = current()
    return c.get("state") if isinstance(c, dict) else None


def history(limit: int = 260) -> list[dict]:
    """Most recent regime rows, oldest first (for a strip chart)."""
    try:
        rows = db.query("SELECT date, state, index_close, sma50, sma200, breadth_pct FROM regime_daily "
                        "ORDER BY date DESC LIMIT ?", (max(1, int(limit)),))
        return list(reversed(rows))
    except Exception as exc:  # noqa: BLE001
        logger.warning("regime.history failed: %s", exc)
        return []
