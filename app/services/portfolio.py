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


# ── plan defaults (stop / targets / note from the engine's own trade plan) ────


def _find_num_key(obj: Any, names: tuple[str, ...], depth: int = 0) -> Optional[float]:
    """Depth-limited search for the first numeric value under any of ``names``."""
    if depth > 4 or not isinstance(obj, dict):
        return None
    for key, val in obj.items():
        if str(key).lower() in names:
            found = _to_float(val)
            if found is not None:
                return found
    for val in obj.values():
        if isinstance(val, dict):
            found = _find_num_key(val, names, depth + 1)
            if found is not None:
                return found
    return None


def _yahoo_atr(symbol: str) -> tuple[Optional[float], Optional[float]]:
    """(14-day ATR, last close) from Yahoo daily candles — the fallback risk
    anchor when TradingView is rate-limited. Either value may be None."""
    try:
        from app.services import guardian, history

        hist = history.get_history(symbol, "3mo", "1d")
        if not isinstance(hist, dict) or "error" in hist:
            return None, None
        candles = [c for c in (hist.get("candles") or []) if isinstance(c, dict)]
        last_close = _to_float(candles[-1].get("close")) if candles else None
        return guardian._atr(candles), last_close
    except Exception as exc:  # noqa: BLE001
        logger.warning("yahoo ATR fallback failed for %s: %s", symbol, exc)
        return None, None


def _upstream_error(*sections: dict) -> Optional[str]:
    """Message of the first {"error": ...} found in the given core-library sections."""
    for section in sections:
        err = section.get("error") if isinstance(section, dict) else None
        if err:
            return str(err.get("message") or err) if isinstance(err, dict) else str(err)
    return None


def plan_defaults(symbol: str, entry: Optional[float] = None) -> dict:
    """Stop / targets / note for a new position, taken from the stock page's
    own trade plan so the user only has to type symbol, quantity and fill.

    Returns {"stop", "target1", "target2", "note", "score", "signal",
    "source", "warnings", "plan"} — any level the engine cannot supply is
    None and explained in ``warnings`` rather than invented.
    """
    try:
        from app.services import stocks

        bare = str(symbol or "").upper().strip().split(":")[-1]
        if not bare:
            return {"error": "symbol is required"}
        entry_f = _to_float(entry)
        detail = stocks.detail(bare)
        if not isinstance(detail, dict) or "error" in detail:
            return {"error": f"stock detail unavailable for {bare}: "
                             f"{(detail or {}).get('error', 'unknown')}"}
        analysis: dict = detail.get("analysis") or {}
        if not isinstance(analysis, dict):
            analysis = {}
        plan: dict = detail.get("trade_plan") or {}
        if not isinstance(plan, dict):
            plan = {}
        levels = stocks._plan_levels(plan)
        warnings: list[str] = []

        price_data = analysis.get("price_data")
        price = _to_float(price_data.get("current_price")) if isinstance(price_data, dict) else None
        upstream = _upstream_error(analysis, plan)
        if upstream:
            warnings.append(
                "TradingView analysis is unavailable right now (usually a 1-2 minute "
                f"rate-limit pause): {upstream[:140]}. Stop falls back to a Yahoo ATR; "
                "retry in a minute for the full plan (score, targets)."
            )
        yahoo_atr: Optional[float] = None
        if price is None or upstream:
            yahoo_atr, last_close = _yahoo_atr(bare)
            if price is None:
                price = last_close
        ref = entry_f or price
        stop = levels.get("stop")
        source = "trade plan"
        if stop is not None and ref is not None and stop >= ref:
            warnings.append(
                f"The plan's stop {stop:.2f} is not below your entry {ref:.2f} — "
                "falling back to entry minus 2×ATR."
            )
            stop = None
        if stop is None and ref is not None:
            atr = _find_num_key(analysis, ("atr", "atr14", "atr_14"))
            atr_source = "TradingView ATR"
            if not atr or atr <= 0:
                if yahoo_atr is None:
                    yahoo_atr, _ = _yahoo_atr(bare)
                atr, atr_source = yahoo_atr, "Yahoo 14-day ATR"
            if atr and atr > 0:
                stop = round(ref - 2.0 * atr, 2)
                source = f"entry − 2×{atr_source}"
            else:
                warnings.append("No stop available: the trade plan has none below your entry "
                                "and no ATR could be computed — enter the stop yourself.")
        t1, t2 = levels.get("t1"), levels.get("t2")
        if ref is not None:
            if t1 is not None and t1 <= ref:
                warnings.append(f"Plan target 1 ({t1:.2f}) is not above your entry — left empty.")
                t1 = None
            if t2 is not None and t2 <= ref:
                warnings.append(f"Plan target 2 ({t2:.2f}) is not above your entry — left empty.")
                t2 = None

        score = _to_float(analysis.get("stock_score"))
        signal = analysis.get("signal") or analysis.get("recommendation")
        if not isinstance(signal, str):
            signal = None
        setup = plan.get("trade_setup")
        scenario = setup.get("primary_scenario") if isinstance(setup, dict) else None
        rr = None
        if ref is not None and stop is not None and t2 is not None and ref > stop:
            rr = round((t2 - ref) / (ref - stop), 2)
        parts = [f"Auto-filled from the {bare} trade plan"]
        if scenario:
            parts.append(f"scenario {scenario}")
        if score is not None:
            parts.append(f"score {score:.0f}")
        if signal:
            parts.append(f"signal {signal}")
        if rr is not None:
            parts.append(f"planned R:R {rr:.1f} to T2")
        note = " · ".join(parts) + "."
        checks = detail.get("plan_checks") if isinstance(detail.get("plan_checks"), list) else []
        warnings.extend(str(c) for c in checks[:3])
        return {
            "symbol": bare,
            "entry": ref,
            "current_price": price,
            "stop": stop,
            "target1": t1,
            "target2": t2,
            "note": note,
            "score": score,
            "signal": signal,
            "source": source,
            "warnings": warnings,
            "plan": {
                "score": score, "signal": signal, "scenario": scenario,
                "levels": levels, "as_of": detail.get("as_of"),
            },
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
    stop: Optional[float] = None,
    target1: Optional[float] = None,
    target2: Optional[float] = None,
    plan: Optional[dict] = None,
    note: str = "",
    allow_override: bool = False,
    raised_stop: bool = False,
) -> dict:
    """Insert a new open (long) position; returns the stored row.

    ``stop`` may be omitted: the stop, any missing target, and an empty note
    are then filled from the engine's own trade plan (``plan_defaults``) and
    the plan is stored on the row so the guardian knows the score at entry.

    Risk is checked at the point of commitment, not just in the sizer:
    - a required "why" note (journaling — setup, scanner, plan),
    - a warning above WARN_TRADE_RISK_PCT per-trade risk,
    - a hard block when total open heat would exceed MAX_OPEN_HEAT_PCT of
      ACCOUNT_SIZE — overridable only by an explicit ``allow_override``,
    - a sector-concentration warning at ≥2 open positions in the same sector.

    ``raised_stop=True`` admits a stop at/above entry — an EXISTING winner
    being recorded after its stop was already moved above cost. The initial
    risk is then unknown, so ``initial_stop`` is stored NULL and R-multiples
    for that trade stay unavailable rather than being invented.
    """
    try:
        symbol = str(symbol or "").upper().strip()
        if not symbol:
            return {"error": "symbol is required"}
        qty = float(qty)
        entry = float(entry)
        if qty <= 0:
            return {"error": "qty must be > 0"}
        if entry <= 0:
            return {"error": "entry must be > 0"}
        auto_filled: list[str] = []
        # Consult the trade plan only when the user relies on it (no stop or no
        # note). A fully specified entry must never trigger a network call.
        if stop is None or not (note or "").strip():
            defaults = plan_defaults(symbol, entry)
            if "error" in defaults:
                if stop is None:
                    return {"error": f"stop is required — could not auto-fill it: {defaults['error']}"}
            else:
                d_stop, d_t1, d_t2 = defaults.get("stop"), defaults.get("target1"), defaults.get("target2")
                if stop is None and d_stop is not None:
                    stop = float(d_stop)
                    auto_filled.append(f"stop {stop:.2f} ({defaults.get('source')})")
                if target1 is None and d_t1 is not None:
                    target1 = float(d_t1)
                    auto_filled.append(f"target1 {target1:.2f}")
                if target2 is None and d_t2 is not None:
                    target2 = float(d_t2)
                    auto_filled.append(f"target2 {target2:.2f}")
                if not (note or "").strip() and defaults.get("note"):
                    note = str(defaults["note"])
                    auto_filled.append("note")
                if plan is None and isinstance(defaults.get("plan"), dict):
                    plan = defaults["plan"]
        if stop is None:
            return {"error": "stop is required — the trade plan offers no stop below your entry; "
                             "enter one yourself."}
        stop = float(stop)
        if stop < 0:
            return {"error": "stop cannot be negative"}
        if stop >= entry and not raised_stop:
            # Positions are stored as side='long'; a stop at/above entry flips
            # the sign of r_multiple and understates open_risk downstream.
            return {
                "error": "stop must be below entry for a long position — for an "
                         "existing winner whose stop is already above cost, resubmit "
                         "with raised_stop=true (R multiples will be unavailable).",
            }
        initial_stop: Optional[float] = stop if stop < entry else None
        # Targets you typed yourself must be real profit levels. (Plan targets
        # below entry were already dropped with a warning in plan_defaults.)
        for label, val in (("target1", target1), ("target2", target2)):
            if val is not None and float(val) <= entry:
                return {
                    "error": f"{label} {float(val):.2f} must be above your entry {entry:.2f}. "
                             "A target at/below cost would make the Guardian call a loss a "
                             "'target hit'. Leave it empty to take the plan's target, or enter "
                             "a real profit level.",
                }
        if target1 is not None and target2 is not None and float(target2) <= float(target1):
            return {"error": f"target2 ({float(target2):.2f}) must be above target1 ({float(target1):.2f})."}
        if not (note or "").strip():
            return {
                "error": "note is required — record WHY you are taking this trade "
                         "(setup, scanner that flagged it, planned R:R). You will "
                         "re-read it at close time.",
            }

        account = float(settings.account_size) or 0.0
        new_risk = max(0.0, entry - stop) * qty
        warnings: list[str] = []
        if initial_stop is None:
            warnings.append(
                f"Stop {stop:.2f} is at/above entry {entry:.2f}: initial risk unknown, so "
                "R multiples for this trade will show as unavailable. The guardian still "
                "watches the stop."
            )
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

        already_open = [p for p in list_positions("open") if p.get("symbol") == symbol]
        if already_open:
            held = sum(_to_float(p.get("qty")) or 0.0 for p in already_open)
            warnings.append(
                f"You already hold {held:g} {symbol} in {len(already_open)} open position(s) "
                f"(#{', #'.join(str(p['id']) for p in already_open)}). If this is the same "
                "holding, use '+ Buy' on that row instead — a second row double-counts it. "
                "Use 'Remove' to delete a row entered by mistake."
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
            "(symbol, side, qty, entry, stop, initial_stop, target1, target2, opened_at, "
            " plan_json, note, status) "
            "VALUES (?, 'long', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
            (
                symbol, qty, entry, stop, initial_stop,
                _to_float(target1), _to_float(target2),
                _now_iso(),
                json.dumps(plan) if plan else None,
                note or "",
            ),
        )
        try:  # journal the opening buy so the fill history is complete
            _record_fill(position_id, "buy", qty, entry,
                         round(qty * entry * settings.fee_pct_per_side / 100.0, 2),
                         None, entry, qty, "open")
        except Exception as exc:  # noqa: BLE001 — journaling must never fail the open
            logger.warning("could not journal opening fill: %s", exc)
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        result = rows[0] if rows else {"id": position_id, "symbol": symbol, "status": "open"}
        result["plan"] = _parse_plan(result)
        if warnings:
            result["risk_warnings"] = warnings
        if auto_filled:
            result["auto_filled"] = auto_filled
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
        direction = -1.0 if (pos.get("side") or "long") == "short" else 1.0
        per_share_risk = _risk_per_share(pos)

        pnl_gross = round((exit_price - entry) * qty * direction, 2)
        # Fees are computed at the configured rate and STORED on the row, so
        # historical stats stay stable if FEE_PCT_PER_SIDE changes later.
        fees = _round_trip_fees(entry, exit_price, qty)
        pnl = round(pnl_gross - fees, 2)
        pnl_pct = round(pnl / (entry * qty) * 100.0, 2) if entry and qty else None
        r_multiple: Optional[float] = None
        if per_share_risk and qty:
            r_multiple = round((pnl / qty) / per_share_risk, 2)

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


def _record_fill(position_id: int, side: str, qty: float, price: float, fees: float,
                 realized: Optional[float], entry_after: float, qty_after: float,
                 note: str = "") -> None:
    db.execute(
        "INSERT INTO position_fills (position_id, ts, side, qty, price, fees, realized_pnl, "
        " entry_after, qty_after, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (position_id, _now_iso(), side, qty, price, fees, realized, entry_after, qty_after, note),
    )


def adjust_position(position_id: int, qty_delta: float, price: float, note: str = "") -> dict:
    """Buy more (``qty_delta`` > 0) or sell part (``qty_delta`` < 0) of an open position.

    - A buy blends the average entry: (old_qty × old_entry + Δ × price) / new_qty.
      The stop, targets and ``initial_stop`` are untouched; heat is re-checked
      and warned about (not blocked — the shares are already bought).
    - A sell realizes PnL on the sold shares, net of round-trip fees at the
      blended entry, and leaves the average entry unchanged. Selling the whole
      remaining quantity closes the position via ``close_position``.
    Every fill is journaled in ``position_fills``.
    """
    try:
        qty_delta = float(qty_delta)
        price = float(price)
        if qty_delta == 0:
            return {"error": "qty_delta must be non-zero (positive = buy, negative = sell)"}
        if price <= 0:
            return {"error": "price must be > 0"}
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        if not rows:
            return {"error": f"position {position_id} not found"}
        pos = rows[0]
        if pos.get("status") != "open":
            return {"error": f"position {position_id} is not open"}
        old_qty = float(pos["qty"])
        old_entry = float(pos["entry"])
        warnings: list[str] = []

        if qty_delta > 0:
            new_qty = old_qty + qty_delta
            new_entry = round((old_qty * old_entry + qty_delta * price) / new_qty, 4)
            fees = round(qty_delta * price * settings.fee_pct_per_side / 100.0, 2)
            db.execute("UPDATE positions SET qty = ?, entry = ? WHERE id = ?",
                       (new_qty, new_entry, position_id))
            _record_fill(position_id, "buy", qty_delta, price, fees, None, new_entry, new_qty, note)
            stop = _to_float(pos.get("stop"))
            if price < old_entry:
                warnings.append(
                    f"Averaging DOWN: bought at {price:.2f} below your {old_entry:.2f} average. "
                    "Adding to a loser is the most expensive habit in trading — make sure the "
                    "setup, not the price, is the reason."
                )
            account = float(settings.account_size) or 0.0
            if stop is not None and account > 0:
                pos_risk = max(0.0, new_entry - stop) * new_qty
                others = 0.0
                for p in list_positions("open"):
                    if p["id"] == position_id:
                        continue
                    p_stop = _to_float(p.get("stop"))
                    if p_stop is not None:
                        others += max(0.0, float(p["entry"]) - p_stop) * float(p["qty"])
                heat = (others + pos_risk) / account * 100.0
                if heat > MAX_OPEN_HEAT_PCT:
                    warnings.append(
                        f"Open heat is now {heat:.1f}% of the account — above the "
                        f"{MAX_OPEN_HEAT_PCT:.0f}% cap. Consider trimming somewhere."
                    )
            result = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))[0]
            result["plan"] = _parse_plan(result)
            result["fill"] = {"side": "buy", "qty": qty_delta, "price": price, "fees": fees,
                              "entry_before": old_entry, "entry_after": new_entry,
                              "qty_before": old_qty, "qty_after": new_qty}
            if warnings:
                result["risk_warnings"] = warnings
            return result

        sell_qty = -qty_delta
        if sell_qty > old_qty + 1e-9:
            return {"error": f"cannot sell {sell_qty:g} shares — only {old_qty:g} held"}
        if abs(sell_qty - old_qty) < 1e-9:
            closed = close_position(position_id, price)
            if "error" not in closed:
                closed["fill"] = {"side": "sell", "qty": sell_qty, "price": price,
                                  "closed_position": True}
            return closed
        fees = _round_trip_fees(old_entry, price, sell_qty)
        realized = round((price - old_entry) * sell_qty - fees, 2)
        new_qty = old_qty - sell_qty
        db.execute("UPDATE positions SET qty = ? WHERE id = ?", (new_qty, position_id))
        _record_fill(position_id, "sell", sell_qty, price, fees, realized, old_entry, new_qty, note)
        per_share_risk = _risk_per_share(pos)
        r_part = round((realized / sell_qty) / per_share_risk, 2) if per_share_risk else None
        result = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))[0]
        result["plan"] = _parse_plan(result)
        result["fill"] = {"side": "sell", "qty": sell_qty, "price": price, "fees": fees,
                          "realized_pnl": realized, "r_multiple": r_part,
                          "qty_before": old_qty, "qty_after": new_qty}
        return result
    except Exception as exc:
        return {"error": str(exc)}


def delete_position(position_id: int) -> dict:
    """Erase a position record entered by mistake (duplicate, typo), with its
    fills and guardian verdicts. This is NOT a sale — nothing is realized.
    Use close_position / adjust_position for real exits."""
    try:
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        if not rows:
            return {"error": f"position {position_id} not found"}
        pos = rows[0]
        sells = db.query(
            "SELECT COUNT(*) AS n FROM position_fills WHERE position_id = ? AND side = 'sell'",
            (position_id,),
        )
        if sells and int(sells[0]["n"] or 0) > 0:
            return {"error": "this position has partial sales journaled — removing it would erase "
                             "realized PnL. Close it instead, or remove the fills first."}
        db.execute("DELETE FROM position_fills WHERE position_id = ?", (position_id,))
        db.execute("DELETE FROM guardian_verdicts WHERE position_id = ?", (position_id,))
        deleted = db.execute_rowcount("DELETE FROM positions WHERE id = ?", (position_id,))
        if not deleted:
            return {"error": f"position {position_id} could not be deleted"}
        return {"ok": True, "deleted": {"id": position_id, "symbol": pos.get("symbol"),
                                        "qty": pos.get("qty"), "entry": pos.get("entry"),
                                        "status": pos.get("status")}}
    except Exception as exc:
        return {"error": str(exc)}


def position_fills(position_id: Optional[int] = None, limit: int = 200) -> list[dict]:
    """Fill journal, newest first (optionally for one position)."""
    try:
        limit = max(1, min(int(limit), 1000))
        if position_id is not None:
            return db.query(
                "SELECT * FROM position_fills WHERE position_id = ? ORDER BY id DESC LIMIT ?",
                (position_id, limit),
            )
        return db.query("SELECT * FROM position_fills ORDER BY id DESC LIMIT ?", (limit,))
    except Exception as exc:
        logger.error("position_fills failed: %s", exc)
        return []


def _partial_sales() -> tuple[float, float, int]:
    """(net realized, fees, count) from partial sells journaled in position_fills."""
    try:
        rows = db.query(
            "SELECT COALESCE(SUM(realized_pnl), 0) AS pnl, COALESCE(SUM(fees), 0) AS fees, "
            "COUNT(*) AS n FROM position_fills WHERE side = 'sell'"
        )
        if rows:
            return (float(rows[0]["pnl"] or 0.0), float(rows[0]["fees"] or 0.0), int(rows[0]["n"] or 0))
    except Exception as exc:
        logger.warning("partial sales aggregate failed: %s", exc)
    return (0.0, 0.0, 0)


def _risk_per_share(pos: dict) -> Optional[float]:
    """Initial risk per share (entry minus the stop AT ENTRY), or None.

    Uses ``initial_stop`` when recorded, else the current stop for rows that
    predate the column. A stop at/above entry (raised winner, or unknown
    initial risk) yields None: R is then unavailable, never fabricated.
    """
    entry = _to_float(pos.get("entry"))
    direction = -1.0 if (pos.get("side") or "long") == "short" else 1.0
    stop = _to_float(pos.get("initial_stop"))
    if stop is None:
        stop = _to_float(pos.get("stop"))
    if entry is None or stop is None:
        return None
    risk = (entry - stop) * direction
    return risk if risk > 0 else None


def update_position(
    position_id: int,
    stop: Optional[float] = None,
    target1: Optional[float] = None,
    target2: Optional[float] = None,
    note: Optional[str] = None,
    initial_stop: Optional[float] = None,
) -> dict:
    """Adjust the CURRENT stop / targets / note of an open position.

    ``initial_stop`` may be supplied ONCE, only while the record has none (a
    winner entered with its stop already above cost): it is the stop you had
    at entry and anchors R multiples from then on.

    This is how a guardian TIGHTEN_STOP suggestion is acted on. The stop may
    sit at or above entry (locking in profit); ``initial_stop`` is never
    touched, so R-multiples keep measuring against the risk you took at entry.
    Passing a field as None leaves it unchanged.
    """
    try:
        rows = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))
        if not rows:
            return {"error": f"position {position_id} not found"}
        pos = rows[0]
        if pos.get("status") != "open":
            return {"error": f"position {position_id} is not open"}
        sets: list[str] = []
        params: list[Any] = []
        warnings: list[str] = []
        entry = float(pos["entry"])
        if stop is not None:
            stop = float(stop)
            if stop <= 0:
                return {"error": "stop must be > 0"}
            sets.append("stop = ?")
            params.append(stop)
            old_stop = _to_float(pos.get("stop"))
            if old_stop is not None and stop < old_stop:
                warnings.append(
                    f"Stop LOWERED from {old_stop:.2f} to {stop:.2f}. Widening a stop after "
                    "entry is the classic way a small loss becomes a large one — make sure "
                    "this is a plan, not a hope."
                )
            if stop >= entry:
                warnings.append(
                    f"Stop {stop:.2f} is at/above entry {entry:.2f}: the trade is now "
                    "risk-free (before fees/gaps)."
                )
        for col, val in (("target1", target1), ("target2", target2)):
            if val is not None:
                val = float(val)
                if val <= 0:
                    return {"error": f"{col} must be > 0"}
                if val <= entry:
                    return {"error": f"{col} {val:.2f} must be above your entry {entry:.2f} — "
                                     "a target at/below cost is not a profit level."}
                sets.append(f"{col} = ?")
                params.append(val)
        new_t1 = float(target1) if target1 is not None else _to_float(pos.get("target1"))
        new_t2 = float(target2) if target2 is not None else _to_float(pos.get("target2"))
        if ((target1 is not None or target2 is not None) and new_t1 is not None
                and new_t2 is not None and new_t2 <= new_t1):
            return {"error": f"target2 ({new_t2:.2f}) must be above target1 ({new_t1:.2f})."}
        if initial_stop is not None:
            if _to_float(pos.get("initial_stop")) is not None:
                return {"error": "initial_stop is already recorded and cannot be changed — "
                                 "it is the risk you took at entry."}
            initial_stop = float(initial_stop)
            if initial_stop <= 0 or initial_stop >= entry:
                return {"error": f"initial_stop must be below your entry {entry:.2f} — it is the "
                                 "protective stop you had when you bought."}
            sets.append("initial_stop = ?")
            params.append(initial_stop)
        if note is not None:
            sets.append("note = ?")
            params.append(str(note))
        if not sets:
            return {"error": "nothing to update"}
        params.append(position_id)
        db.execute(f"UPDATE positions SET {', '.join(sets)} WHERE id = ?", params)  # noqa: S608
        result = db.query("SELECT * FROM positions WHERE id = ?", (position_id,))[0]
        result["plan"] = _parse_plan(result)
        if warnings:
            result["risk_warnings"] = warnings
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
        per_share_risk = _risk_per_share(pos)
        if per_share_risk and qty:
            r_net = (net / qty) / per_share_risk
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
        partial_pnl, partial_fees, partial_n = _partial_sales()
        realized_total = round(stats["realized_pnl"] + partial_pnl, 2)
        return {
            "open_positions": open_rows,
            "open_count": len(open_rows),
            "closed_count": len(closed_positions),
            "unrealized_pnl": round(unrealized_total, 2),
            # Closed positions PLUS partial sales journaled in position_fills.
            "realized_pnl": realized_total,
            "realized_pnl_closed": stats["realized_pnl"],
            "realized_pnl_partial_sales": round(partial_pnl, 2),
            "partial_sales_count": partial_n,
            "realized_pnl_gross": round(stats["realized_pnl_gross"] + partial_pnl + partial_fees, 2),
            "fees_paid": round(stats["fees_paid"] + partial_fees, 2),
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
            **_benchmark_fields(realized_total + round(unrealized_total, 2)),
            "as_of": _now_iso(),
        }
    except Exception as exc:
        return {"error": str(exc)}
