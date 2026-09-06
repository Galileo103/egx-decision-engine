"""Relative-strength leaders, plus the shared daily-candle cache and EGX30
benchmark series used by the Signal Scorecard.

"Which stocks to pick": names outperforming the index over 1, 3 and 6 months,
still near their 52-week high, above their 50-day average and liquid enough to
exit. Classic swing-trade pool. Everything is computed from Yahoo daily
candles (delayed, dividend-unadjusted — see history.py) so it works even when
TradingView is rate-limited.

Benchmark: Yahoo's ^CASE30 chart when it has real depth (it often carries a
handful of bars only); otherwise an equal-weight proxy chained from the EGX30
constituents' daily returns. The payload always says which one was used.
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
from app.config import settings
from app.symbols import universe as universe_symbols

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

#: Sessions per horizon (EGX ~245 sessions/yr).
HORIZONS: dict[str, int] = {"1m": 21, "3m": 63, "6m": 126}
#: RS score weights per horizon (3m carries the most, as in classic RS ranks).
_WEIGHTS: dict[str, float] = {"1m": 0.3, "3m": 0.4, "6m": 0.3}
#: Within this % of the 52-week high counts as "at new highs".
NEW_HIGH_PCT = 2.0
_MIN_BENCH_BARS = 200
_CANDLE_TTL = 4 * 3600.0
_FETCH_PAUSE = 0.1

_candle_cache: dict[str, tuple[float, list[dict]]] = {}
_bench_cache: tuple[float, dict[str, Any]] | None = None
_lock = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def daily_candles(symbol: str, range_: str = "1y") -> list[dict]:
    """Daily candles (oldest first) for a bare EGX ticker or an index symbol.

    Wraps history.get_history with a longer in-process TTL so the scorecard
    and the leaders scan — which touch the same 100 symbols — do not refetch.
    Returns [] when unavailable.

    Yahoo publishes an EGX daily bar roughly a full session late: the session
    that just closed arrives as an all-null row (dropped below) and only fills
    the next day. Left alone, every card computed from these candles — the
    checklist, levels, patterns, the scanners and setups — reads one session
    stale, which for a post-close decision is the one session that matters. So
    the just-closed session is grafted on from the snapshot the post-close job
    already wrote from TradingView (`market.session_bar`). The two sources agree
    on closes to the piastre; TradingView volume can differ by a couple of
    percent, which is immaterial to a 20-day volume average.
    """
    # The expected session is part of the cache key on purpose. A fetch made
    # while the market was still open (the 10-minute intraday job) legitimately
    # has no bar for today, and with a plain key that entry would shadow the
    # post-close stitch for the rest of the 4-hour TTL.
    try:
        from app import calendar_egx

        session = calendar_egx.last_completed_session().strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 — never let the calendar break a fetch
        session = ""
    key = f"{symbol.upper()}|{range_}|{session}"
    now = time.monotonic()
    with _lock:
        hit = _candle_cache.get(key)
        if hit and now - hit[0] < _CANDLE_TTL:
            return hit[1]
    try:
        from app.services import history

        payload = history.get_history(symbol, range_, "1d")
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily_candles(%s) failed: %s", symbol, exc)
        return []
    if not isinstance(payload, dict) or "error" in payload:
        return []
    # Dividends / splits ride along with the bars: keep them so the pattern
    # scanner and the Guardian can tell an ex-date gap from a market move.
    if payload.get("events"):
        try:
            from app.services import corporate_actions

            corporate_actions.record_yahoo(symbol, payload.get("events"))
        except Exception as exc:  # noqa: BLE001 — bookkeeping must never break a fetch
            logger.warning("corporate actions bookkeeping failed for %s: %s", symbol, exc)
    candles = [
        c for c in (payload.get("candles") or [])
        if isinstance(c, dict) and _num(c.get("close")) is not None
    ]
    candles.sort(key=lambda c: str(c.get("time")))
    if is_dead_feed(candles):
        # Yahoo carries some EGX tickers as a flat line with zero volume for
        # months (ORAS sat at 71.05 for a year while trading ~850). A flat line
        # yields no signals on its own, but graft one real session onto it and
        # it becomes a +1000% "breakout" — so the whole series is unusable.
        logger.warning("daily_candles(%s): Yahoo series is a dead feed (flat close, zero volume) — ignored",
                       symbol)
        candles = []
    # Requires a real Yahoo series to graft onto: when Yahoo has nothing for a
    # symbol, one snapshot bar is not history, and a 1-bar series is worse than
    # an empty one to every caller that guards on bar count.
    if session and candles and str(candles[-1].get("time")) < session:
        bar = _session_bar(symbol)
        # Only ever appends: a bar dated at or before what Yahoo already has is
        # dropped rather than allowed to overwrite the authoritative history.
        if bar and str(bar.get("time")) > str(candles[-1].get("time")):
            candles = candles + [bar]
    with _lock:
        _candle_cache[key] = (now, candles)
        if len(_candle_cache) > 400:
            for k, _ in sorted(_candle_cache.items(), key=lambda kv: kv[1][0])[:100]:
                _candle_cache.pop(k, None)
    return candles


def invalidate(symbol: str) -> int:
    """Drop every cached candle series for `symbol` (all ranges/sessions).

    The on-demand stock refresh calls this so a Yahoo backfill — or a snapshot
    row that did not exist a minute ago — is seen now, not after the 4-hour TTL.
    """
    prefix = f"{symbol.upper()}|"
    with _lock:
        keys = [k for k in _candle_cache if k.startswith(prefix)]
        for k in keys:
            _candle_cache.pop(k, None)
    return len(keys)


_DEAD_FEED_BARS = 10


def is_dead_feed(candles: list[dict]) -> bool:
    """True when the last bars are one unchanging close with no volume at all.

    A genuinely suspended stock looks the same, and dropping it is right too:
    nothing traded, so nothing can be a signal.
    """
    tail = candles[-_DEAD_FEED_BARS:]
    if len(tail) < _DEAD_FEED_BARS:
        return False
    closes = {c.get("close") for c in tail}
    return len(closes) == 1 and not any(_num(c.get("volume")) for c in tail)


def _session_bar(symbol: str) -> Optional[dict]:
    """market.session_bar, imported lazily (market imports this module's peers)."""
    try:
        from app.services import market

        return market.session_bar(symbol)
    except Exception as exc:  # noqa: BLE001 — the graft is an enhancement
        logger.warning("session_bar(%s) unavailable: %s", symbol, exc)
        return None


def _proxy_index(symbols: list[str], range_: str = "1y") -> dict[str, float]:
    """Equal-weight index level per date, chained from members' daily returns."""
    series: dict[str, dict[str, float]] = {}
    for sym in symbols:
        candles = daily_candles(sym, range_)
        if len(candles) < 30:
            continue
        prev: Optional[float] = None
        for c in candles:
            close = _num(c.get("close"))
            date = str(c.get("time"))
            if close is None or close <= 0:
                continue
            if prev:
                series.setdefault(date, {})[sym] = close / prev - 1.0
            prev = close
        time.sleep(_FETCH_PAUSE)
    level = 100.0
    out: dict[str, float] = {}
    # A date needs a reasonable share of members reporting, else one thin
    # name would drive the whole "index" that day.
    min_members = max(2, min(5, len(symbols) // 2))
    for date in sorted(series):
        rets = list(series[date].values())
        if len(rets) < min_members:
            continue
        level *= 1.0 + sum(rets) / len(rets)
        out[date] = level
    return out


_bench_cache_by_range: dict[str, tuple[float, dict[str, Any]]] = {}


def benchmark_series(force: bool = False, range_: str = "1y") -> dict[str, Any]:
    """{"source", "series": {date: level}, "dates": [sorted dates]} for EGX30.

    ``range_`` widens the window (e.g. "5y" for multi-year backtests); each
    range is cached separately.
    """
    global _bench_cache
    now = time.monotonic()
    cached = _bench_cache if range_ == "1y" else _bench_cache_by_range.get(range_)
    if not force and cached and now - cached[0] < _CANDLE_TTL:
        return cached[1]
    source = "^CASE30 (Yahoo)"
    series: dict[str, float] = {}
    idx = daily_candles("^CASE30", range_)
    if len(idx) >= _MIN_BENCH_BARS:
        series = {str(c["time"]): float(c["close"]) for c in idx}
    else:
        source = "equal-weight EGX30 proxy (Yahoo constituents)"
        try:
            series = _proxy_index(universe_symbols("EGX30"), range_)
        except Exception as exc:  # noqa: BLE001
            logger.warning("EGX30 proxy failed: %s", exc)
            series = {}
    result = {"source": source, "series": series, "dates": sorted(series), "bars": len(series),
              "range": range_}
    if range_ == "1y":
        _bench_cache = (now, result)
    else:
        _bench_cache_by_range[range_] = (now, result)
    return result


def benchmark_return(bench: dict[str, Any], d0: str, d1: str) -> Optional[float]:
    """Benchmark return between two dates (nearest available bar at/before each)."""
    dates: list[str] = bench.get("dates") or []
    series: dict[str, float] = bench.get("series") or {}
    if not dates:
        return None

    def level_at(date: str) -> Optional[float]:
        # Largest bar date <= date (binary search on the sorted list).
        lo, hi = 0, len(dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if dates[mid] <= date:
                lo = mid + 1
            else:
                hi = mid
        return series.get(dates[lo - 1]) if lo > 0 else None

    a, b = level_at(d0), level_at(d1)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """0-100 percentile rank per key (100 = best)."""
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    n = len(ordered)
    if n == 1:
        return {ordered[0][0]: 100.0}
    out: dict[str, float] = {}
    i = 0
    while i < n:  # ties share the rank of the group's top position
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        for k, _ in ordered[i:j + 1]:
            out[k] = round(j / (n - 1) * 100.0, 1)
        i = j + 1
    return out


# ── computation ──────────────────────────────────────────────────────────────


def _symbol_metrics(symbol: str, bench: dict[str, Any]) -> Optional[dict]:
    candles = daily_candles(symbol)
    if len(candles) < HORIZONS["1m"] + 2:
        return None
    closes = [float(c["close"]) for c in candles]
    dates = [str(c["time"]) for c in candles]
    last = closes[-1]
    row: dict[str, Any] = {
        "symbol": symbol,
        "price": round(last, 4),
        "as_of": dates[-1],
        "bars": len(closes),
    }
    for name, h in HORIZONS.items():
        if len(closes) > h and closes[-1 - h] > 0:
            ret = last / closes[-1 - h] - 1.0
            b = benchmark_return(bench, dates[-1 - h], dates[-1])
            row[f"ret_{name}"] = round(ret * 100.0, 2)
            row[f"bench_{name}"] = round(b * 100.0, 2) if b is not None else None
            row[f"excess_{name}"] = round((ret - b) * 100.0, 2) if b is not None else None
        else:
            row[f"ret_{name}"] = row[f"bench_{name}"] = row[f"excess_{name}"] = None
    window = candles[-252:]
    high_52 = max((_num(c.get("high")) or 0.0) for c in window) or None
    row["high_52w"] = round(high_52, 4) if high_52 else None
    row["pct_from_52w_high"] = round((last / high_52 - 1.0) * 100.0, 2) if high_52 else None
    row["new_high"] = bool(high_52 and last >= high_52 * (1 - NEW_HIGH_PCT / 100.0))
    if len(closes) >= 50:
        sma50 = sum(closes[-50:]) / 50.0
        row["sma50"] = round(sma50, 4)
        row["above_sma50"] = last > sma50
    else:
        row["sma50"] = None
        row["above_sma50"] = None
    values = sorted(
        (float(c["close"]) * (_num(c.get("volume")) or 0.0)) for c in candles[-20:]
    )
    row["median_value_20d"] = round(values[len(values) // 2], 0) if values else None
    return row


# ── sectors (TA roadmap Task 7) ──────────────────────────────────────────────

#: Sector index rows are stored in rs_leaders under this symbol prefix.
SECTOR_PREFIX = "SECTOR:"
#: A sector needs this many members with usable candles before it gets an index.
MIN_SECTOR_MEMBERS = 2


def sector_of(symbol: str) -> Optional[str]:
    """Sector key for a bare EGX ticker ('banks', 'real_estate', …); None when unclassified."""
    try:
        from tradingview_mcp.core.data.egx_sectors import get_sector

        s = get_sector(str(symbol or "").upper().split(":")[-1])
        return s if s and s != "other" else None
    except Exception:  # noqa: BLE001
        return None


def sector_label(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    try:
        from tradingview_mcp.core.data.egx_sectors import SECTOR_DISPLAY_NAMES

        return str(SECTOR_DISPLAY_NAMES.get(key) or key.replace("_", " ").title())
    except Exception:  # noqa: BLE001
        return key.replace("_", " ").title()


def _series_return(series: dict[str, float], dates: list[str], h: int) -> Optional[float]:
    if len(dates) <= h:
        return None
    a, b = series.get(dates[-1 - h]), series.get(dates[-1])
    return (b / a - 1.0) if (a and b and a > 0) else None


def sector_strength(rows: list[dict], bench: dict[str, Any]) -> list[dict]:
    """Equal-weight sector indices built from the ranked stocks' own candles (already
    cached by the sweep), with 1m/3m/6m returns and excess over EGX30, ranked by the
    same 30/40/30 weighting as the stocks. Pure apart from the candle cache."""
    groups: dict[str, list[str]] = {}
    for r in rows:
        sec = r.get("sector")
        if sec:
            groups.setdefault(sec, []).append(str(r["symbol"]))
    out: list[dict] = []
    for sec, members in groups.items():
        if len(members) < MIN_SECTOR_MEMBERS:
            continue
        series = _proxy_index(members)
        dates = sorted(series)
        if len(dates) < HORIZONS["1m"] + 2:
            continue
        row: dict[str, Any] = {"sector": sec, "label": sector_label(sec), "members": len(members),
                               "symbols": sorted(members), "as_of": dates[-1]}
        for name, h in HORIZONS.items():
            ret = _series_return(series, dates, h)
            b = benchmark_return(bench, dates[-1 - h], dates[-1]) if len(dates) > h else None
            row[f"ret_{name}"] = round(ret * 100.0, 2) if ret is not None else None
            row[f"excess_{name}"] = round((ret - b) * 100.0, 2) if (ret is not None and b is not None) else None
        out.append(row)
    # Weighted score across horizons (excess, falling back to raw return), then rank.
    ranks: dict[str, dict[str, float]] = {}
    for name in HORIZONS:
        vals = {}
        for r in out:
            v = r.get(f"excess_{name}")
            if v is None:
                v = r.get(f"ret_{name}")
            if v is not None:
                vals[r["sector"]] = float(v)
        ranks[name] = _percentile_ranks(vals)
    for r in out:
        total, weight = 0.0, 0.0
        for name, w in _WEIGHTS.items():
            pr = ranks[name].get(r["sector"])
            if pr is not None:
                total += pr * w
                weight += w
        r["rs_score"] = round(total / weight, 1) if weight else None
    out.sort(key=lambda r: (r.get("rs_score") is not None, r.get("rs_score") or 0.0), reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def attach_sectors(rows: list[dict], sectors: list[dict]) -> None:
    """Stamp each stock row with its sector, the sector's rank, the stock's rank inside
    the sector (by RS score) and its 1m/3m return minus the sector's. In place."""
    by_sec = {s["sector"]: s for s in sectors}
    n_sectors = len(sectors)
    members: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("sector"):
            members.setdefault(r["sector"], []).append(r)
    for sec, rs in members.items():
        rs_sorted = sorted(rs, key=lambda r: (r.get("rs_score") is not None, r.get("rs_score") or 0.0), reverse=True)
        for i, r in enumerate(rs_sorted, 1):
            r["rank_in_sector"] = i
            r["sector_size"] = len(rs_sorted)
    for r in rows:
        sec = r.get("sector")
        s = by_sec.get(sec) if sec else None
        r["sector_label"] = sector_label(sec)
        r["sector_rank"] = s.get("rank") if s else None
        r["sector_count"] = n_sectors
        r["sector_rs_score"] = s.get("rs_score") if s else None
        for name in ("1m", "3m"):
            sr = s.get(f"ret_{name}") if s else None
            r[f"rs_vs_sector_{name}"] = (round(r[f"ret_{name}"] - sr, 2)
                                         if (s and r.get(f"ret_{name}") is not None and sr is not None) else None)
        r.setdefault("rank_in_sector", None)
        r.setdefault("sector_size", None)


def sector_context(symbol: str, universe: str = "EGX100") -> Optional[dict]:
    """The stored sector reading for one stock (instant, from the latest ranking):
    {sector, sector_label, sector_rank, sector_count, sector_excess_3m, rank_in_sector,
    sector_size, rs_vs_sector_1m, rs_vs_sector_3m, date}. None when not ranked."""
    try:
        sym = str(symbol or "").upper().split(":")[-1]
        uni = (universe or "EGX100").upper()
        d = db.query("SELECT MAX(date) AS d FROM rs_leaders WHERE universe = ?", (uni,))
        date = d[0].get("d") if d else None
        if not date:
            return None
        rows = db.query("SELECT payload_json FROM rs_leaders WHERE universe = ? AND date = ? AND symbol = ?",
                        (uni, date, sym))
        if not rows:
            return None
        r = json.loads(rows[0]["payload_json"])
        sec = r.get("sector")
        if not sec:
            return {"sector": None, "date": date}
        srow = db.query("SELECT payload_json FROM rs_leaders WHERE universe = ? AND date = ? AND symbol = ?",
                        (uni, date, SECTOR_PREFIX + sec))
        s = json.loads(srow[0]["payload_json"]) if srow else {}
        return {"sector": sec, "sector_label": r.get("sector_label") or sector_label(sec),
                "sector_rank": r.get("sector_rank"), "sector_count": r.get("sector_count"),
                "sector_rs_score": s.get("rs_score"), "sector_excess_1m": s.get("excess_1m"),
                "sector_excess_3m": s.get("excess_3m"), "rank_in_sector": r.get("rank_in_sector"),
                "sector_size": r.get("sector_size"), "rs_vs_sector_1m": r.get("rs_vs_sector_1m"),
                "rs_vs_sector_3m": r.get("rs_vs_sector_3m"), "date": date}
    except Exception as exc:  # noqa: BLE001
        logger.warning("sector_context(%s) failed: %s", symbol, exc)
        return None


def sector_sentence(ctx: Optional[dict]) -> str:
    """One sentence for the checklist's Trend pillar; '' when nothing is stored."""
    if not ctx or not ctx.get("sector") or ctx.get("sector_rank") is None:
        return ""
    lead = ctx["sector_rank"] <= max(1, (ctx.get("sector_count") or 1) // 3)
    lag = ctx["sector_rank"] > (ctx.get("sector_count") or 1) - max(1, (ctx.get("sector_count") or 1) // 3)
    txt = (f"Sector: {ctx['sector_label']} ranks {ctx['sector_rank']} of {ctx['sector_count']} sectors by relative "
           f"strength" + (" — a leading sector" if lead else " — a lagging sector; money is elsewhere" if lag else ""))
    if ctx.get("rank_in_sector") and ctx.get("sector_size"):
        txt += f"; the stock is #{ctx['rank_in_sector']} of {ctx['sector_size']} inside it"
    if ctx.get("rs_vs_sector_1m") is not None:
        txt += f" ({ctx['rs_vs_sector_1m']:+.1f} pts vs the sector over 1m)"
    return txt + "."


def compute(
    universe: str = "EGX100",
    limit: int = 40,
    persist: bool = False,
    include_illiquid: bool = False,
) -> dict:
    """Rank a universe by relative strength vs EGX30. Never raises."""
    try:
        started = time.monotonic()
        uni = (universe or "EGX100").upper()
        symbols = universe_symbols(uni)
        bench = benchmark_series()
        rows: list[dict] = []
        skipped = 0
        for sym in symbols:
            try:
                row = _symbol_metrics(sym, bench)
            except Exception as exc:  # noqa: BLE001
                logger.warning("leaders: %s failed: %s", sym, exc)
                row = None
            if row is None:
                skipped += 1
            else:
                row["sector"] = sector_of(sym)
                rows.append(row)
            time.sleep(_FETCH_PAUSE)

        # RS score: weighted percentile rank of EXCESS return per horizon
        # (falls back to raw return when no benchmark bar exists for a date).
        ranks: dict[str, dict[str, float]] = {}
        for name in HORIZONS:
            vals = {}
            for r in rows:
                v = r.get(f"excess_{name}")
                if v is None:
                    v = r.get(f"ret_{name}")
                if v is not None:
                    vals[r["symbol"]] = float(v)
            ranks[name] = _percentile_ranks(vals)
        for r in rows:
            total, weight = 0.0, 0.0
            for name, w in _WEIGHTS.items():
                pr = ranks[name].get(r["symbol"])
                if pr is not None:
                    total += pr * w
                    weight += w
            r["rs_score"] = round(total / weight, 1) if weight else None

        min_value = float(settings.min_daily_value_egp)
        filtered = 0
        kept: list[dict] = []
        for r in rows:
            liq = r.get("median_value_20d")
            r["liquid"] = None if liq is None else liq >= min_value
            if not include_illiquid and liq is not None and liq < min_value:
                filtered += 1
                continue
            kept.append(r)
        kept.sort(key=lambda r: (r.get("rs_score") is not None, r.get("rs_score") or 0.0), reverse=True)
        for i, r in enumerate(kept, 1):
            r["rank"] = i
        # Sector strength from the same candles (all cached by now): equal-weight
        # sector indices ranked like the stocks, then each stock's place in its sector.
        sectors = sector_strength(rows, bench)
        attach_sectors(rows, sectors)
        top = kept[: max(1, int(limit))]
        date = datetime.now(CAIRO).strftime("%Y-%m-%d")
        if persist and kept:
            _persist(date, uni, kept, sectors)
        return {
            "rows": top,
            "sectors": sectors,
            "universe": uni,
            "date": date,
            "as_of": _now_iso(),
            "benchmark": bench.get("source"),
            "benchmark_bars": bench.get("bars"),
            "scanned": len(symbols),
            "ranked": len(kept),
            "skipped_no_data": skipped,
            "filtered_illiquid": filtered,
            "min_daily_value_egp": min_value,
            "elapsed_s": round(time.monotonic() - started, 1),
            "basis": (
                "Returns from Yahoo daily closes (delayed, not dividend-adjusted). "
                "RS score = percentile rank of excess return vs EGX30 over 1m/3m/6m, "
                "weighted 30/40/30. New high = within 2% of the 52-week high. Sector strength = the "
                "same measure on an equal-weight index of each sector's ranked members; rank in sector = "
                "the stock's RS score against its sector peers."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("leaders.compute failed")
        return {"error": str(exc)}


def _persist(date: str, uni: str, rows: list[dict], sectors: Optional[list[dict]] = None) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO rs_leaders (date, universe, symbol, rank, rs_score, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (date, uni, r["symbol"], r.get("rank"), r.get("rs_score"), json.dumps(r), _now_iso())
            for r in rows
        ] + [
            # Sector indices share the table under a reserved symbol prefix so one
            # date's ranking is one transaction and one read.
            (date, uni, SECTOR_PREFIX + s["sector"], s.get("rank"), s.get("rs_score"), json.dumps(s), _now_iso())
            for s in (sectors or [])
        ],
    )


def latest(universe: str = "EGX100", limit: int = 40, sector: Optional[str] = None) -> dict:
    """Most recently persisted ranking for a universe (fast path for the UI).
    ``sector`` filters the stock rows to one sector key; the sector table is always returned."""
    try:
        uni = (universe or "EGX100").upper()
        dates = db.query(
            "SELECT MAX(date) AS d FROM rs_leaders WHERE universe = ?", (uni,)
        )
        date = dates[0].get("d") if dates else None
        if not date:
            return {"rows": [], "sectors": [], "universe": uni, "date": None, "stored": False}
        rows = db.query(
            "SELECT symbol, payload_json FROM rs_leaders WHERE universe = ? AND date = ? ORDER BY rank ASC",
            (uni, date),
        )
        out: list[dict] = []
        sectors: list[dict] = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (TypeError, ValueError):
                continue
            if str(r["symbol"]).startswith(SECTOR_PREFIX):
                sectors.append(payload)
            else:
                out.append(payload)
        total = len(out)
        if sector:
            out = [r for r in out if r.get("sector") == sector]
        out = out[: max(1, int(limit))]
        return {
            "rows": out, "sectors": sectors, "universe": uni, "date": date, "stored": True,
            "ranked": total, "sector": sector,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
