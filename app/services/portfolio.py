"""Position sizing, position lifecycle (open/close), and portfolio performance."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db
from app.config import settings
from app.symbols import tv_to_yahoo

from tradingview_mcp.core.services.yahoo_finance_service import get_prices_bulk

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_trip_fees(entry: float, exit_price: float, qty: float) -> float:
    """All-in EGX transaction costs for both legs (settings.fee_pct_per_side)."""
    rate = settings.fee_pct_per_side / 100.0
    return round((entry * qty + exit_price * qty) * rate, 2)


# ── sizing ───────────────────────────────────────────────────────────────────


def size_position(
    account: float,
    risk_pct: float,
    entry: float,
    stop: float,
    symbol: Optional[str] = None,
) -> dict:
    """Fixed-fractional position size for a long trade.

    When ``symbol`` is given, the suggested size is checked against the
    stock's 20-day median traded value — on EGX, exit liquidity is the real
    risk, and a position that is a large slice of a day's turnover cannot be
    stopped out anywhere near the planned level.

    Returns {"shares", "risk_amount", "position_cost", "risk_reward_note"}
    or {"error": ...} on invalid input.
    """
    try:
        account = float(account)
        risk_pct = float(risk_pct)
        entry = float(entry)
        stop = float(stop)
        if account <= 0:
            return {"error": "account must be > 0"}
        if entry <= 0:
            return {"error": "entry must be > 0"}
        if risk_pct <= 0:
            return {"error": "risk_pct must be > 0"}
        if stop >= entry:
            return {"error": "stop must be below entry for a long position"}
        if stop < 0:
            return {"error": "stop cannot be negative"}

        risk_amount = account * risk_pct / 100.0
        per_share_risk = entry - stop
        shares = int(risk_amount // per_share_risk)
        capped_by_capital = False
        if shares * entry > account:
            shares = int(account // entry)
            capped_by_capital = True
        position_cost = round(shares * entry, 2)

        two_r_target = entry + 2 * per_share_risk
        est_fees = _round_trip_fees(entry, entry, max(shares, 0) or 0)
        notes = [
            f"Risking {risk_amount:,.0f} EGP ({risk_pct:.2f}% of {account:,.0f}) "
            f"at {per_share_risk:.2f} EGP/share risk.",
            f"A 2R target sits at {two_r_target:.2f}.",
            f"Estimated round-trip fees ~{est_fees:,.0f} EGP "
            f"({settings.fee_pct_per_side}%/side) — a stop-out costs risk + fees.",
        ]
        if capped_by_capital:
            notes.append("Size capped by available capital, so realized risk is below target.")
        if risk_pct > 2:
            notes.append(f"WARNING: risk_pct {risk_pct:.2f}% exceeds the 2% cap guideline.")
        if shares <= 0:
            notes.append("Risk budget too small for even 1 share at this stop distance.")

        liquidity_egp: Optional[float] = None
        adv_pct: Optional[float] = None
        if symbol:
            from app.services.market import median_daily_value

            liquidity_egp = median_daily_value(symbol)
            if liquidity_egp and liquidity_egp > 0 and position_cost > 0:
                adv_pct = round(position_cost / liquidity_egp * 100.0, 1)
                if adv_pct > 15:
                    notes.append(
                        f"LIQUIDITY WARNING: this position is ~{adv_pct:.0f}% of "
                        f"{symbol}'s 20-day median daily value ({liquidity_egp:,.0f} EGP) "
                        "— entering and exiting will move the price; cap at ~15%."
                    )
                else:
                    notes.append(
                        f"Position is ~{adv_pct:.1f}% of {symbol}'s 20-day median "
                        f"daily value ({liquidity_egp:,.0f} EGP)."
                    )
            elif liquidity_egp is None:
                notes.append(
                    f"Liquidity unknown for {symbol} (snapshots history too thin "
                    "to compute 20-day traded value)."
                )

        return {
            "shares": shares,
            "risk_amount": round(risk_amount, 2),
            "position_cost": position_cost,
            "liquidity_egp": liquidity_egp,
            "position_pct_of_adv": adv_pct,
            "risk_reward_note": " ".join(notes),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── lifecycle ────────────────────────────────────────────────────────────────


#: Portfolio-level cap on total risk-at-stops as % of account — the user
#: guide's own "take something off above ~6%" rule, enforced as a mechanism.
MAX_OPEN_HEAT_PCT = 6.0
#: Per-trade risk % above which a warning is attached (not a block).
WARN_TRADE_RISK_PCT = 2.0


def _sector_of(symbol: str) -> Optional[str]:
    try:
        from tradingview_mcp.core.data.egx_sectors import get_sector

        sector = get_sector(symbol)
        return sector if sector and sector != "other" else None
    except Exception:
        return None


def open_position(
    symbol: str,
    qty: float,
    entry: float,
    stop: float,
    target1: Optional[float] = None,
    target2: Optional[float] = None,
    plan: Optional[dict] = None,
    note: str = "",
    allow_override: bool = False,
) -> dict:
    """Insert a new open (long) position; returns the stored row.

    Risk is checked at the point of commitment, not just in the sizer:
    - a required "why" note (journaling — setup, scanner, plan),
    - a warning above WARN_TRADE_RISK_PCT per-trade risk,
    - a hard block when total open heat would exceed MAX_OPEN_HEAT_PCT of
      ACCOUNT_SIZE — overridable only by an explicit ``allow_override``,
    - a sector-concentration warning at ≥2 open positions in the same sector.
    """
    try:
        symbol = str(symbol or "").upper().strip()
        if not symbol:
            return {"error": "symbol is required"}
        qty = float(qty)
        entry = float(entry)
        stop = float(stop)
        if qty <= 0:
            return {"error": "qty must be > 0"}
        if entry <= 0:
            return {"error": "entry must be > 0"}
        if stop < 0:
            return {"error": "stop cannot be negative"}
        if stop >= entry:
            # Positions are stored as side='long'; a stop at/above entry flips
            # the sign of r_multiple and understates open_risk downstream.
            return {"error": "stop must be below entry for a long position"}
        if not (note or "").strip():
            return {
                "error": "note is required — record WHY you are taking this trade "
                         "(setup, scanner that flagged it, planned R:R). You will "
                         "re-read it at close time.",
            }

        account = float(settings.account_size) or 0.0
        new_risk = (entry - stop) * qty
        warnings: list[str] = []
        if account > 0:
            new_risk_pct = new_risk / account * 100.0
            existing_risk = 0.0
            for pos in list_positions("open"):
                p_entry = _to_float(pos.get("entry")) or 0.0
                p_stop = _to_float(pos.get("stop"))
                p_qty = _to_float(pos.get("qty")) or 0.0
                p_dir = -1.0 if (pos.get("side") or "long") == "short" else 1.0
                if p_stop is not None:
                    existing_risk += max(0.0, (p_entry - p_stop) * p_dir) * p_qty
            heat_pct = (existing_risk + new_risk) / account * 100.0

            if heat_pct > MAX_OPEN_HEAT_PCT and not allow_override:
                return {
                    "error": (
                        f"BLOCKED: this trade takes total open risk to {heat_pct:.1f}% "
                        f"of the account ({existing_risk + new_risk:,.0f} EGP of "
                        f"{account:,.0f}) — above the {MAX_OPEN_HEAT_PCT:.0f}% open-heat "
                        "cap. Reduce size, close something, or resubmit with an "
                        "explicit override."
                    ),
                    "requires_override": True,
                    "open_heat_pct": round(heat_pct, 1),
                    "new_trade_risk_pct": round(new_risk_pct, 2),
                }
            if heat_pct > MAX_OPEN_HEAT_PCT:
                warnings.append(
                    f"OVERRIDDEN: open heat is {heat_pct:.1f}% of the account — "
                    f"above the {MAX_OPEN_HEAT_PCT:.0f}% cap."
                )
            if new_risk_pct > WARN_TRADE_RISK_PCT:
                warnings.append(
                    f"This single trade risks {new_risk_pct:.2f}% of the account "
                    f"(> {WARN_TRADE_RISK_PCT:.0f}% guideline)."
                )

        sector = _sector_of(symbol)
        if sector:
            same_sector = [
                p["symbol"] for p in list_positions("open")
                if _sector_of(str(p.get("symbol") or "")) == sector
            ]
            if len(same_sector) >= 2:
                warnings.append(
                    f"Sector concentration: already holding {len(same_sector)} open "
                    f"position(s) in '{sector}' ({', '.join(sorted(set(same_sector))[:5])}) "
                    "— EGX sectors move together."
                )

        position_id = db.execute(
            "INSERT INTO positions "
            "(symbol, side, qty, entry, stop, target1, target2, opened_at, plan_json, note, status) "
            "VALUES (?, 'long', ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
            (
                symbol, qty, entry, stop,
                _to_float(target1), _to_float(target2),
                _now_iso(),
                json.dumps(plan) if plan else None,
                note or "",
            ),
        )
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        result = rows[0] if rows else {"id": position_id, "symbol": symbol, "status": "open"}
        if warnings:
            result["risk_warnings"] = warnings
        return result
    except Exception as exc:
        return {"error": str(exc)}


def close_position(
    position_id: int,
    exit_price: float,
    plan_followed: Optional[bool] = None,
) -> dict:
    """Close a position at exit_price; returns pnl, pnl_pct and r_multiple.

    ``plan_followed`` records the one journaling question that matters at
    close time: did you exit per the plan, or deviate? Stored on the row so
    discipline can be compared against results later.
    """
    try:
        exit_price = float(exit_price)
        if exit_price < 0:
            return {"error": "exit_price cannot be negative"}
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        if not rows:
            return {"error": f"position {position_id} not found"}
        pos = rows[0]
        if pos.get("status") == "closed":
            return {"error": f"position {position_id} is already closed"}

        entry = float(pos["entry"])
        qty = float(pos["qty"])
        stop = _to_float(pos.get("stop"))
        direction = -1.0 if (pos.get("side") or "long") == "short" else 1.0

        pnl_gross = round((exit_price - entry) * qty * direction, 2)
        # Fees are computed at the configured rate and STORED on the row, so
        # historical stats stay stable if FEE_PCT_PER_SIDE changes later.
        fees = _round_trip_fees(entry, exit_price, qty)
        pnl = round(pnl_gross - fees, 2)
        pnl_pct = round(pnl / (entry * qty) * 100.0, 2) if entry and qty else None
        r_multiple: Optional[float] = None
        if stop is not None and entry - stop != 0 and qty:
            r_multiple = round((pnl / qty) / ((entry - stop) * direction), 2)

        closed_at = _now_iso()
        db.execute(
            "UPDATE positions SET status = 'closed', closed_at = ?, exit_price = ?, "
            "fees = ?, plan_followed = ? WHERE id = ?",
            (closed_at, exit_price, fees,
             None if plan_followed is None else (1 if plan_followed else 0),
             position_id),
        )
        result = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))[0]
        result.update({
            "pnl": pnl,                # net of fees — the honest headline
            "pnl_gross": pnl_gross,
            "fees": fees,
            "pnl_pct": pnl_pct,
            "r_multiple": r_multiple,  # net R
            "entry_note": pos.get("note") or "",  # what you said at entry
        })
        return result
    except Exception as exc:
        return {"error": str(exc)}


def list_positions(status: str = "all") -> list[dict]:
    """Positions filtered by status ('all' | 'open' | 'closed'), newest first."""
    try:
        if status in ("open", "closed"):
            rows = db.query(
                "SELECT * FROM positions WHERE status = ? ORDER BY id DESC", (status,)
            )
        else:
            rows = db.query("SELECT * FROM positions ORDER BY id DESC")
        for row in rows:
            row["plan"] = _parse_plan(row)
        return rows
    except Exception as exc:
        logger.error("list_positions failed: %s", exc)
        return []


def _parse_plan(row: dict) -> Optional[dict]:
    raw = row.get("plan_json")
    if not raw:
        return None
    try:
        plan = json.loads(raw)
        return plan if isinstance(plan, dict) else None
    except (TypeError, ValueError):
        return None


# ── performance ──────────────────────────────────────────────────────────────


def _closed_stats(closed: list[dict]) -> dict:
    """Net-of-fees realized stats over closed positions.

    Wins, R-multiples and realized PnL are all computed net of transaction
    costs (stored ``fees`` per row; estimated at the current rate for rows
    closed before fee tracking existed). Win rate's denominator counts only
    positions with a recorded exit — the same population as every other stat.
    """
    realized_net = 0.0
    realized_gross = 0.0
    fees_total = 0.0
    wins = 0
    settled = 0
    r_values: list[float] = []
    r_followed: list[float] = []
    r_deviated: list[float] = []
    for pos in closed:
        entry = _to_float(pos.get("entry")) or 0.0
        qty = _to_float(pos.get("qty")) or 0.0
        exit_price = _to_float(pos.get("exit_price"))
        if exit_price is None:
            continue
        settled += 1
        direction = -1.0 if (pos.get("side") or "long") == "short" else 1.0
        gross = (exit_price - entry) * qty * direction
        fees = _to_float(pos.get("fees"))
        if fees is None:
            fees = _round_trip_fees(entry, exit_price, qty)
        net = gross - fees
        realized_gross += gross
        realized_net += net
        fees_total += fees
        if net > 0:
            wins += 1
        stop = _to_float(pos.get("stop"))
        if stop is not None and entry - stop != 0 and qty:
            r_net = (net / qty) / ((entry - stop) * direction)
            r_values.append(r_net)
            followed = pos.get("plan_followed")
            if followed in (1, True):
                r_followed.append(r_net)
            elif followed in (0, False):
                r_deviated.append(r_net)
    return {
        "realized_pnl": round(realized_net, 2),
        "realized_pnl_gross": round(realized_gross, 2),
        "fees_paid": round(fees_total, 2),
        "win_rate": round(wins / settled * 100.0, 1) if settled else None,
        "avg_r": round(sum(r_values) / len(r_values), 2) if r_values else None,
        # The cheapest discipline detector there is: R when you followed the
        # plan vs R when you deviated.
        "avg_r_plan_followed": (
            round(sum(r_followed) / len(r_followed), 2) if r_followed else None
        ),
        "avg_r_plan_deviated": (
            round(sum(r_deviated) / len(r_deviated), 2) if r_deviated else None
        ),
        "plan_followed_count": len(r_followed),
        "plan_deviated_count": len(r_deviated),
    }


def _mark_prices(symbols: list[str]) -> dict[str, dict]:
    """Mark per TV symbol with provenance: {"price", "source", "as_of"}.

    Yahoo bulk quotes first (carrying the provider's ``price_source`` — for
    .CA symbols this is often a daily candle close, not a live quote), then
    the latest snapshot row, dated so stale marks are visibly stale.
    """
    marks: dict[str, dict] = {}
    if not symbols:
        return marks
    yahoo_map = {tv_to_yahoo(s).upper(): s for s in symbols}
    try:
        quotes = get_prices_bulk(list(yahoo_map))
    except Exception as exc:
        logger.warning("get_prices_bulk failed: %s", exc)
        quotes = []
    for quote in quotes:
        if not isinstance(quote, dict) or "error" in quote:
            continue
        tv_sym = yahoo_map.get(str(quote.get("symbol", "")).upper())
        price = _to_float(quote.get("price"))
        if tv_sym and price is not None:
            marks[tv_sym] = {
                "price": price,
                "source": str(quote.get("price_source") or "yahoo_quote"),
                "as_of": quote.get("market_time") or quote.get("as_of"),
            }
    for sym in symbols:
        if sym in marks:
            continue
        rows = db.query(
            "SELECT price, date FROM snapshots WHERE symbol = ? "
            "ORDER BY date DESC, id DESC LIMIT 1",
            (sym,),
        )
        if rows and rows[0].get("price") is not None:
            marks[sym] = {
                "price": float(rows[0]["price"]),
                "source": "snapshot",
                "as_of": rows[0].get("date"),
            }
    return marks


def _egx30_comparison(
    total_net_pnl: float,
) -> tuple[str, Optional[dict]]:
    """Portfolio-vs-EGX30 comparison since the first recorded trade.

    Index rows are persisted daily by the post-close job (symbol 'EGX30').
    The portfolio side approximates return as total net PnL over
    ACCOUNT_SIZE — documented in the note, not hidden.
    """
    try:
        first = db.query(
            "SELECT MIN(substr(opened_at, 1, 10)) AS d FROM positions"
        )
        start_date = first[0].get("d") if first else None
        if not start_date:
            return ("EGX30 benchmark: no trades recorded yet.", None)

        rows = db.query(
            "SELECT date, price FROM snapshots "
            "WHERE symbol = 'EGX30' AND price IS NOT NULL AND date >= ? "
            "ORDER BY date ASC",
            (start_date,),
        )
        if len(rows) < 2:
            return (
                "EGX30 benchmark comparison needs at least 2 daily index rows "
                "since your first trade — they accumulate each post-close run.",
                None,
            )
        first_row, last_row = rows[0], rows[-1]
        idx_change = (last_row["price"] - first_row["price"]) / first_row["price"] * 100.0

        account = float(settings.account_size) or 0.0
        pf_return = round(total_net_pnl / account * 100.0, 2) if account else None
        note = (
            f"Since {first_row['date']}: EGX30 {idx_change:+.2f}% · your net PnL "
            f"{total_net_pnl:+,.0f} EGP"
            + (f" (≈{pf_return:+.2f}% of ACCOUNT_SIZE)" if pf_return is not None else "")
            + f" as of {last_row['date']}."
        )
        return (note, {
            "since": first_row["date"],
            "index_change_pct": round(idx_change, 2),
            "portfolio_net_pnl": round(total_net_pnl, 2),
            "portfolio_return_pct_of_account": pf_return,
            "index_as_of": last_row["date"],
        })
    except Exception as exc:
        return (f"EGX30 benchmark comparison unavailable ({exc}).", None)


def _benchmark_fields(total_net_pnl: float) -> dict:
    note, detail = _egx30_comparison(total_net_pnl)
    fields: dict[str, Any] = {"benchmark_note": note}
    if detail:
        fields["benchmark"] = detail
    return fields


def performance() -> dict:
    """Portfolio performance: MTM open positions, realized stats, open risk."""
    try:
        open_positions = list_positions("open")
        closed_positions = list_positions("closed")

        marks = _mark_prices(sorted({p["symbol"] for p in open_positions}))
        open_rows: list[dict] = []
        unrealized_total = 0.0
        open_risk = 0.0
        for pos in open_positions:
            entry = _to_float(pos.get("entry")) or 0.0
            qty = _to_float(pos.get("qty")) or 0.0
            stop = _to_float(pos.get("stop"))
            direction = -1.0 if (pos.get("side") or "long") == "short" else 1.0
            mark_info = marks.get(pos["symbol"])
            mark = _to_float(mark_info.get("price")) if mark_info else None
            unrealized = None
            if mark is not None:
                # Net of the round-trip fees an exit at the mark would incur.
                gross = (mark - entry) * qty * direction
                unrealized = round(gross - _round_trip_fees(entry, mark, qty), 2)
                unrealized_total += unrealized
            if stop is not None:
                open_risk += max(0.0, (entry - stop) * direction) * qty
            open_rows.append({
                **pos,
                "mark_price": mark,
                "mark_source": mark_info["source"] if mark_info else None,
                "mark_as_of": mark_info.get("as_of") if mark_info else None,
                "unrealized_pnl": unrealized,   # net of estimated exit costs
                "unrealized_pct": (
                    round((mark - entry) / entry * 100.0 * direction, 2)
                    if (mark is not None and entry) else None
                ),
            })

        stats = _closed_stats(closed_positions)
        return {
            "open_positions": open_rows,
            "open_count": len(open_rows),
            "closed_count": len(closed_positions),
            "unrealized_pnl": round(unrealized_total, 2),
            "realized_pnl": stats["realized_pnl"],
            "realized_pnl_gross": stats["realized_pnl_gross"],
            "fees_paid": stats["fees_paid"],
            "win_rate": stats["win_rate"],
            "avg_r": stats["avg_r"],
            "avg_r_plan_followed": stats["avg_r_plan_followed"],
            "avg_r_plan_deviated": stats["avg_r_plan_deviated"],
            "plan_followed_count": stats["plan_followed_count"],
            "plan_deviated_count": stats["plan_deviated_count"],
            "open_risk": round(open_risk, 2),
            "open_heat_pct": (
                round(open_risk / settings.account_size * 100.0, 1)
                if settings.account_size else None
            ),
            "fee_pct_per_side": settings.fee_pct_per_side,
            "pnl_basis": (
                f"All PnL, win rate and R figures are NET of {settings.fee_pct_per_side}%/side "
                "transaction costs; gross figures carry a _gross suffix."
            ),
            **_benchmark_fields(stats["realized_pnl"] + round(unrealized_total, 2)),
            "as_of": _now_iso(),
        }
    except Exception as exc:
        return {"error": str(exc)}
