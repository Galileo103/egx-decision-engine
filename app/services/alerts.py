"""Alert rules: CRUD, evaluation against live quotes / stored snapshots, Telegram delivery.

Rule types (params_json shapes):
    price_above / price_below : {"symbol": str, "level": float}
    score_min                 : {"universe": str} or {"symbol": str}, plus {"threshold": float}
    squeeze                   : {"universe": str, "bbw_max": float}
    signal_change             : {"symbol": str}
    entry_hit                 : {"symbol": str, "entry": float}

Price checks use the fast Yahoo quote endpoint (``get_price``); when Yahoo is
unavailable, the latest row in the ``snapshots`` table (populated daily by the
EGX screener via ``market.snapshot_universe``) is used as a fallback.
squeeze / score_min / signal_change rules read the snapshots table directly.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import httpx

from app import db
from app.config import settings
from app.symbols import tv_to_yahoo, universe

from tradingview_mcp.core.services.yahoo_finance_service import get_price

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

#: Do not refire the same (rule, symbol) pair within this window.
DEDUPE_HOURS = 6

#: Known rule types and their required parameter names.
RULE_TYPES: dict[str, list[str]] = {
    "price_above": ["symbol", "level"],
    "price_below": ["symbol", "level"],
    "score_min": ["threshold"],  # plus "universe" OR "symbol"
    "squeeze": ["universe", "bbw_max"],
    "signal_change": ["symbol"],
    "entry_hit": ["symbol", "entry"],
}


# ── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _norm_symbol(value: Any) -> str:
    """Normalize any symbol form ('comi', 'EGX:COMI') to a bare upper ticker.

    The snapshots table stores bare tickers, so every rule/evaluator must
    compare with the same form (mirrors app.services.stocks._bare).
    """
    return str(value or "").strip().upper().split(":")[-1]


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_snapshot(symbol: str, timeframe: str = "1D") -> Optional[dict]:
    """Most recent snapshots row for one symbol, or None."""
    rows = db.query(
        "SELECT * FROM snapshots WHERE symbol = ? AND timeframe = ? "
        "ORDER BY date DESC, id DESC LIMIT 1",
        (symbol.upper(), timeframe),
    )
    return rows[0] if rows else None


def _latest_snapshot_rows(timeframe: str = "1D") -> list[dict]:
    """One row per symbol from the most recent snapshot date."""
    dates = db.query(
        "SELECT MAX(date) AS d FROM snapshots WHERE timeframe = ?", (timeframe,)
    )
    if not dates or not dates[0].get("d"):
        return []
    return db.query(
        "SELECT * FROM snapshots WHERE date = ? AND timeframe = ?",
        (dates[0]["d"], timeframe),
    )


def _live_quote(symbol: str) -> Optional[dict]:
    """Fast Yahoo quote for a TV symbol; falls back to the latest snapshot row.

    Returns {"price": float, "previous_close": float | None, "source": str}
    or None when no price is available anywhere.
    """
    try:
        quote = get_price(tv_to_yahoo(symbol))
    except Exception as exc:  # get_price shouldn't raise, but be safe
        quote = {"error": str(exc)}
    price = quote.get("price") if isinstance(quote, dict) else None
    if isinstance(quote, dict) and "error" not in quote and price is not None:
        # Carry the provider's own provenance: for .CA symbols Yahoo's quote
        # block is often frozen and the price is really a daily candle close
        # ("candle_close") — alert messages must say so, not imply "live".
        return {
            "price": float(price),
            "previous_close": _to_float(quote.get("previous_close")),
            "source": str(quote.get("price_source") or "yahoo"),
        }
    # EGX screener fallback: latest persisted snapshot (screener-sourced).
    # The snapshot date is carried in `source` so every alert message states
    # how old the price is instead of presenting it as current.
    snap = _latest_snapshot(symbol)
    if snap and snap.get("price") is not None:
        return {
            "price": float(snap["price"]),
            "previous_close": None,
            "source": f"snapshot {snap.get('date') or 'unknown date'}",
        }
    return None


def _universe_symbols(name: str) -> set[str]:
    try:
        return {s.upper() for s in universe(name)}
    except Exception as exc:
        logger.warning("universe(%r) failed: %s", name, exc)
        return set()


def _parse_params(row: dict) -> dict:
    try:
        params = json.loads(row.get("params_json") or "{}")
        return params if isinstance(params, dict) else {}
    except (TypeError, ValueError):
        return {}


# ── rule CRUD ────────────────────────────────────────────────────────────────


def create_rule(name: str, rule_type: str, params: dict) -> dict:
    """Create an alert rule; returns the stored rule (or {"error": ...})."""
    try:
        if rule_type not in RULE_TYPES:
            return {
                "error": f"Unknown rule_type: {rule_type}",
                "available": sorted(RULE_TYPES),
            }
        params = dict(params or {})
        if params.get("symbol"):
            params["symbol"] = _norm_symbol(params["symbol"])
        missing = [p for p in RULE_TYPES[rule_type] if p not in params]
        if rule_type == "score_min" and not (params.get("universe") or params.get("symbol")):
            missing.append("universe|symbol")
        if missing:
            return {"error": f"Missing params for {rule_type}: {', '.join(missing)}"}
        rule_id = db.execute(
            "INSERT INTO alert_rules (name, rule_type, params_json, enabled, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (name, rule_type, json.dumps(params), _now_iso()),
        )
        rows = db.query("SELECT * FROM alert_rules WHERE id = ?", (rule_id,))
        rule = rows[0] if rows else {"id": rule_id}
        rule["params"] = params
        return rule
    except Exception as exc:
        return {"error": str(exc)}


def list_rules() -> list[dict]:
    """All alert rules with parsed params."""
    try:
        rules = db.query("SELECT * FROM alert_rules ORDER BY id")
        for rule in rules:
            rule["params"] = _parse_params(rule)
        return rules
    except Exception as exc:
        logger.error("list_rules failed: %s", exc)
        return []


def delete_rule(rule_id: int) -> dict:
    """Delete a rule by id; reports whether a row was actually removed."""
    try:
        deleted = db.execute_rowcount("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        if not deleted:
            return {"ok": False, "error": f"rule {rule_id} not found"}
        return {"ok": True, "deleted": rule_id}
    except Exception as exc:
        logger.error("delete_rule(%s) failed: %s", rule_id, exc)
        return {"ok": False, "error": str(exc)}


def toggle_rule(rule_id: int, enabled: bool) -> dict:
    """Enable/disable a rule; reports whether a row was actually updated."""
    try:
        updated = db.execute_rowcount(
            "UPDATE alert_rules SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id),
        )
        if not updated:
            return {"ok": False, "error": f"rule {rule_id} not found"}
        return {"ok": True, "rule_id": rule_id, "enabled": enabled}
    except Exception as exc:
        logger.error("toggle_rule(%s) failed: %s", rule_id, exc)
        return {"ok": False, "error": str(exc)}


# ── evaluation ───────────────────────────────────────────────────────────────


def _eval_price_threshold(rule: dict, params: dict) -> list[tuple[str, str]]:
    symbol = _norm_symbol(params.get("symbol"))
    level = _to_float(params.get("level"))
    if not symbol or level is None:
        return []
    quote = _live_quote(symbol)
    if quote is None:
        return []
    price = quote["price"]
    if rule["rule_type"] == "price_above" and price >= level:
        return [(symbol, f"{symbol} is {price:.2f} — at/above your {level:.2f} level ({quote['source']})")]
    if rule["rule_type"] == "price_below" and price <= level:
        return [(symbol, f"{symbol} is {price:.2f} — at/below your {level:.2f} level ({quote['source']})")]
    return []


def _eval_score_min(rule: dict, params: dict) -> list[tuple[str, str]]:
    threshold = _to_float(params.get("threshold"))
    if threshold is None:
        return []
    if params.get("symbol"):
        symbol = _norm_symbol(params["symbol"])
        snap = _latest_snapshot(symbol)
        rows = [snap] if snap else []
    else:
        members = _universe_symbols(str(params.get("universe", "ALL")))
        rows = [
            r for r in _latest_snapshot_rows()
            if not members or str(r.get("symbol", "")).upper() in members
        ]
    hits: list[tuple[str, str]] = []
    for row in rows:
        score = _to_float(row.get("score"))
        if score is not None and score >= threshold:
            hits.append((
                str(row["symbol"]).upper(),
                f"{row['symbol']} score {score:.1f} >= {threshold:.1f} "
                f"(signal: {row.get('signal') or 'n/a'}, {row.get('date')})",
            ))
    return hits


def _eval_squeeze(rule: dict, params: dict) -> list[tuple[str, str]]:
    bbw_max = _to_float(params.get("bbw_max"))
    if bbw_max is None:
        return []
    members = _universe_symbols(str(params.get("universe", "ALL")))
    hits: list[tuple[str, str]] = []
    for row in _latest_snapshot_rows():
        symbol = str(row.get("symbol", "")).upper()
        if members and symbol not in members:
            continue
        bbw = _to_float(row.get("bbw"))
        if bbw is not None and bbw <= bbw_max:
            hits.append((
                symbol,
                f"{symbol} in Bollinger squeeze: BBW {bbw:.4f} <= {bbw_max:.4f} ({row.get('date')})",
            ))
    return hits


def _eval_signal_change(rule: dict, params: dict) -> list[tuple[str, str]]:
    symbol = _norm_symbol(params.get("symbol"))
    if not symbol:
        return []
    rows = db.query(
        "SELECT date, signal FROM snapshots WHERE symbol = ? AND timeframe = '1D' "
        "ORDER BY date DESC, id DESC LIMIT 2",
        (symbol,),
    )
    if len(rows) < 2:
        return []
    latest, previous = rows[0], rows[1]
    if latest.get("signal") and previous.get("signal") and latest["signal"] != previous["signal"]:
        return [(
            symbol,
            f"{symbol} signal changed {previous['signal']} -> {latest['signal']} ({latest['date']})",
        )]
    return []


def _eval_entry_hit(rule: dict, params: dict) -> list[tuple[str, str]]:
    symbol = _norm_symbol(params.get("symbol"))
    entry = _to_float(params.get("entry"))
    if not symbol or entry is None:
        return []
    quote = _live_quote(symbol)
    if quote is None:
        return []
    price, prev = quote["price"], quote.get("previous_close")
    # A cross needs a reference point (previous close). Without one (snapshot
    # fallback) "price >= entry" is a persistent state, not an event — it would
    # refire every dedupe window forever, so it does not fire at all.
    if prev is None:
        return []
    if (prev < entry <= price) or (prev > entry >= price):
        return [(
            symbol,
            f"{symbol} crossed trade-plan entry {entry:.2f} since previous close "
            f"{prev:.2f} (now {price:.2f}, {quote['source']})",
        )]
    return []


_EVALUATORS: dict[str, Callable[[dict, dict], list[tuple[str, str]]]] = {
    "price_above": _eval_price_threshold,
    "price_below": _eval_price_threshold,
    "score_min": _eval_score_min,
    "squeeze": _eval_squeeze,
    "signal_change": _eval_signal_change,
    "entry_hit": _eval_entry_hit,
}


def _recently_fired(rule_id: int, symbol: str) -> bool:
    cutoff = (datetime.now(CAIRO) - timedelta(hours=DEDUPE_HOURS)).isoformat()
    rows = db.query(
        "SELECT 1 FROM alerts_fired WHERE rule_id = ? AND symbol = ? AND fired_at >= ? LIMIT 1",
        (rule_id, symbol, cutoff),
    )
    return bool(rows)


def evaluate_all() -> dict:
    """Evaluate every enabled rule; fire, persist, and (best-effort) deliver.

    Returns {"evaluated": n, "fired": [...]} — never raises.
    """
    try:
        rules = [r for r in list_rules() if r.get("enabled")]
        fired: list[dict] = []
        for rule in rules:
            evaluator = _EVALUATORS.get(rule["rule_type"])
            if evaluator is None:
                continue
            try:
                hits = evaluator(rule, rule.get("params") or {})
            except Exception as exc:
                logger.warning("rule %s (%s) evaluation failed: %s",
                               rule.get("id"), rule.get("rule_type"), exc)
                continue
            for symbol, message in hits:
                try:
                    if _recently_fired(rule["id"], symbol):
                        continue
                    text = f"[{rule.get('name') or rule['rule_type']}] {message}"
                    delivered = send_telegram(text)
                    db.execute(
                        "INSERT INTO alerts_fired (rule_id, symbol, message, fired_at, delivered) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (rule["id"], symbol, text, _now_iso(), 1 if delivered else 0),
                    )
                    fired.append({
                        "rule_id": rule["id"],
                        "name": rule.get("name"),
                        "rule_type": rule["rule_type"],
                        "symbol": symbol,
                        "message": text,
                        "delivered": delivered,
                    })
                except Exception as exc:
                    logger.error("failed to record alert for %s: %s", symbol, exc)
        return {"evaluated": len(rules), "fired": fired}
    except Exception as exc:
        return {"error": str(exc)}


# ── delivery ─────────────────────────────────────────────────────────────────


def send_telegram(text: str) -> bool:
    """POST a message to the configured Telegram chat. False when unconfigured/failed."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        logger.info("Telegram not configured; alert kept locally only")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        logger.warning("Telegram send failed: HTTP %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False
