"""Weekly review — the loop that turns a journal into a better trader.

Everything else in the app answers "what to buy / hold / sell today". This
module answers, once a week, "how did the decisions go, and whose fault was
it": the trades closed and opened this week, your realised R per entry rule
next to what the same rule did in the five-year replay ("you vs system"),
whether you followed the plan, whether you acted on the Guardian, how much
heat you carried each session, and the equity path against EGX30. A
free-text lesson per week is stored alongside (``review_notes``), and the
Saturday maintenance job sends the headline as one Telegram digest.

Trading weeks run Sunday–Thursday (Cairo). ``compute(week)`` accepts any date
inside the week; without one it reviews the week containing the last
completed session (so a Friday/Saturday review looks at the week just ended).

Never raises; returns {"error": ...} on failure.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.config import settings

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

#: Entry rules / scanners a closed trade may be attributed to (live hits on the entry session).
ATTRIBUTABLE_PREFIXES = ("pattern_", "checklist_")   # excluded — not entry rules
#: A hit up to this many sessions before the fill still counts as the trade's reason.
ATTRIBUTION_LOOKBACK_DAYS = 4


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(s: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ── week arithmetic (pure) ───────────────────────────────────────────────────


def week_bounds(ref: Optional[date] = None) -> tuple[date, date]:
    """(Sunday, Thursday) of the EGX trading week containing ``ref``.

    A Friday or Saturday belongs to the week that just ended, so a weekend
    review reads the finished week rather than an empty upcoming one.
    """
    if ref is None:
        try:
            from app import calendar_egx

            ref = calendar_egx.last_completed_session()
        except Exception:  # noqa: BLE001
            ref = datetime.now(CAIRO).date()
    wd = ref.weekday()                 # Mon=0 … Sun=6
    if wd in (4, 5):                   # Fri / Sat → previous Sunday
        sunday = ref - timedelta(days=(wd - 6) % 7)
    else:
        sunday = ref - timedelta(days=(wd + 1) % 7)
    return sunday, sunday + timedelta(days=4)


def _sessions(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        try:
            from app import calendar_egx

            if calendar_egx.is_trading_day(d):
                out.append(d)
        except Exception:  # noqa: BLE001
            if d.weekday() not in (4, 5):
                out.append(d)
        d += timedelta(days=1)
    return out


# ── attribution ──────────────────────────────────────────────────────────────


def attribute(symbol: str, opened_at: Any) -> list[str]:
    """Entry rules / scanners that fired on the symbol on (or up to 4 days before)
    the fill date — live hits only. Patterns and checklist verdicts are context,
    not the entry rule, so they are left out."""
    d0 = _d(opened_at)
    if not d0:
        return []
    try:
        rows = db.query(
            "SELECT DISTINCT scanner, date FROM scanner_hits WHERE symbol = ? AND COALESCE(source,'live') = 'live' "
            "AND date <= ? AND date >= ? ORDER BY date DESC",
            (str(symbol).upper(), d0.isoformat(), (d0 - timedelta(days=ATTRIBUTION_LOOKBACK_DAYS)).isoformat()),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("attribute(%s) failed: %s", symbol, exc)
        return []
    seen: list[str] = []
    for r in rows:
        name = str(r["scanner"])
        if name.startswith(ATTRIBUTABLE_PREFIXES):
            continue
        if name not in seen:
            seen.append(name)
    return seen


def _system_expectation() -> dict[str, dict]:
    """Rule -> {avg_r, win_rate, n, verdict} from the Proven-edge table (rules traded
    with Guardian exits) — the yardstick a live rule's realised R is compared with."""
    out: dict[str, dict] = {}
    try:
        for r in db.query("SELECT name, n, hit_rate, edge_metric, verdict FROM proven_edge WHERE kind = 'rule'"):
            out[str(r["name"])] = {"avg_r": r.get("edge_metric"), "win_rate": r.get("hit_rate"),
                                   "n": r.get("n"), "verdict": r.get("verdict")}
        for r in db.query("SELECT name, n, hit_rate, edge_metric, verdict FROM proven_edge WHERE kind = 'scanner'"):
            out.setdefault(str(r["name"]), {"avg_r": None, "win_rate": r.get("hit_rate"), "n": r.get("n"),
                                            "verdict": r.get("verdict"), "excess_10d": r.get("edge_metric")})
    except Exception as exc:  # noqa: BLE001
        logger.warning("system expectation unavailable: %s", exc)
    return out


def _trade_row(pos: dict) -> dict:
    """One closed position as the review shows it (net R, held sessions, attribution)."""
    from app.services import portfolio as P

    entry = _num(pos.get("entry")) or 0.0
    qty = _num(pos.get("qty")) or 0.0
    exit_price = _num(pos.get("exit_price"))
    fees = _num(pos.get("fees"))
    gross: Optional[float] = None
    net: Optional[float] = None
    if exit_price is not None:
        gross = (exit_price - entry) * qty
        if fees is None:
            fees = P._round_trip_fees(entry, exit_price, qty)
        net = gross - fees
    risk = P._risk_per_share(pos)
    r_net = round((net / qty) / risk, 2) if (net is not None and qty and risk) else None
    d_open, d_close = _d(pos.get("opened_at")), _d(pos.get("closed_at"))
    held = (d_close - d_open).days if d_open and d_close else None
    stop_now, stop0 = _num(pos.get("stop")), _num(pos.get("initial_stop"))
    t1 = _num(pos.get("target1"))
    # How did it end? By the plan (stop or target), or by hand?
    how = "unknown"
    if exit_price is not None:
        if stop_now is not None and exit_price <= stop_now * 1.002:
            how = "stop"
        elif t1 is not None and exit_price >= t1 * 0.998:
            how = "target"
        else:
            how = "discretionary"
    return {
        "id": pos.get("id"), "symbol": pos.get("symbol"), "entry": entry, "exit": exit_price, "qty": qty,
        "opened_at": str(pos.get("opened_at") or "")[:10], "closed_at": str(pos.get("closed_at") or "")[:10],
        "held_days": held, "pnl_net": round(net, 2) if net is not None else None, "r_net": r_net,
        "plan_followed": pos.get("plan_followed"), "exit_how": how,
        "stop_lowered": bool(stop_now is not None and stop0 is not None and stop_now < stop0 - 1e-9),
        "note": pos.get("note") or "", "rules": attribute(str(pos.get("symbol") or ""), pos.get("opened_at")),
    }


def you_vs_system(closed_rows: list[dict]) -> dict:
    """Realised R per attributed rule against the replayed expectation."""
    expect = _system_expectation()
    groups: dict[str, list[dict]] = {}
    unattributed: list[dict] = []
    for t in closed_rows:
        if t.get("r_net") is None:
            continue
        if not t["rules"]:
            unattributed.append(t)
            continue
        for rule in t["rules"]:
            groups.setdefault(rule, []).append(t)
    rows = []
    for rule, ts in groups.items():
        rs = [t["r_net"] for t in ts]
        wins = sum(1 for r in rs if r > 0)
        exp = expect.get(rule) or {}
        avg_r = round(sum(rs) / len(rs), 2)
        gap = round(avg_r - exp["avg_r"], 2) if exp.get("avg_r") is not None else None
        rows.append({
            "rule": rule, "n": len(rs), "avg_r": avg_r, "win_rate": round(wins / len(rs) * 100.0, 1),
            "system_avg_r": exp.get("avg_r"), "system_win_rate": exp.get("win_rate"), "system_n": exp.get("n"),
            "system_verdict": exp.get("verdict"), "gap_r": gap,
            "read": (
                "too few trades to judge — keep taking the rule's signals" if len(rs) < 5 else
                "you are extracting more than the rule offers — check that exits are not luck" if gap is not None and gap > 0.3 else
                "you are giving back the rule's edge — compare your exits with the Guardian's" if gap is not None and gap < -0.3 else
                "in line with the system" if gap is not None else "no system figure for this rule yet"
            ),
            "symbols": [t["symbol"] for t in ts][:8],
        })
    rows.sort(key=lambda r: (-r["n"], r["rule"]))
    return {"rows": rows, "unattributed": [{"symbol": t["symbol"], "r_net": t["r_net"], "closed_at": t["closed_at"]}
                                          for t in unattributed],
            "basis": ("A closed trade is attributed to the live entry rules / scanners that fired on its symbol on the "
                      "fill session (or up to 4 days before). System = the same rule traded universe-wide with Guardian "
                      "exits over three years (Proven edge). Gap = your average R minus the system's; under five trades "
                      "the gap is noise.")}


def discipline(closed_rows: list[dict]) -> dict:
    followed = [t["r_net"] for t in closed_rows if t.get("plan_followed") in (1, True) and t.get("r_net") is not None]
    deviated = [t["r_net"] for t in closed_rows if t.get("plan_followed") in (0, False) and t.get("r_net") is not None]
    unanswered = sum(1 for t in closed_rows if t.get("plan_followed") is None)
    lowered = [t["symbol"] for t in closed_rows if t.get("stop_lowered")]
    discretionary = [t["symbol"] for t in closed_rows if t.get("exit_how") == "discretionary"]
    by_how = {}
    for t in closed_rows:
        by_how[t["exit_how"]] = by_how.get(t["exit_how"], 0) + 1
    return {
        "followed_n": len(followed), "deviated_n": len(deviated), "unanswered_n": unanswered,
        "avg_r_followed": round(sum(followed) / len(followed), 2) if followed else None,
        "avg_r_deviated": round(sum(deviated) / len(deviated), 2) if deviated else None,
        "stops_lowered": lowered, "discretionary_exits": discretionary, "exits_by_how": by_how,
        "read": (
            "Deviating from the plan cost you: average R when you followed it is higher." if followed and deviated
            and sum(followed) / len(followed) > sum(deviated) / len(deviated) else
            "Your deviations have paid so far — be suspicious; that is usually luck at this sample size." if followed and deviated else
            "Answer the 'did you follow the plan?' question at every close — it is the cheapest discipline meter there is."
            if unanswered else "Not enough closed trades to judge discipline yet."
        ),
    }


def guardian_week(start: date, end: date) -> dict:
    """Non-HOLD verdicts issued in the week and whether the ledger shows an action after each."""
    try:
        rows = db.query(
            "SELECT g.*, p.status, p.stop AS stop_now, p.closed_at, p.initial_stop FROM guardian_verdicts g "
            "LEFT JOIN positions p ON p.id = g.position_id WHERE g.date >= ? AND g.date <= ? AND g.verdict != 'HOLD' "
            "ORDER BY g.date, g.position_id", (start.isoformat(), end.isoformat()),
        )
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "error": str(exc)}
    out = []
    for g in rows:
        pid = g.get("position_id")
        acted, how = False, None
        try:
            fills = db.query("SELECT ts, side, qty FROM position_fills WHERE position_id = ? AND side = 'sell' "
                             "AND substr(ts,1,10) >= ? ORDER BY ts", (pid, g["date"]))
        except Exception:  # noqa: BLE001
            fills = []
        if g.get("status") == "closed" and str(g.get("closed_at") or "")[:10] >= str(g["date"]):
            acted, how = True, "closed"
        elif fills:
            acted, how = True, f"sold {sum(_num(f.get('qty')) or 0 for f in fills):g} shares"
        else:
            sug, stop_now = _num(g.get("suggested_stop")), _num(g.get("stop_now"))
            if g.get("verdict") == "TIGHTEN_STOP" and sug is not None and stop_now is not None and stop_now >= sug - 1e-9:
                acted, how = True, "stop raised"
        try:
            reasons = json.loads(g.get("reasons_json") or "[]")
        except (TypeError, ValueError):
            reasons = []
        out.append({"date": g["date"], "symbol": g["symbol"], "position_id": pid, "verdict": g["verdict"],
                    "severity": g.get("severity"), "r_now": g.get("r_now"), "suggested_stop": g.get("suggested_stop"),
                    "acted": acted, "how": how, "reason": (reasons[0] if reasons else "")[:200]})
    # Collapse repeats: keep the first day each (position, verdict) appeared plus its latest action state.
    seen: dict[tuple, dict] = {}
    for r in out:
        key = (r["position_id"], r["verdict"])
        if key not in seen:
            seen[key] = dict(r, repeats=1)
        else:
            seen[key]["repeats"] += 1
            if r["acted"]:
                seen[key]["acted"], seen[key]["how"] = True, r["how"]
    rows2 = list(seen.values())
    actionable = [r for r in rows2 if r["severity"] in ("critical", "action")]
    ignored = [r for r in actionable if not r["acted"]]
    return {"rows": rows2, "actionable": len(actionable), "ignored": [f"{r['symbol']} {r['verdict']}" for r in ignored],
            "read": (f"{len(ignored)} actionable Guardian verdict(s) had no action in the ledger — either record what you "
                     "did (Stop / Sell / Close) or write down why you overruled it." if ignored else
                     "Every actionable verdict this week has a matching ledger action." if actionable else
                     "No actionable Guardian verdicts this week.")}


def heat_series(start: date, end: date) -> list[dict]:
    """Open heat per session of the week: Σ (entry − stop) × qty over the positions open that
    day, as % of ACCOUNT_SIZE. Uses each position's CURRENT stop (stop history is not
    journaled), so past days are an approximation and say so."""
    account = float(settings.account_size) or 0.0
    try:
        pos = db.query("SELECT symbol, qty, entry, stop, opened_at, closed_at, status FROM positions")
    except Exception:  # noqa: BLE001
        pos = []
    out = []
    for d in _sessions(start, end):
        risk = 0.0
        n_open = 0
        for p in pos:
            o, c = _d(p.get("opened_at")), _d(p.get("closed_at"))
            if not o or o > d or (c and c < d):
                continue
            n_open += 1
            e, s, q = _num(p.get("entry")) or 0.0, _num(p.get("stop")), _num(p.get("qty")) or 0.0
            if s is not None:
                risk += max(0.0, e - s) * q
        out.append({"date": d.isoformat(), "open_positions": n_open, "risk_egp": round(risk, 0),
                    "heat_pct": round(risk / account * 100.0, 2) if account else None})
    return out


# ── notes ────────────────────────────────────────────────────────────────────


def get_note(week_start: str) -> dict:
    try:
        rows = db.query("SELECT * FROM review_notes WHERE week_start = ?", (week_start,))
        return dict(rows[0]) if rows else {"week_start": week_start, "text": "", "updated_at": None}
    except Exception as exc:  # noqa: BLE001
        return {"week_start": week_start, "text": "", "error": str(exc)}


def save_note(week_start: str, text: str) -> dict:
    """Store (or clear) the week's lessons. ``ok`` only after the row is written."""
    try:
        ws = _d(week_start)
        if not ws:
            return {"error": "week_start must be a YYYY-MM-DD date"}
        sunday, _ = week_bounds(ws)
        text = str(text or "").strip()
        db.execute("INSERT OR REPLACE INTO review_notes (week_start, text, updated_at) VALUES (?, ?, ?)",
                   (sunday.isoformat(), text, _now_iso()))
        rows = db.query("SELECT * FROM review_notes WHERE week_start = ?", (sunday.isoformat(),))
        if not rows:
            return {"error": "note was not stored"}
        return {"ok": True, **dict(rows[0])}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def notes(limit: int = 12) -> list[dict]:
    try:
        return db.query("SELECT * FROM review_notes WHERE text != '' ORDER BY week_start DESC LIMIT ?", (limit,))
    except Exception:  # noqa: BLE001
        return []


# ── the review ───────────────────────────────────────────────────────────────


def _performance() -> dict:
    """Portfolio performance (marks + benchmark); isolated so tests can stub the network."""
    from app.services import portfolio

    return portfolio.performance()


def compute(week: Optional[str] = None) -> dict:
    """The weekly review for the week containing ``week`` (any date; default = the
    week of the last completed session). Never raises."""
    try:
        from app.services import portfolio as P

        ref = _d(week) if week else None
        start, end = week_bounds(ref)
        s, e = start.isoformat(), end.isoformat()
        closed_all = [_trade_row(p) for p in P.list_positions("closed") if p.get("exit_price") is not None]
        closed_week = [t for t in closed_all if s <= t["closed_at"] <= e]
        opened_week = [{"id": p.get("id"), "symbol": p.get("symbol"), "entry": _num(p.get("entry")),
                        "stop": _num(p.get("stop")), "qty": _num(p.get("qty")), "opened_at": str(p.get("opened_at") or "")[:10],
                        "status": p.get("status"), "note": p.get("note") or "",
                        "rules": attribute(str(p.get("symbol") or ""), p.get("opened_at"))}
                       for p in P.list_positions("all") if s <= str(p.get("opened_at") or "")[:10] <= e]
        try:
            perf = _performance()
        except Exception as exc:  # noqa: BLE001
            perf = {"error": str(exc)}
        perf_ok = isinstance(perf, dict) and "error" not in perf
        week_pnl = round(sum(t["pnl_net"] or 0.0 for t in closed_week), 2)
        week_rs = [t["r_net"] for t in closed_week if t["r_net"] is not None]
        heat = heat_series(start, end)
        gw = guardian_week(start, end)
        vs = you_vs_system(closed_all)
        disc = discipline(closed_all)
        try:
            from app.services import regime

            reg = regime.current()
        except Exception:  # noqa: BLE001
            reg = {}
        # Headline: one paragraph a trader can read on a phone.
        parts = [f"Week {s} → {e}: {len(closed_week)} trade{'s' if len(closed_week) != 1 else ''} closed"
                 + (f" for {week_pnl:+,.0f} EGP net" if closed_week else "")
                 + (f" ({sum(week_rs) / len(week_rs):+.2f}R average)" if week_rs else "")
                 + f", {len(opened_week)} opened."]
        if perf_ok:
            parts.append(f"Open heat now {perf.get('open_heat_pct') or 0:.1f}% across {perf.get('open_count', 0)} position(s); "
                         f"unrealised {perf.get('unrealized_pnl') or 0:+,.0f} EGP.")
            bm = perf.get("benchmark") or {}
            if isinstance(bm, dict) and bm.get("index_change_pct") is not None:
                parts.append(f"Since your first trade ({bm.get('since')}): EGX30 {bm['index_change_pct']:+.2f}% vs your "
                             f"net PnL {bm.get('portfolio_net_pnl', 0):+,.0f} EGP"
                             + (f" ({bm['portfolio_return_pct_of_account']:+.2f}% of the account)."
                                if bm.get("portfolio_return_pct_of_account") is not None else "."))
        if gw.get("ignored"):
            parts.append(f"Guardian verdicts without a ledger action: {', '.join(gw['ignored'][:4])}.")
        worst = min((r for r in vs["rows"] if r.get("gap_r") is not None and r["n"] >= 5), key=lambda r: r["gap_r"], default=None)
        if worst and worst["gap_r"] < -0.3:
            parts.append(f"Biggest leak: {worst['rule']} — you average {worst['avg_r']:+.2f}R where the system makes "
                         f"{worst['system_avg_r']:+.2f}R.")
        if reg.get("state"):
            parts.append(f"Tape: {reg['state']}.")
        return {
            "week": {"start": s, "end": e, "label": f"{s} → {e}", "sessions": len(heat),
                     "prev": (start - timedelta(days=7)).isoformat(), "next": (start + timedelta(days=7)).isoformat()},
            "headline": " ".join(parts),
            "closed": closed_week, "opened": opened_week,
            "week_pnl_net": week_pnl, "week_avg_r": round(sum(week_rs) / len(week_rs), 2) if week_rs else None,
            "you_vs_system": vs, "discipline": disc, "guardian": gw, "heat": heat,
            "performance": ({k: perf.get(k) for k in ("open_count", "closed_count", "realized_pnl", "unrealized_pnl",
                                                       "win_rate", "avg_r", "open_heat_pct", "benchmark",
                                                       "benchmark_note")} if perf_ok else perf),
            "regime": {"state": reg.get("state"), "text": reg.get("text")} if isinstance(reg, dict) else None,
            "note": get_note(s), "recent_notes": notes(6),
            "closed_all_count": len(closed_all),
            "basis": ("Trading weeks run Sunday to Thursday. Trade R is net of fees against the INITIAL stop. "
                      "Heat per session uses each position's current stop (stop history is not journaled). "
                      "Attribution = live entry-rule hits on the fill session or the 4 days before."),
            "as_of": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("review.compute failed")
        return {"error": str(exc)}


def digest_text(rev: dict) -> str:
    """The weekly review as one Telegram message (headline + the three things to act on)."""
    if not isinstance(rev, dict) or "error" in rev:
        return f"[EGX weekly review] unavailable: {(rev or {}).get('error', 'unknown')}"
    lines = [f"[EGX weekly review] {rev['week']['label']}", rev.get("headline", "")]
    d = rev.get("discipline") or {}
    if d.get("followed_n") or d.get("deviated_n"):
        lines.append(f"Plan followed: {d.get('followed_n', 0)}× ({d.get('avg_r_followed')}R) · deviated: "
                     f"{d.get('deviated_n', 0)}× ({d.get('avg_r_deviated')}R)")
    for r in (rev.get("you_vs_system") or {}).get("rows", [])[:3]:
        lines.append(f"{r['rule']}: you {r['avg_r']:+.2f}R over {r['n']}"
                     + (f" vs system {r['system_avg_r']:+.2f}R" if r.get("system_avg_r") is not None else ""))
    g = rev.get("guardian") or {}
    if g.get("ignored"):
        lines.append("Unacted Guardian: " + ", ".join(g["ignored"][:4]))
    note = (rev.get("note") or {}).get("text") or ""
    if note:
        lines.append("Lesson: " + note[:200])
    lines.append("Open /review.html to write this week's lesson.")
    return "\n".join(x for x in lines if x)


def digest(send: bool = True, week: Optional[str] = None) -> dict:
    """Compute the review and (optionally) push it to Telegram once. Never raises."""
    try:
        rev = compute(week)
        text = digest_text(rev)
        sent = False
        if send:
            from app.services.alerts import send_telegram

            sent = bool(send_telegram(text))
        return {"sent": sent, "text": text, "week": (rev.get("week") or {}).get("label") if isinstance(rev, dict) else None,
                "error": rev.get("error") if isinstance(rev, dict) else None}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "sent": False}
