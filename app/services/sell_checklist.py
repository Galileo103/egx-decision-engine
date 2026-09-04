"""Six-pillar SELL checklist for a stock you hold — the mirror of the buy checklist.

    Thesis (daily trend + score) → Weekly structure → Relative strength →
    Distribution volume → Bearish events & shapes → Exit plan (stop, ladder)

The buy checklist asks "is there a reason to enter?"; this one asks "is there
a reason to leave, and at what price?". Pillar statuses read from the HOLDER's
point of view:

    pass  the pillar still supports holding
    warn  it is deteriorating — tighten, do not pre-empt
    fail  it says exit (or reduce) — and names the level that says so

The verdict is ``hold`` / ``reduce`` / ``exit`` and every verdict cites levels:
``exit_below`` (the line that ends the trade), ``reduce_at`` (where to take a
partial) and ``trail_stop_to`` (a stop anchored to a tested support), with a
partial-exit ladder built from the position's own targets. Yahoo daily candles
only, so it answers instantly and survives TradingView pauses. Never raises.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import settings

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

PILLARS = ("thesis", "weekly", "relative_strength", "distribution", "bearish_events", "exit_plan")
LABELS = {
    "thesis": "Thesis / daily trend", "weekly": "Weekly structure", "relative_strength": "Relative strength",
    "distribution": "Distribution volume", "bearish_events": "Bearish events", "exit_plan": "Exit plan",
}
#: Price-action events that mean "the buyers just failed" — a fresh one on a held
#: stock is worth a Telegram ping even when the stop is intact.
RED_FLAGS = {"bull_trap", "false_breakout", "change_of_character", "failed_retest", "upthrust",
             "lower_high_lower_low", "break_of_structure"}
#: A bearish event this many sessions old or younger counts as fresh.
FRESH_SESSIONS = 3
#: Partial-exit ladder: share of the position sold at target 1.
PARTIAL_PCT = 50


def _p(status: str, text: str, **extra: Any) -> dict:
    return {"status": status, "text": text, **extra}


def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _find_position(sym: str) -> Optional[dict]:
    try:
        from app.services import portfolio

        for p in portfolio.list_positions("open"):
            if str(p.get("symbol") or "").upper() == sym:
                return p
    except Exception:  # noqa: BLE001
        return None
    return None


def _sessions_ago(date: Optional[str], candles: list[dict]) -> Optional[int]:
    if not date:
        return None
    d = str(date)[:10]
    for k in range(1, min(len(candles), 60) + 1):
        if str(candles[-k].get("time"))[:10] <= d:
            return k - 1
    return None


def sell_checklist(symbol: str, position: Optional[dict] = None, candles: Optional[list[dict]] = None,
                   mark: Optional[float] = None) -> dict:
    """Run the six sell pillars. ``position`` (entry/stop/targets/qty) is looked up
    from the open book when omitted; without any position the checklist still runs
    as "if you held it" with a levels-based stop."""
    try:
        from app.services import guardian, leaders, levels, patterns, weekly
        from app.services.rules_backtest import Ind

        sym = str(symbol or "").upper().strip().split(":")[-1]
        if candles is None:
            candles = leaders.daily_candles(sym)
        if len(candles) < 120:
            return {"symbol": sym, "error": f"not enough daily history ({len(candles)} bars)"}
        pos = position if position is not None else _find_position(sym)
        held = bool(pos)
        x = Ind(candles)
        last_close = x.c[-1]
        price = float(mark) if mark else last_close
        atr = x.atr[-1] or price * 0.02
        lv = levels.compute(sym, candles)
        det = patterns.detect(sym, candles)
        pats = (det.get("patterns") or []) if isinstance(det, dict) else []
        wk = weekly.context(candles)
        out: dict[str, dict] = {}
        levels_cited: dict[str, Any] = {}

        entry = _num((pos or {}).get("entry"))
        stop = _num((pos or {}).get("stop"))
        t1 = _num((pos or {}).get("target1"))
        t2 = _num((pos or {}).get("target2"))
        qty = _num((pos or {}).get("qty")) or 0.0
        # invalid targets (at/below entry) are ignored exactly as the Guardian does
        if entry is not None:
            if t1 is not None and t1 <= entry:
                t1 = None
            if t2 is not None and t2 <= entry:
                t2 = None
        if t1 is not None and t2 is not None and t2 <= t1:
            t2 = None

        # 1. Thesis — daily trend health plus the score you bought on.
        sma20, sma50 = x.sma20[-1], x.sma50[-1]
        structure = next((r for r in pats if r["pattern"] in ("higher_high_higher_low", "lower_high_lower_low")
                          and r.get("timeframe", "1D") == "1D"), None)
        score_bits: list[str] = []
        score_fail = score_warn = False
        if held:
            opened = str((pos or {}).get("opened_at") or "")[:10]
            entry_score, src = guardian._entry_score(pos or {}, opened)
            snap = guardian._latest_snapshot(sym)
            score_now = _num((snap or {}).get("score")) if snap else None
            signal_now = str((snap or {}).get("signal") or "") if snap else ""
            if entry_score is not None and score_now is not None:
                drop = entry_score - score_now
                score_bits.append(f"score {entry_score:.0f} at entry ({src}) → {score_now:.0f} now")
                if drop >= settings.guardian_score_drop:
                    score_fail = True
                elif drop >= settings.guardian_score_drop / 2:
                    score_warn = True
            if "SELL" in signal_now.upper():
                score_bits.append(f"snapshot signal is {signal_now}")
                score_fail = True
        if sma20 and sma50:
            if price < sma50 and sma20 < sma50:
                st, txt = "fail", (f"Daily trend broken: price {price:.2f} is below the 50-day average ({sma50:.2f}) and the "
                                   f"20-day has crossed under it. The reason you bought — a rising stock — is gone.")
            elif price < sma20 or (structure and structure["pattern"] == "lower_high_lower_low"):
                st, txt = "warn", (f"Tiring: price {price:.2f} is {'below the 20-day average (' + format(sma20, '.2f') + ')' if price < sma20 else 'still above the 20-day'}"
                                   + (", and the swings make lower highs and lower lows" if structure and structure["pattern"] == "lower_high_lower_low" else "")
                                   + f". The 50-day ({sma50:.2f}) is the line the trend must hold.")
            else:
                st, txt = "pass", (f"Trend intact: price {price:.2f} above the 20-day ({sma20:.2f}) and 50-day ({sma50:.2f}) averages"
                                   + ("; higher highs and higher lows." if structure and structure["pattern"] == "higher_high_higher_low" else "."))
            levels_cited["sma50"] = round(sma50, 4)
        else:
            st, txt = "warn", "Not enough history for the moving averages."
        if score_fail:
            st = "fail"
            txt += " Thesis check: " + "; ".join(score_bits) + " — the setup that justified the entry has unwound."
        elif score_bits:
            if score_warn and st == "pass":
                st = "warn"
            txt += " Thesis check: " + "; ".join(score_bits) + "."
        out["thesis"] = _p(st, txt)

        # 2. Weekly structure — whether, not when.
        if "error" in wk:
            out["weekly"] = _p("warn", "Weekly context unavailable (thin history).")
        else:
            low = wk.get("last_swing_low")
            tail = f" The weekly low that must hold: {low:.2f}." if low else ""
            levels_cited["weekly_swing_low"] = low
            if wk["trend"] == "up":
                out["weekly"] = _p("pass", wk["text"] + tail)
            elif wk["trend"] == "down":
                out["weekly"] = _p("fail", wk["text"] + " Holding a daily position inside a weekly downtrend is fighting the tide." + tail)
            else:
                out["weekly"] = _p("warn", wk["text"] + tail)

        # 3. Relative strength — is the stock still leading the index?
        try:
            bench = leaders.benchmark_series()
            rs = leaders._symbol_metrics(sym, bench)
        except Exception:  # noqa: BLE001
            rs = None
        if not rs or rs.get("excess_1m") is None:
            out["relative_strength"] = _p("warn", "Relative strength unavailable (no benchmark).")
        else:
            e1, e3 = rs["excess_1m"], rs.get("excess_3m")
            off_high = rs.get("pct_from_52w_high")
            base = (f"Last month {rs['ret_1m']:+.1f}% vs EGX30 {rs['bench_1m']:+.1f}% ({e1:+.1f} points)"
                    + (f"; 3 months {e3:+.1f} points" if e3 is not None else "")
                    + (f"; {off_high:.1f}% from the 52-week high" if off_high is not None else "") + ".")
            if e1 <= -5.0:
                out["relative_strength"] = _p("fail", base + " The stock has lost its leadership — money is rotating out of it.")
            elif e1 < 0 and (e3 is None or e3 > 0):
                out["relative_strength"] = _p("warn", base + " Strength is fading: it led over three months but lags this month.")
            elif e1 < 0:
                out["relative_strength"] = _p("warn", base + " Lagging the index.")
            elif off_high is not None and off_high <= -15:
                out["relative_strength"] = _p("warn", base + " Still beating the index but well off its high.")
            else:
                out["relative_strength"] = _p("pass", base + " Still a leader.")
            out["relative_strength"]["excess_1m"] = e1
            out["relative_strength"]["excess_3m"] = e3

        # 4. Distribution — who is doing the volume, sellers or buyers?
        v20 = x.vavg[-1] or 0.0
        recent = sum(x.v[-5:]) / 5.0 if v20 else 0.0
        ratio = recent / v20 if v20 else None
        n = len(x.c)
        down_vol = sum(x.v[i] for i in range(n - 20, n) if x.c[i] < x.c[i - 1])
        tot_vol = sum(x.v[-20:]) or 1.0
        down_share = down_vol / tot_vol
        if ratio is None:
            out["distribution"] = _p("warn", "No volume data.")
        elif down_share >= 0.65 or (down_share >= 0.55 and ratio >= 1.1):
            out["distribution"] = _p("fail", f"Distribution: {down_share * 100:.0f}% of the last 20 sessions' volume traded on down days" + (f" and this week runs at {ratio:.1f}x the 20-day average" if ratio >= 1.1 else "") + " — sellers are in charge.")
        elif down_share >= 0.55 or (ratio >= 1.3 and sma20 and price < sma20):
            out["distribution"] = _p("warn", f"{down_share * 100:.0f}% of recent volume on down days, activity {ratio:.1f}x average — supply is building.")
        else:
            out["distribution"] = _p("pass", f"{(1 - down_share) * 100:.0f}% of recent volume on up days, activity {ratio:.1f}x average — no distribution.")
        out["distribution"]["down_share"] = round(down_share, 3)
        out["distribution"]["volume_ratio"] = round(ratio, 2) if ratio is not None else None

        # 5. Bearish events and shapes — with the level each one names.
        heads = [r for r in pats if r.get("event_headline", True) and r.get("timeframe", "1D") == "1D"]
        bear_events = [r for r in heads if r.get("direction") == "bearish" and r.get("status") == "confirmed"
                       and r.get("category") in ("price_action", "candlestick")]
        bear_shapes = [r for r in heads if r.get("direction") == "bearish"
                       and r.get("category") in ("reversal", "triangle", "wedge", "channel", "continuation")]
        conf_shapes = [r for r in bear_shapes if r.get("status") == "confirmed"]
        form_shapes = [r for r in bear_shapes if r.get("status") == "forming"]

        def _age(r: dict) -> Optional[int]:
            a = _sessions_ago(r.get("break_date"), candles)
            return a if a is not None else r.get("age_days")

        fresh: list[dict] = []
        for r in bear_events + conf_shapes:
            a = _age(r)
            if a is not None and a <= FRESH_SESSIONS:
                fresh.append(r)
        red = [r for r in bear_events if r["pattern"] in RED_FLAGS or any(m in RED_FLAGS for m in _members(r, pats))]

        def _name(r: dict) -> str:
            lvl = r.get("neckline")
            return r["label"] + (f" at {lvl:.2f}" if lvl is not None else "") + (
                f" (target {r['target']:.2f})" if r.get("target") is not None else "")

        fresh_red = [r for r in fresh if r in red or r in conf_shapes]
        if fresh_red:
            out["bearish_events"] = _p("fail", "Fresh bearish signal on the tape: " + ", ".join(_name(r) for r in fresh_red[:3])
                                       + ". The buyers just failed at a level you can see on the chart.")
        elif conf_shapes:
            r0 = conf_shapes[0]
            out["bearish_events"] = _p("fail" if (stop is None or (r0.get("target") is not None and r0["target"] < (stop or 0))) else "warn",
                                       f"Confirmed bearish shape: {_name(r0)}." + (" Its measured target sits below your stop — the chart expects your stop to be hit." if stop is not None and r0.get("target") is not None and r0["target"] < stop else ""))
        elif red or bear_events:
            out["bearish_events"] = _p("warn", "Bearish events, not fresh: " + ", ".join(_name(r) for r in (red or bear_events)[:3]) + ".")
        elif form_shapes:
            out["bearish_events"] = _p("warn", f"Bearish shape forming: {_name(form_shapes[0])} — a close below {form_shapes[0]['neckline']:.2f} would confirm it.")
        else:
            out["bearish_events"] = _p("pass", "No confirmed bearish event or shape on the daily chart.")
        fresh_out = [{"pattern": r["pattern"], "label": r["label"], "neckline": r.get("neckline"),
                      "target": r.get("target"), "break_date": r.get("break_date"), "sessions_ago": _age(r),
                      "also_seen_as": r.get("also_seen_as") or []} for r in fresh_red]
        nearest_bear_trigger = None
        for r in bear_shapes + bear_events:
            lvl = r.get("neckline")
            if lvl is not None and lvl < price and (nearest_bear_trigger is None or lvl > nearest_bear_trigger["level"]):
                nearest_bear_trigger = {"level": round(lvl, 4), "label": r["label"], "status": r.get("status")}

        # 6. Exit plan — stop distance, structure stop, partial-exit ladder.
        wk_sup = (lv.get("weekly_supports") or [None])[0] if "error" not in lv else None
        cands: list[tuple[float, str]] = []
        for l in (lv.get("supports") or [])[:4]:
            if l.get("touches", 0) >= 2 and l["level"] <= price - 1.0 * atr:
                cands.append((l["level"], f"support {l['level']:.2f} tested {l['touches']}x" + (" (weekly zone)" if l.get("weekly") else "")))
        if wk_sup and wk_sup["level"] <= price - 1.0 * atr:
            cands.append((wk_sup["level"], f"weekly support {wk_sup['level']:.2f} tested {wk_sup['touches']}x"))
        struct = max(cands, key=lambda c: c[0]) if cands else None
        struct_stop = round(struct[0] - 0.5 * atr, 4) if struct is not None else None
        struct_txt = struct[1] if struct is not None else ""
        trail_to: Optional[float] = None
        trail_reason: Optional[str] = None
        if struct_stop is not None and struct_stop < price - 0.75 * atr and (stop is None or struct_stop > stop + 0.25 * atr):
            trail_to, trail_reason = struct_stop, f"just under {struct[1]}"
        ladder: list[dict] = []
        if held and stop is not None:
            dist_atr = (price - stop) / atr if atr else None
            be_stop = max(entry or stop, struct_stop or 0.0) if entry else (struct_stop or stop)
            if t1 is not None and price >= t1:
                ladder.append({"step": "reduce_now", "pct": PARTIAL_PCT, "qty": int(qty * PARTIAL_PCT / 100),
                               "at": round(price, 4), "why": f"target 1 ({t1:.2f}) reached"})
                ladder.append({"step": "stop_to", "level": round(be_stop, 4),
                               "why": "breakeven" if be_stop == entry else f"under structure ({be_stop:.2f})"})
                if t2 is not None:
                    ladder.append({"step": "final", "at": t2, "why": "target 2 — sell the rest or trail tight"})
            else:
                if t1 is not None:
                    ladder.append({"step": "reduce_at", "pct": PARTIAL_PCT, "qty": int(qty * PARTIAL_PCT / 100),
                                   "at": t1, "why": "target 1"})
                    ladder.append({"step": "then_stop_to", "level": round(be_stop, 4),
                                   "why": "breakeven" if be_stop == entry else f"under structure ({be_stop:.2f})"})
                if t2 is not None:
                    ladder.append({"step": "final", "at": t2, "why": "target 2"})
            txt = f"Stop {stop:.2f} is {dist_atr:.1f} ATR ({(price - stop) / price * 100:.1f}%) below the mark {price:.2f}."
            if trail_to is not None:
                txt += f" Raise it to {trail_to:.2f}, {trail_reason} — a stop at a level the market has respected beats one at an arbitrary distance."
            if t1 is not None and price >= t1:
                txt += f" Target 1 ({t1:.2f}) is reached: sell {PARTIAL_PCT}% ({int(qty * PARTIAL_PCT / 100)} shares) and move the stop to {be_stop:.2f}; the rest runs to {t2:.2f}." if t2 else \
                       f" Target 1 ({t1:.2f}) is reached: sell {PARTIAL_PCT}% ({int(qty * PARTIAL_PCT / 100)} shares) and move the stop to {be_stop:.2f}."
            elif t1 is not None:
                txt += f" Next step: sell {PARTIAL_PCT}% at {t1:.2f} (target 1), then stop to {be_stop:.2f}."
            if dist_atr is not None and dist_atr <= 1.0:
                out["exit_plan"] = _p("warn", txt + " Price is within one ATR of the stop — let the stop decide, do not pre-empt it and do not widen it.")
            elif dist_atr is not None and dist_atr > 4.0 and trail_to is not None:
                out["exit_plan"] = _p("warn", txt + " The stop is more than four ATR away — too loose for the trend you are in.")
            else:
                out["exit_plan"] = _p("pass", txt)
        elif held:
            out["exit_plan"] = _p("fail", "No stop on this position. Set one now: " + (f"under {struct_txt} at {struct_stop:.2f}." if struct_stop is not None else f"{price - 2 * atr:.2f} (two ATR below the mark)."))
        else:
            hyp = struct_stop if struct_stop is not None else round(price - 2 * atr, 4)
            out["exit_plan"] = _p("warn", f"Not held. If you owned it, the stop belongs at {hyp:.2f}" + (f", {struct_txt}." if struct is not None else " (two ATR below)."))
        out["exit_plan"]["struct_stop"] = struct_stop

        # Decision levels — the lines that end, reduce or protect the trade.
        exit_below, exit_reason = None, None
        if stop is not None:
            exit_below, exit_reason = stop, "your stop"
        elif struct_stop is not None:
            exit_below, exit_reason = struct_stop, f"levels-based stop, just under {struct_txt}"
        else:
            exit_below, exit_reason = round(price - 2.0 * atr, 4), "two ATR below the mark (no tested support nearby)"
        change_line = None
        if nearest_bear_trigger and (exit_below is None or nearest_bear_trigger["level"] > exit_below):
            change_line = nearest_bear_trigger
        reduce_at, reduce_reason = None, None
        if t1 is not None and price < t1:
            reduce_at, reduce_reason = t1, "target 1"
        elif t2 is not None and price < t2:
            reduce_at, reduce_reason = t2, "target 2"
        elif lv.get("nearest_resistance") and "error" not in lv:
            nr = lv["nearest_resistance"]
            reduce_at, reduce_reason = nr["level"], f"nearest resistance ({nr['source']})"
        decision = {
            "exit_below": exit_below, "exit_reason": exit_reason,
            "bearish_trigger": change_line,
            "reduce_at": round(reduce_at, 4) if reduce_at is not None else None, "reduce_reason": reduce_reason,
            "trail_stop_to": trail_to, "trail_reason": trail_reason,
            "ladder": ladder,
        }

        # Verdict
        fails = [k for k in PILLARS if out[k]["status"] == "fail"]
        warns = [k for k in PILLARS if out[k]["status"] == "warn"]
        against = len(fails)
        t1_hit = t1 is not None and price >= t1
        stopped = stop is not None and price <= stop
        if stopped:
            verdict = "exit"
            headline = f"Exit: mark {price:.2f} is at/below your stop {stop:.2f}. The plan already decided."
        elif ("thesis" in fails and "weekly" in fails) or against >= 3 or (against >= 2 and "bearish_events" in fails):
            verdict = "exit"
            headline = (f"Exit: {against} of 6 pillars say leave — " + ", ".join(LABELS[k].lower() for k in fails)
                        + (f". Sell into strength above {reduce_at:.2f} if it comes, otherwise at market; the trade ends below {exit_below:.2f}." if reduce_at and exit_below else "."))
        elif against >= 1 or t1_hit:
            verdict = "reduce"
            bits = []
            if t1_hit:
                bits.append(f"take {PARTIAL_PCT}% here (target 1 {t1:.2f} reached)")
            elif reduce_at:
                bits.append(f"take {PARTIAL_PCT}% at {reduce_at:.2f} ({reduce_reason})")
            if trail_to is not None:
                bits.append(f"stop to {trail_to:.2f} ({trail_reason})")
            elif exit_below is not None:
                bits.append(f"full exit below {exit_below:.2f}")
            headline = ("Reduce: " + (", ".join(LABELS[k].lower() for k in fails) + " is against you — " if fails else "")
                        + "; ".join(bits) + ".")
        else:
            verdict = "hold"
            headline = (f"Hold: nothing broken ({6 - len(warns)} of 6 pillars healthy" + (", " + ", ".join(LABELS[k].lower() for k in warns) + " unclear" if warns else "") + ")."
                        + (f" Exit line {exit_below:.2f} ({exit_reason})." if exit_below is not None else "")
                        + (f" A close below {change_line['level']:.2f} ({change_line['label']}) would change the picture." if change_line else "")
                        + (f" Raise the stop to {trail_to:.2f}, {trail_reason}." if trail_to is not None else ""))
        return {
            "symbol": sym, "held": held, "price": round(price, 4), "verdict": verdict, "headline": headline,
            "against": against, "pillars": [{"key": k, "label": LABELS[k], **out[k]} for k in PILLARS],
            "decision_levels": decision, "fresh_bearish": fresh_out,
            "position": ({"entry": entry, "stop": stop, "target1": t1, "target2": t2, "qty": qty} if held else None),
            "as_of": str(candles[-1]["time"]),
            "basis": ("Holder's view on Yahoo daily candles. Thesis = price vs 20/50-day averages, swing structure and "
                      "the score you bought on; Weekly = 10/40-week averages and swing structure; Relative strength = "
                      "1- and 3-month return vs EGX30; Distribution = down-day share of 20-session volume; Bearish "
                      "events = the pattern scanner, fresh = within 3 sessions; Exit plan = stop distance in ATR, "
                      "a stop under the nearest tested support, and a partial-exit ladder from your own targets."),
            "computed_at": datetime.now(CAIRO).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sell_checklist failed")
        return {"symbol": symbol, "error": str(exc)}


def _members(head: dict, rows: list[dict]) -> list[str]:
    eid = head.get("event_id")
    if eid is None:
        return []
    return [r["pattern"] for r in rows if r.get("event_id") == eid and r is not head]


def compact(sc: dict) -> Optional[dict]:
    """The slice the Guardian attaches to each position row."""
    if not isinstance(sc, dict) or "error" in sc:
        return None
    return {
        "verdict": sc.get("verdict"), "headline": sc.get("headline"), "against": sc.get("against"),
        "pillars": {p["key"]: p["status"] for p in sc.get("pillars") or []},
        "decision_levels": sc.get("decision_levels"), "fresh_bearish": sc.get("fresh_bearish") or [],
    }
