"""Position Guardian — exit verdicts for every OPEN position.

The buy side of the app (score, trade plan, scanners, sizing) tells you what
to buy; nothing watched what you already hold. This module closes that gap:
for each open position it marks the price, re-reads the daily candles since
entry, compares today's snapshot score/signal with the one you bought on, and
returns ONE verdict plus every reason behind it.

Verdicts (most severe first — the position's verdict is the most severe one
that applies; all reasons are listed):

    EXIT_STOP      critical  mark at/below your stop — the plan says out
    TRAIL_EXIT     action    price retraced > ATR_MULT x ATR14 from its
                             post-entry high after having reached >= 1R
    TARGET2_HIT    action    mark at/above target 2 — take profit / trail tight
    TARGET1_HIT    action    mark at/above target 1 — partial + stop to breakeven
    PLAN_INVALID   warning   a recorded target sits at/below entry (or T2 <= T1) —
                             a data-entry error; such targets are ignored, never
                             "hit", and the record must be fixed
    STOP_TOUCHED   warning   today's low pierced the stop but the close
                             recovered — check whether your broker filled you
    BEARISH_EVENT  warning   the pattern scanner confirmed a bearish event on
                             this stock within the last 3 sessions (sell
                             checklist) — cites the level and its target
    CHECKLIST_EXIT warning   the six-pillar sell checklist says EXIT (thesis and
                             weekly both broken, or three pillars against) while
                             the stop is still intact
    THESIS_BROKEN  warning   snapshot signal turned SELL, or the composite
                             score fell >= SCORE_DROP points since entry
    TIGHTEN_STOP   advice    >= 1R reached and the chandelier/breakeven level
                             sits above your current stop
    TIME_STOP      advice    held >= TIME_STOP_BARS sessions and still inside
                             +/-0.5R — dead money, capital has a cost
    HOLD           ok        nothing above applies

Everything here is advisory. Data is delayed and .CA Yahoo marks are often a
daily close, not a live quote — every payload carries the mark's provenance.
Service functions never raise; they return {"error": ...}.
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

#: Verdict -> severity, ordered from most to least severe.
SEVERITY: dict[str, str] = {
    "EXIT_STOP": "critical",
    "TRAIL_EXIT": "action",
    "TARGET2_HIT": "action",
    "TARGET1_HIT": "action",
    "PLAN_INVALID": "warning",
    "STOP_TOUCHED": "warning",
    "BEARISH_EVENT": "warning",
    "CHECKLIST_EXIT": "warning",
    "THESIS_BROKEN": "warning",
    "TIGHTEN_STOP": "advice",
    "TIME_STOP": "advice",
    "HOLD": "ok",
}
_RANK: dict[str, int] = {name: i for i, name in enumerate(SEVERITY)}
#: Severities that are pushed to Telegram (advice/ok stay in the app).
NOTIFY_SEVERITIES = ("critical", "action", "warning")
#: Inside this band of R a position counts as "going nowhere" for TIME_STOP.
_DEAD_MONEY_R = 0.5
_ATR_PERIOD = 14


# ── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _today() -> str:
    return datetime.now(CAIRO).strftime("%Y-%m-%d")


def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN guard


def _date_part(iso: Any) -> str:
    return str(iso or "")[:10]


def _atr(candles: list[dict], period: int = _ATR_PERIOD) -> Optional[float]:
    """Simple-average true range over the last ``period`` completed bars."""
    trs: list[float] = []
    prev_close: Optional[float] = None
    for c in candles:
        high, low, close = _num(c.get("high")), _num(c.get("low")), _num(c.get("close"))
        if high is None or low is None or close is None:
            continue
        tr = high - low
        if prev_close is not None:
            tr = max(tr, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        prev_close = close
    if len(trs) < max(3, period // 2):
        return None
    window = trs[-period:]
    return sum(window) / len(window)


def _candles_since(symbol: str, opened_date: str) -> tuple[list[dict], list[dict], Optional[str]]:
    """(all daily candles, candles strictly after the entry date, error)."""
    try:
        from app.services import history

        hist = history.get_history(symbol, "6mo", "1d")
    except Exception as exc:  # noqa: BLE001
        return [], [], str(exc)
    if not isinstance(hist, dict) or "error" in hist:
        return [], [], str((hist or {}).get("error") or "history unavailable")
    candles = [c for c in (hist.get("candles") or []) if isinstance(c, dict)]
    since = [c for c in candles if _date_part(c.get("time")) > opened_date]
    return candles, since, None


def _snapshot_at_or_before(symbol: str, date: str) -> Optional[dict]:
    rows = db.query(
        "SELECT date, score, signal, rating FROM snapshots "
        "WHERE symbol = ? AND timeframe = '1D' AND date <= ? AND score IS NOT NULL "
        "ORDER BY date DESC, id DESC LIMIT 1",
        (symbol, date),
    )
    return rows[0] if rows else None


def _latest_snapshot(symbol: str) -> Optional[dict]:
    rows = db.query(
        "SELECT date, score, signal, rating FROM snapshots "
        "WHERE symbol = ? AND timeframe = '1D' ORDER BY date DESC, id DESC LIMIT 1",
        (symbol,),
    )
    return rows[0] if rows else None


def _entry_score(pos: dict, opened_date: str) -> tuple[Optional[float], str]:
    """Score you bought on: the plan stored at open, else the nearest snapshot."""
    plan = pos.get("plan")
    if isinstance(plan, dict):
        for key in ("score", "stock_score", "composite_score"):
            found = _num(plan.get(key))
            if found is not None:
                return found, "plan"
        analysis = plan.get("analysis")
        if isinstance(analysis, dict):
            found = _num(analysis.get("stock_score"))
            if found is not None:
                return found, "plan"
    snap = _snapshot_at_or_before(pos["symbol"], opened_date)
    if snap and _num(snap.get("score")) is not None:
        return _num(snap["score"]), f"snapshot {snap.get('date')}"
    return None, "unknown"


def _is_sell_signal(signal: Any) -> bool:
    return "SELL" in str(signal or "").upper()


# ── core evaluation ──────────────────────────────────────────────────────────


def assess_position(
    pos: dict,
    mark: Optional[dict],
    candles: list[dict],
    since_entry: list[dict],
    latest_snap: Optional[dict],
    entry_score: Optional[float],
    entry_score_source: str,
    history_error: Optional[str] = None,
) -> dict:
    """Pure verdict logic for one position — no I/O, unit-testable.

    ``mark`` is {"price", "source", "as_of"} or None; ``candles`` are daily
    bars (oldest first) and ``since_entry`` the subset after the entry date.
    """
    symbol = str(pos.get("symbol") or "")
    entry = _num(pos.get("entry")) or 0.0
    stop = _num(pos.get("stop"))
    qty = _num(pos.get("qty")) or 0.0
    t1 = _num(pos.get("target1"))
    t2 = _num(pos.get("target2"))
    opened_date = _date_part(pos.get("opened_at"))
    price = _num(mark.get("price")) if isinstance(mark, dict) else None

    reasons: list[str] = []
    verdicts: list[str] = []
    # R is measured against the risk taken AT ENTRY (initial_stop), not the
    # current stop — otherwise raising the stop would silently inflate R.
    risk_stop = _num(pos.get("initial_stop"))
    if risk_stop is None:
        risk_stop = stop
    per_share_risk = (entry - risk_stop) if (risk_stop is not None and entry > risk_stop) else None

    # Targets are profit levels: one at/below entry is a data-entry error, and
    # comparing the mark against it would celebrate a loss ("target hit" on a
    # trade that is under water). Such targets are ignored and flagged.
    plan_faults: list[str] = []
    if t1 is not None and t1 <= entry:
        plan_faults.append(f"target 1 ({t1:.2f}) is at/below your entry {entry:.2f}")
        t1 = None
    if t2 is not None and t2 <= entry:
        plan_faults.append(f"target 2 ({t2:.2f}) is at/below your entry {entry:.2f}")
        t2 = None
    if t1 is not None and t2 is not None and t2 <= t1:
        plan_faults.append(f"target 2 ({t2:.2f}) is not above target 1 ({t1:.2f})")
        t2 = None

    r_now: Optional[float] = None
    unreal_pct: Optional[float] = None
    if price is not None and entry:
        unreal_pct = round((price - entry) / entry * 100.0, 2)
        if per_share_risk:
            r_now = round((price - entry) / per_share_risk, 2)

    # Post-entry path: highest close, today's low, ATR, sessions held.
    highest_close: Optional[float] = None
    peak_r: Optional[float] = None
    last_low: Optional[float] = None
    for c in since_entry:
        close = _num(c.get("close"))
        if close is not None and (highest_close is None or close > highest_close):
            highest_close = close
    if since_entry:
        last_low = _num(since_entry[-1].get("low"))
    if price is not None:
        highest_close = max(highest_close or price, price)
    if highest_close is not None and per_share_risk:
        peak_r = round((highest_close - entry) / per_share_risk, 2)
    atr = _atr(candles)
    bars_held = len(since_entry)
    try:
        days_held = (datetime.now(CAIRO).date() - datetime.fromisoformat(opened_date).date()).days
    except ValueError:
        days_held = None

    suggested_stop: Optional[float] = None

    if price is None:
        reasons.append("No price available for this symbol (Yahoo and snapshots both empty) "
                       "— verdict cannot be computed; check the position manually.")
        verdict = "HOLD"
    else:
        # 1. Hard stop.
        if stop is not None and price <= stop:
            verdicts.append("EXIT_STOP")
            reasons.append(
                f"Mark {price:.2f} is at/below your stop {stop:.2f}"
                + (f" ({r_now:+.2f}R)" if r_now is not None else "")
                + ". The plan you wrote at entry says exit — hoping is not a plan."
            )
        elif stop is not None and last_low is not None and last_low <= stop:
            verdicts.append("STOP_TOUCHED")
            reasons.append(
                f"Today's low {last_low:.2f} pierced the stop {stop:.2f} but the close "
                f"recovered to {price:.2f}. If you hold a resting stop order, confirm "
                "whether it filled; if not, decide now whether the level still holds."
            )

        # 2. Targets (validated above — invalid ones are None here).
        if plan_faults:
            verdicts.append("PLAN_INVALID")
            reasons.append(
                "Fix this record: " + "; ".join(plan_faults) + ". A target must sit above "
                "cost, so the Guardian ignored it rather than call a loss a 'target hit'. "
                "Use the row's Targets button to enter real profit levels."
            )
        if t2 is not None and price >= t2:
            verdicts.append("TARGET2_HIT")
            reasons.append(
                f"Mark {price:.2f} is at/above target 2 ({t2:.2f}). Book the profit or "
                "trail a tight stop — do not let a completed trade turn into a new one."
            )
        elif t1 is not None and price >= t1:
            verdicts.append("TARGET1_HIT")
            reasons.append(
                f"Mark {price:.2f} is at/above target 1 ({t1:.2f}). Consider taking a "
                "partial and moving the stop to breakeven so the rest is a free trade."
            )

        # 3. Trailing / tighten (only once the trade has proven itself with >= 1R).
        if per_share_risk and peak_r is not None and peak_r >= 1.0 and atr:
            chandelier = (highest_close or price) - settings.guardian_atr_mult * atr
            candidate = round(max(chandelier, entry), 2)  # never below breakeven once >= 1R
            if price <= chandelier and "EXIT_STOP" not in verdicts:
                verdicts.append("TRAIL_EXIT")
                reasons.append(
                    f"Price has given back more than {settings.guardian_atr_mult:g}xATR "
                    f"({atr:.2f}) from its post-entry high {highest_close:.2f} "
                    f"(peak {peak_r:+.2f}R, now {r_now:+.2f}R). The trailing exit says "
                    "the move is over; take what is left."
                )
            elif stop is not None and candidate > stop and candidate < price:
                verdicts.append("TIGHTEN_STOP")
                suggested_stop = candidate
                reasons.append(
                    f"Reached {peak_r:+.2f}R. Raise the stop from {stop:.2f} to about "
                    f"{candidate:.2f} (high {highest_close:.2f} minus "
                    f"{settings.guardian_atr_mult:g}xATR {atr:.2f}, floored at breakeven) — "
                    "a winner must not be allowed to become a loser."
                )

        # 4. Thesis check against the snapshot you bought on.
        if latest_snap:
            score_now = _num(latest_snap.get("score"))
            signal_now = latest_snap.get("signal")
            snap_date = latest_snap.get("date")
            broken: list[str] = []
            if _is_sell_signal(signal_now):
                broken.append(f"snapshot signal is {signal_now} ({snap_date})")
            if (score_now is not None and entry_score is not None
                    and entry_score - score_now >= settings.guardian_score_drop):
                broken.append(
                    f"composite score fell {entry_score:.0f} -> {score_now:.0f} "
                    f"since entry ({entry_score_source})"
                )
            if broken:
                verdicts.append("THESIS_BROKEN")
                reasons.append(
                    "The reason you bought no longer holds: " + "; ".join(broken)
                    + ". Re-read your entry note — if the setup is gone, so is the trade."
                )
            if entry_score is None:
                reasons.append(
                    "Score at entry is unknown (no trade plan stored and no snapshot on or before "
                    "the entry date), so the score-drop half of the thesis check cannot run; only "
                    "the SELL-signal half is active for this position."
                )
        else:
            reasons.append(
                f"No daily snapshot exists for {symbol} (it was outside the scanned universe), "
                "so the thesis check — score and signal since entry — could not run. Held "
                "stocks are now snapshotted at every close; this fills itself from the next session."
            )
        if per_share_risk is None:
            reasons.append(
                "Initial risk is unknown (the stop was recorded at/above cost), so R multiples "
                "and the trailing-stop logic are unavailable. Use the row's Stop button and enter "
                "the stop you actually had at entry to restore them."
            )

        # 5. Time stop.
        if (bars_held >= settings.guardian_time_stop_bars and r_now is not None
                and abs(r_now) < _DEAD_MONEY_R and not verdicts):
            verdicts.append("TIME_STOP")
            reasons.append(
                f"Held {bars_held} sessions and still {r_now:+.2f}R. Dead money has a "
                "cost: the capital could be in a setup that is actually moving."
            )

        verdict = min(verdicts, key=lambda v: _RANK[v]) if verdicts else "HOLD"
        if verdict == "HOLD":
            reasons.append(
                "Stop intact, no target reached, thesis unchanged — nothing to do. "
                "Doing nothing is a decision too."
            )

    if history_error:
        reasons.append(f"Daily history unavailable ({history_error}) — trailing-stop and "
                       "time-stop checks skipped.")

    return {
        "position_id": pos.get("id"),
        "symbol": symbol,
        "qty": qty,
        "entry": entry,
        "stop": stop,
        "target1": t1,
        "target2": t2,
        "opened_at": pos.get("opened_at"),
        "note": pos.get("note") or "",
        "mark": price,
        "mark_source": mark.get("source") if isinstance(mark, dict) else None,
        "mark_as_of": mark.get("as_of") if isinstance(mark, dict) else None,
        "r_now": r_now,
        "peak_r": peak_r,
        "unrealized_pct": unreal_pct,
        "bars_held": bars_held,
        "days_held": days_held,
        "atr14": round(atr, 4) if atr else None,
        "highest_close_since_entry": highest_close,
        "suggested_stop": suggested_stop,
        "score_at_entry": entry_score,
        "score_at_entry_source": entry_score_source,
        "score_now": _num(latest_snap.get("score")) if latest_snap else None,
        "signal_now": latest_snap.get("signal") if latest_snap else None,
        "snapshot_date": latest_snap.get("date") if latest_snap else None,
        "thesis_check": "ok" if latest_snap else "unavailable",
        "plan_faults": plan_faults,
        "verdict": verdict,
        "severity": SEVERITY[verdict],
        "all_verdicts": verdicts,
        "reasons": reasons,
    }


def apply_sell_checklist(row: dict, sc: Optional[dict]) -> dict:
    """Fold the sell checklist (``sell_checklist.compact``) into a Guardian row.

    Adds: a BEARISH_EVENT verdict when a confirmed bearish signal is fresh; a
    structure-anchored TIGHTEN_STOP (stop just under a tested support) when it
    beats the current stop; the partial-exit ladder on target hits; and the
    decision levels (exit_below / reduce_at / trail_stop_to) every verdict
    cites. Pure — no I/O — so it is unit-testable.
    """
    row["sell_checklist"] = sc
    if not sc:
        row.setdefault("exit_below", row.get("stop"))
        return row
    verdicts = list(row.get("all_verdicts") or [])
    reasons = list(row.get("reasons") or [])
    price, stop = row.get("mark"), row.get("stop")
    dl = sc.get("decision_levels") or {}
    hard_exit = "EXIT_STOP" in verdicts or "TRAIL_EXIT" in verdicts
    # 1. Fresh confirmed bearish signal on a stock you hold.
    fresh = sc.get("fresh_bearish") or []
    if fresh and price is not None and not hard_exit:
        f = fresh[0]
        lvl, tgt = f.get("neckline"), f.get("target")
        ago = f.get("sessions_ago")
        verdicts.append("BEARISH_EVENT")
        text = (f"Confirmed bearish signal {ago} session(s) ago: {f['label']}" if ago is not None
                else f"Confirmed bearish signal: {f['label']}")
        if lvl is not None:
            text += f" at {lvl:.2f}"
        if tgt is not None:
            text += f", measured target {tgt:.2f}"
        if tgt is not None and stop is not None and tgt < stop:
            text += ". That target sits below your stop — the chart expects the stop to be hit; leaving before it is beats waiting for it."
        else:
            text += ". Tighten the stop under the nearest tested support rather than hoping."
        reasons.append(text)
    # 1b. The checklist itself says exit while the stop is intact: say so as a
    #     verdict, or the badge would read HOLD next to an EXIT checklist.
    if sc.get("verdict") == "exit" and not hard_exit and "CHECKLIST_EXIT" not in verdicts:
        verdicts.append("CHECKLIST_EXIT")
        reasons.append("Sell checklist says EXIT: " + str(sc.get("headline") or "").replace("Exit: ", "", 1))
    # 2. Structure stop: a tested support between the stop and the price.
    trail = dl.get("trail_stop_to")
    if (trail is not None and stop is not None and price is not None and trail > stop
            and trail < price and not hard_exit):
        cur = row.get("suggested_stop")
        if cur is None or trail > cur:
            row["suggested_stop"] = round(float(trail), 2)
        if "TIGHTEN_STOP" not in verdicts:
            verdicts.append("TIGHTEN_STOP")
        reasons.append(f"Structure stop: raise the stop from {stop:.2f} to {trail:.2f}, "
                       f"{dl.get('trail_reason') or 'under tested support'} — a level the market has "
                       "respected beats an arbitrary distance.")
    # 3. Partial-exit ladder when a target is reached.
    ladder = dl.get("ladder") or []
    if ladder and ("TARGET1_HIT" in verdicts or "TARGET2_HIT" in verdicts):
        steps = []
        for s in ladder:
            if s.get("step") == "reduce_now":
                steps.append(f"sell {s['pct']}% ({s['qty']} shares) at market ~{s['at']:.2f}")
            elif s.get("step") == "stop_to":
                steps.append(f"move the stop to {s['level']:.2f} ({s['why']})")
            elif s.get("step") == "final":
                steps.append(f"let the rest run to {s['at']:.2f} ({s['why']})")
        if steps:
            reasons.append("Exit ladder: " + "; ".join(steps) + ".")
    verdict = min(verdicts, key=lambda v: _RANK[v]) if verdicts else "HOLD"
    if verdict != "HOLD":
        reasons = [r for r in reasons if not str(r).startswith("Stop intact, no target reached")]
    row["all_verdicts"] = verdicts
    row["verdict"] = verdict
    row["severity"] = SEVERITY[verdict]
    row["reasons"] = reasons
    row["exit_below"] = dl.get("exit_below") if dl.get("exit_below") is not None else stop
    row["reduce_at"] = dl.get("reduce_at")
    row["trail_stop_to"] = trail
    row["bearish_trigger"] = dl.get("bearish_trigger")
    return row


# ── persistence / delivery ───────────────────────────────────────────────────


def _already_notified(position_id: Any, verdict: str, date: str) -> bool:
    rows = db.query(
        "SELECT 1 FROM guardian_verdicts WHERE position_id = ? AND verdict = ? "
        "AND date = ? AND notified = 1 LIMIT 1",
        (position_id, verdict, date),
    )
    return bool(rows)


def _persist(row: dict, date: str, notified: bool) -> None:
    db.execute(
        "INSERT OR REPLACE INTO guardian_verdicts "
        "(date, position_id, symbol, verdict, severity, mark, r_now, suggested_stop, "
        " reasons_json, notified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            date, row.get("position_id"), row.get("symbol"), row.get("verdict"),
            row.get("severity"), row.get("mark"), row.get("r_now"), row.get("suggested_stop"),
            json.dumps(row.get("reasons") or []), 1 if notified else 0, _now_iso(),
        ),
    )


def _telegram_text(row: dict) -> str:
    head = f"[Guardian] {row['symbol']} #{row.get('position_id')}: {row['verdict']}"
    parts = [head]
    if row.get("mark") is not None:
        parts.append(
            f"mark {row['mark']:.2f} ({row.get('mark_source') or 'unknown source'})"
            + (f" · {row['r_now']:+.2f}R" if row.get("r_now") is not None else "")
        )
    if row.get("suggested_stop") is not None:
        parts.append(f"suggested stop {row['suggested_stop']:.2f}")
    levels_bits = []
    if row.get("exit_below") is not None:
        levels_bits.append(f"exit below {row['exit_below']:.2f}")
    if row.get("reduce_at") is not None:
        levels_bits.append(f"reduce at {row['reduce_at']:.2f}")
    if row.get("trail_stop_to") is not None:
        levels_bits.append(f"trail stop to {row['trail_stop_to']:.2f}")
    if levels_bits:
        parts.append("Levels: " + " · ".join(levels_bits))
    if row.get("reasons"):
        parts.append(str(row["reasons"][0]))
    if row.get("note"):
        parts.append(f'Your entry note: "{str(row["note"])[:200]}"')
    return "\n".join(parts)


# ── public API ───────────────────────────────────────────────────────────────


def evaluate(persist: bool = False, notify: bool = False) -> dict:
    """Assess every open position. Returns {"verdicts": [...], "summary": {...}}.

    ``persist`` stores one row per position per Cairo date (latest wins);
    ``notify`` pushes critical/action/warning verdicts to Telegram once per
    (position, verdict, date). Never raises.
    """
    try:
        from app.services import portfolio

        positions = portfolio.list_positions("open")
        if not positions:
            return {
                "verdicts": [], "summary": {"open": 0, "by_severity": {}, "needs_action": 0,
                                            "notified": 0},
                "as_of": _now_iso(), "date": _today(),
            }
        symbols = sorted({str(p["symbol"]) for p in positions})
        try:
            marks = portfolio._mark_prices(symbols)
        except Exception as exc:  # noqa: BLE001
            logger.warning("guardian: mark prices failed: %s", exc)
            marks = {}

        history_cache: dict[str, tuple[list[dict], list[dict], Optional[str]]] = {}
        snapshot_cache: dict[str, Optional[dict]] = {}
        today = _today()
        out: list[dict] = []
        notified_count = 0
        for pos in positions:
            symbol = str(pos["symbol"])
            opened_date = _date_part(pos.get("opened_at"))
            cache_key = f"{symbol}|{opened_date}"
            if cache_key not in history_cache:
                history_cache[cache_key] = _candles_since(symbol, opened_date)
            candles, since, hist_err = history_cache[cache_key]
            if symbol not in snapshot_cache:
                snapshot_cache[symbol] = _latest_snapshot(symbol)
            entry_score, source = _entry_score(pos, opened_date)
            row = assess_position(
                pos, marks.get(symbol), candles, since,
                snapshot_cache[symbol], entry_score, source, hist_err,
            )
            # Sell checklist: bearish events, structure stop, exit ladder, levels.
            try:
                from app.services import sell_checklist as SC

                sc = SC.sell_checklist(symbol, position=pos, mark=row.get("mark"))
                row = apply_sell_checklist(row, SC.compact(sc))
            except Exception as exc:  # noqa: BLE001
                logger.warning("guardian: sell checklist failed for %s: %s", symbol, exc)
                row = apply_sell_checklist(row, None)
            sent = False
            if notify and row["severity"] in NOTIFY_SEVERITIES:
                if not _already_notified(row["position_id"], row["verdict"], today):
                    try:
                        from app.services.alerts import send_telegram

                        sent = send_telegram(_telegram_text(row))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("guardian: telegram failed: %s", exc)
                    if sent:
                        notified_count += 1
                else:
                    sent = True  # keep the flag so a re-run does not re-ping
            row["notified"] = sent
            if persist:
                try:
                    _persist(row, today, sent)
                except Exception as exc:  # noqa: BLE001
                    logger.error("guardian: persist failed for %s: %s", symbol, exc)
            out.append(row)

        out.sort(key=lambda r: (_RANK[r["verdict"]], r["symbol"]))
        by_sev: dict[str, int] = {}
        for row in out:
            by_sev[row["severity"]] = by_sev.get(row["severity"], 0) + 1
        return {
            "verdicts": out,
            "summary": {
                "open": len(out),
                "by_severity": by_sev,
                "needs_action": sum(1 for r in out if r["severity"] in NOTIFY_SEVERITIES),
                "notified": notified_count,
            },
            "thresholds": {
                "atr_mult": settings.guardian_atr_mult,
                "score_drop": settings.guardian_score_drop,
                "time_stop_bars": settings.guardian_time_stop_bars,
            },
            "basis": (
                "Advisory only. Marks may be daily closes (see mark_source); trailing "
                "levels use 14-day ATR on Yahoo daily candles; thesis checks compare "
                "the latest post-close snapshot with the score at entry. Each row also "
                "carries the six-pillar sell checklist: exit_below / reduce_at / "
                "trail_stop_to are the levels the verdict cites."
            ),
            "date": today,
            "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def history(position_id: Optional[int] = None, limit: int = 60) -> list[dict]:
    """Stored verdict rows, newest first (optionally for one position)."""
    try:
        limit = max(1, min(int(limit), 500))
        if position_id is not None:
            rows = db.query(
                "SELECT * FROM guardian_verdicts WHERE position_id = ? "
                "ORDER BY date DESC, id DESC LIMIT ?",
                (position_id, limit),
            )
        else:
            rows = db.query(
                "SELECT * FROM guardian_verdicts ORDER BY date DESC, id DESC LIMIT ?",
                (limit,),
            )
        for row in rows:
            try:
                row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
            except (TypeError, ValueError):
                row["reasons"] = []
        return rows
    except Exception as exc:  # noqa: BLE001
        logger.error("guardian.history failed: %s", exc)
        return []
