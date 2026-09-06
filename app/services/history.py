"""Historical OHLCV candles via the Yahoo Finance v8 chart API."""
from __future__ import annotations

import logging
import random
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.symbols import tv_to_yahoo

_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_TIMEOUT = 15.0
_CACHE_TTL = 600.0        # 10 minutes for a good response
_NEG_CACHE_TTL = 60.0     # remember a failure this long (don't hammer)
_STALE_MAX = 86_400.0     # serve an expired entry up to a day old on failure
_MAX_CACHE_ENTRIES = 256
_RETRIES = 3

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
_neg_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
#: Set when Yahoo 429s — every symbol backs off, not just the one that hit it.
_throttled_until = 0.0
_cache_lock = threading.Lock()


def _prune_cache() -> None:
    """Drop the oldest entries once the caches exceed their bound (called under lock)."""
    if len(_cache) > _MAX_CACHE_ENTRIES:
        for key, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[: len(_cache) // 4]:
            _cache.pop(key, None)
    if len(_neg_cache) > _MAX_CACHE_ENTRIES:
        for key, _ in sorted(_neg_cache.items(), key=lambda kv: kv[1][0])[: len(_neg_cache) // 4]:
            _neg_cache.pop(key, None)


def _candle_time(ts: int, interval: str) -> str:
    """Format a unix timestamp for the given interval.

    Daily+ intervals get plain dates; intraday keeps the time component.
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    if interval.endswith(("d", "wk", "mo")):
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_chart(payload: dict[str, Any], symbol: str, interval: str) -> dict:
    """Convert a Yahoo v8 chart payload into the contract candle shape."""
    chart = payload.get("chart") or {}
    err = chart.get("error")
    if err:
        desc = err.get("description") or err.get("code") or str(err)
        return {"error": f"Yahoo chart error for {symbol}: {desc}"}

    results = chart.get("result") or []
    if not results:
        return {"error": f"No chart data returned for {symbol}"}

    result = results[0] or {}
    timestamps = result.get("timestamp") or []
    indicators = (result.get("indicators") or {}).get("quote") or [{}]
    quote = indicators[0] or {}
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    candles: list[dict] = []
    rejected = 0
    for i, ts in enumerate(timestamps):
        try:
            o, h, low, c = opens[i], highs[i], lows[i], closes[i]
        except IndexError:
            break
        if None in (ts, o, h, low, c):
            continue  # skip null candles (halts / partial rows)
        # A zero or negative price is corrupt data, not a real bar — it used
        # to flow into indicators and snapshots as a genuine quote. Likewise a
        # high below the low means the row is inconsistent.
        try:
            o_f, h_f, l_f, c_f = float(o), float(h), float(low), float(c)
        except (TypeError, ValueError):
            rejected += 1
            continue
        if min(o_f, h_f, l_f, c_f) <= 0 or h_f < l_f:
            rejected += 1
            continue
        vol = volumes[i] if i < len(volumes) else None
        candles.append(
            {
                "time": _candle_time(int(ts), interval),
                "open": round(o_f, 4),
                "high": round(h_f, 4),
                "low": round(l_f, 4),
                "close": round(c_f, 4),
                "volume": float(vol) if vol is not None else 0.0,
            }
        )

    if not candles:
        return {"error": f"No usable candles returned for {symbol}"}
    if rejected:
        logger.warning("%s: dropped %d invalid candle(s) from Yahoo", symbol, rejected)
    out: dict[str, Any] = {"symbol": symbol, "candles": candles}
    if rejected:
        out["rejected_candles"] = rejected
    return out


def _stale_or_error(key: tuple[str, str, str], now: float, error: dict,
                    record: bool = True) -> dict:
    """Serve an expired-but-recent cache entry rather than an error, if we have one.

    A chart that is 20 minutes stale beats an empty panel during a Yahoo
    outage — the returned payload says so via ``stale``/``stale_age_s``.

    ``record=False`` MUST be used when serving from an existing neg-cache hit:
    re-stamping the entry there gives the negative cache a *sliding* expiry, so
    a chart polling every 10s would keep the 60s TTL from ever elapsing and
    Yahoo would never be retried.
    """
    with _cache_lock:
        if record:
            _neg_cache[key] = (now, error)
        hit = _cache.get(key)
    if hit is not None and now - hit[0] < _STALE_MAX:
        stale = dict(hit[1])
        stale["stale"] = True
        stale["stale_age_s"] = int(now - hit[0])
        stale["stale_reason"] = error.get("error", "upstream unavailable")
        return stale
    return error


def invalidate(symbol: str) -> int:
    """Forget every cached response (good and failed) for `symbol`."""
    yahoo_symbol = tv_to_yahoo(symbol)
    with _cache_lock:
        keys = [k for k in _cache if k[0] == yahoo_symbol]
        neg_keys = [k for k in _neg_cache if k[0] == yahoo_symbol]
        for k in keys:
            _cache.pop(k, None)
        for k in neg_keys:
            _neg_cache.pop(k, None)
    return len(keys) + len(neg_keys)


def get_history(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
    """Fetch OHLCV history for an EGX symbol from Yahoo Finance.

    Returns {"symbol", "candles": [{"time","open","high","low","close",
    "volume"}, ...]} or {"error": "..."}. Successful results are cached for
    10 minutes; failures are negative-cached for 60s (so a dashboard refresh
    during a 429 storm does not prolong the throttle), retried with
    exponential backoff, and fall back to a stale cache entry when possible.
    """
    global _throttled_until
    try:
        yahoo_symbol = tv_to_yahoo(symbol)
        key = (yahoo_symbol, range_, interval)
        now = _time.monotonic()

        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None and now - hit[0] < _CACHE_TTL:
                return dict(hit[1])   # shallow copy — callers must not poison the cache
            neg = _neg_cache.get(key)
            throttled_for = _throttled_until - now
        if neg is not None and now - neg[0] < _NEG_CACHE_TTL:
            # record=False: serving a remembered failure must not extend its TTL.
            return _stale_or_error(key, now, neg[1], record=False)

        if throttled_for > 0:
            return _stale_or_error(
                key, now,
                {"error": f"Yahoo rate limit — backing off {int(throttled_for)}s"},
            )

        url = _BASE_URL.format(symbol=yahoo_symbol)
        params = {"interval": interval, "range": range_}
        last_error: dict = {"error": f"no response for {yahoo_symbol}"}

        for attempt in range(_RETRIES):
            try:
                with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
                    resp = client.get(url, params=params)
            except Exception as exc:  # network error — retry
                last_error = {"error": f"Yahoo request failed for {yahoo_symbol}: {exc}"}
                if attempt < _RETRIES - 1:
                    _time.sleep(0.6 * (2 ** attempt) + random.uniform(0, 0.3))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                if resp.status_code == 429:
                    cooldown = 120.0
                    try:
                        if retry_after:
                            cooldown = max(cooldown, float(retry_after))
                    except ValueError:
                        pass
                    with _cache_lock:
                        _throttled_until = _time.monotonic() + cooldown
                    logger.warning(
                        "Yahoo 429 for %s — backing off %.0fs for ALL symbols",
                        yahoo_symbol, cooldown,
                    )
                    last_error = {"error": f"Yahoo rate limit (429) for {yahoo_symbol}"}
                    break
                last_error = {"error": f"Yahoo chart HTTP {resp.status_code} for {yahoo_symbol}"}
                if attempt < _RETRIES - 1:
                    _time.sleep(0.6 * (2 ** attempt) + random.uniform(0, 0.3))
                continue

            if resp.status_code != 200:
                # Yahoo puts a useful description in the JSON body even on 404.
                try:
                    parsed = _parse_chart(resp.json(), symbol, interval)
                except ValueError:
                    parsed = {"error": f"Yahoo chart HTTP {resp.status_code} for {yahoo_symbol}"}
                return _stale_or_error(key, now, parsed) if "error" in parsed else parsed

            try:
                result = _parse_chart(resp.json(), symbol, interval)
            except ValueError:
                last_error = {"error": f"Yahoo returned non-JSON for {yahoo_symbol}"}
                break

            if "error" not in result:
                with _cache_lock:
                    _cache[key] = (_time.monotonic(), result)
                    _neg_cache.pop(key, None)
                    _prune_cache()
                return result
            last_error = result
            break

        return _stale_or_error(key, now, last_error)
    except Exception as exc:  # noqa: BLE001 — service functions never raise
        return {"error": str(exc)}
