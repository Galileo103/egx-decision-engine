"""Corporate actions — the calendar the charts do not know about.

An ex-dividend gap, a rights issue or a capital increase moves a stock for a
reason that has nothing to do with buyers and sellers, yet the pattern
scanner reads the gap as a break of structure or a bear trap, the Guardian
reads it as a stop touch, and the checklist counts it as a bearish event.
This module keeps one table of dated events per symbol from two sources:

* ``yahoo``  — dividends and splits Yahoo returns alongside the daily bars
               (recorded whenever ``leaders.daily_candles`` fetches a series);
* ``manual`` — upcoming ex-dates, rights and capital increases the user types
               in (EGX publishes them, no feed does).

Readers: ``patterns.detect`` tags a row whose trigger bar sits on an event as
``suspect``; the checklist ignores suspect rows; the Guardian and the
checklist Risk pillar warn when a known event is within EX_DATE_WARN_DAYS.
Never raises; write functions return {"ok": True} only after the row exists.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

TYPES: tuple[str, ...] = ("dividend", "split", "rights", "capital_increase", "bonus", "other")
LABELS: dict[str, str] = {
    "dividend": "ex-dividend", "split": "split", "rights": "rights issue",
    "capital_increase": "capital increase", "bonus": "bonus shares", "other": "corporate action",
}
#: Warn when an event falls within this many calendar days ahead.
EX_DATE_WARN_DAYS = 5
#: A pattern trigger within this many sessions of an event is tagged suspect.
GAP_TOLERANCE_DAYS = 1


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _sym(s: Any) -> str:
    return str(s or "").upper().strip().split(":")[-1]


def _d(s: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── writes ───────────────────────────────────────────────────────────────────


def record_yahoo(symbol: str, events: Any) -> int:
    """Upsert the dividends / splits Yahoo returned with a chart. Returns rows written."""
    sym = _sym(symbol)
    if not sym or not isinstance(events, list) or not events:
        return 0
    rows = []
    for e in events:
        if not isinstance(e, dict):
            continue
        kind = str(e.get("type") or "")
        d = _d(e.get("date"))
        if kind not in ("dividend", "split") or not d:
            continue
        rows.append((sym, kind, d.isoformat(), _num(e.get("amount")), _num(e.get("ratio")),
                     str(e.get("note") or ""), "yahoo", _now_iso()))
    if not rows:
        return 0
    try:
        return db.executemany(
            "INSERT OR REPLACE INTO corporate_actions (symbol, type, ex_date, amount, ratio, note, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_yahoo(%s) failed: %s", sym, exc)
        return 0


def add(symbol: str, type_: str, ex_date: str, amount: Optional[float] = None,
        ratio: Optional[float] = None, note: str = "") -> dict:
    """Manual entry (upcoming or past). ``ok`` only after the row is readable."""
    try:
        sym = _sym(symbol)
        if not sym:
            return {"error": "symbol is required"}
        kind = str(type_ or "").lower().strip()
        if kind not in TYPES:
            return {"error": f"type must be one of {', '.join(TYPES)}"}
        d = _d(ex_date)
        if not d:
            return {"error": "ex_date must be a YYYY-MM-DD date"}
        db.execute(
            "INSERT OR REPLACE INTO corporate_actions (symbol, type, ex_date, amount, ratio, note, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)",
            (sym, kind, d.isoformat(), _num(amount), _num(ratio), str(note or "").strip(), _now_iso()),
        )
        rows = db.query("SELECT * FROM corporate_actions WHERE symbol = ? AND type = ? AND ex_date = ? AND source = 'manual'",
                        (sym, kind, d.isoformat()))
        if not rows:
            return {"error": "event was not stored"}
        return {"ok": True, **_shape(rows[0])}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def delete(action_id: int) -> dict:
    """Remove one manual event (Yahoo rows are re-derived, so they are not deletable)."""
    try:
        n = db.execute_rowcount("DELETE FROM corporate_actions WHERE id = ? AND source = 'manual'", (int(action_id),))
        return {"ok": True, "deleted": n} if n else {"error": f"manual event {action_id} not found"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── reads ────────────────────────────────────────────────────────────────────


def _shape(r: dict) -> dict:
    out = dict(r)
    out["label"] = LABELS.get(str(r.get("type")), str(r.get("type")))
    return out


def for_symbol(symbol: str, since: Optional[str] = None) -> list[dict]:
    """Every stored event for a symbol (oldest first), optionally from ``since``."""
    try:
        sym = _sym(symbol)
        if since:
            rows = db.query("SELECT * FROM corporate_actions WHERE symbol = ? AND ex_date >= ? ORDER BY ex_date",
                            (sym, str(since)[:10]))
        else:
            rows = db.query("SELECT * FROM corporate_actions WHERE symbol = ? ORDER BY ex_date", (sym,))
        return [_shape(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("for_symbol(%s) failed: %s", symbol, exc)
        return []


def upcoming(symbols: Optional[list[str]] = None, days: int = 30, today: Optional[date] = None) -> list[dict]:
    """Events dated today or later within ``days`` (all symbols, or the given ones)."""
    try:
        t = today or datetime.now(CAIRO).date()
        end = t + timedelta(days=max(0, int(days)))
        if symbols:
            syms = sorted({_sym(s) for s in symbols if _sym(s)})
            if not syms:
                return []
            marks = ",".join("?" for _ in syms)
            rows = db.query(f"SELECT * FROM corporate_actions WHERE ex_date >= ? AND ex_date <= ? AND symbol IN ({marks}) "  # noqa: S608
                            "ORDER BY ex_date, symbol", [t.isoformat(), end.isoformat(), *syms])
        else:
            rows = db.query("SELECT * FROM corporate_actions WHERE ex_date >= ? AND ex_date <= ? ORDER BY ex_date, symbol",
                            (t.isoformat(), end.isoformat()))
        out = []
        for r in rows:
            s = _shape(r)
            ed = _d(r["ex_date"])
            s["days_until"] = (ed - t).days if ed else None
            out.append(s)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("upcoming failed: %s", exc)
        return []


def next_for(symbol: str, within_days: int = EX_DATE_WARN_DAYS, today: Optional[date] = None) -> Optional[dict]:
    """The nearest upcoming event for one symbol within ``within_days``, else None."""
    ev = upcoming([symbol], within_days, today)
    return ev[0] if ev else None


def warning_text(ev: Optional[dict]) -> str:
    """One sentence for the Guardian / checklist about an imminent event."""
    if not ev:
        return ""
    when = ("today" if ev.get("days_until") == 0 else f"in {ev.get('days_until')} day(s)")
    amt = ev.get("amount")
    detail = f" of {amt:.2f} EGP" if (amt is not None and ev.get("type") == "dividend") else ""
    ratio = ev.get("ratio")
    if ratio is not None and ev.get("type") in ("split", "bonus", "rights", "capital_increase"):
        detail = f" (ratio {ratio:g})"
    return (f"{LABELS.get(str(ev.get('type')), 'Corporate action').capitalize()} {when} ({ev.get('ex_date')}){detail}: "
            "the price will gap for a reason that is not buying or selling — do not read that bar as a breakdown, "
            "and check your stop is not sitting inside the gap." + (f" Note: {ev['note']}" if ev.get("note") else ""))


def events_near(symbol: str, day: Any, tolerance_days: int = GAP_TOLERANCE_DAYS) -> list[dict]:
    """Events whose ex-date is within ``tolerance_days`` of ``day`` (a pattern's trigger bar)."""
    d = _d(day)
    if not d:
        return []
    lo, hi = d - timedelta(days=tolerance_days), d + timedelta(days=tolerance_days + 2)   # +2: weekend after Thursday
    try:
        rows = db.query("SELECT * FROM corporate_actions WHERE symbol = ? AND ex_date >= ? AND ex_date <= ? ORDER BY ex_date",
                        (_sym(symbol), lo.isoformat(), hi.isoformat()))
        return [_shape(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("events_near(%s) failed: %s", symbol, exc)
        return []


def tag_suspect(symbol: str, rows: list[dict]) -> int:
    """Mark pattern rows whose trigger bar (break_date, else start_date for forming
    rows) coincides with a corporate action: ``suspect`` = one sentence. In place;
    returns how many rows were tagged. One DB read per symbol."""
    try:
        events = for_symbol(symbol)
    except Exception:  # noqa: BLE001
        events = []
    if not events:
        return 0
    by_date: list[tuple[date, dict]] = []
    for e in events:
        ed = _d(e["ex_date"])
        if ed:
            by_date.append((ed, e))
    tagged = 0
    for r in rows:
        anchor = _d(r.get("break_date")) if r.get("break_date") else None
        if anchor is None:
            continue
        for ed, e in by_date:
            if -GAP_TOLERANCE_DAYS <= (anchor - ed).days <= GAP_TOLERANCE_DAYS + 2:
                r["suspect"] = (f"{LABELS.get(str(e.get('type')), 'corporate action')} on {e['ex_date']}"
                                + (f" ({e['amount']:.2f} EGP)" if e.get("amount") is not None else "")
                                + " — the trigger bar is an event gap, not a market decision")
                r["suspect_event"] = {k: e.get(k) for k in ("type", "ex_date", "amount", "ratio", "source")}
                tagged += 1
                break
    return tagged
