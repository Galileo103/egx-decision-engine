"""Six-pillar decision checklist for one stock:

    Trend → Support/Resistance → Volume → Price action → Patterns → Risk plan

Each pillar gets PASS / WARN / FAIL with one sentence of evidence, drawn from
the app's own modules on Yahoo daily candles (so it answers instantly and
survives TradingView pauses). The overall verdict counts the pillars and
names what is missing — the point is to stop a buy that has two crosses,
not to bless one that has six ticks.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import settings

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

PILLARS = ("trend", "support_resistance", "volume", "price_action", "patterns", "risk")
LABELS = {
    "trend": "Trend", "support_resistance": "Support / resistance", "volume": "Volume",
    "price_action": "Price action", "patterns": "Patterns", "risk": "Risk plan",
}


def _p(status: str, text: str, **extra: Any) -> dict:
    return {"status": status, "text": text, **extra}


def _member_keys(head: dict, rows: list[dict]) -> list[str]:
    """Pattern keys of the non-headline rows clustered with ``head``."""
    eid = head.get("event_id")
    if eid is None:
        return []
    return [r["pattern"] for r in rows if r.get("event_id") == eid and r is not head]


def checklist(symbol: str) -> dict:
    """Run the six pillars for one symbol. Never raises."""
    try:
        from app.services import leaders, levels, patterns, weekly
        from app.services.rules_backtest import Ind

        sym = str(symbol or "").upper().strip().split(":")[-1]
        candles = leaders.daily_candles(sym)
        if len(candles) < 120:
            return {"symbol": sym, "error": f"not enough daily history ({len(candles)} bars)"}
        x = Ind(candles)
        price = x.c[-1]
        atr = x.atr[-1] or price * 0.02
        lv = levels.compute(sym, candles)
        pats = patterns.detect(sym, candles).get("patterns") or []
        out: dict[str, dict] = {}

        # 1. Trend — daily first, then the weekly context (daily candles resampled).
        sma20, sma50 = x.sma20[-1], x.sma50[-1]
        sma50_prev = x.sma50[-11] if len(x.c) > 11 else None
        structure = next((r for r in pats if r["pattern"] in ("higher_high_higher_low", "lower_high_lower_low")), None)
        rising50 = sma50 is not None and sma50_prev is not None and sma50 > sma50_prev
        if sma20 and sma50 and price > sma50 and sma20 > sma50:
            txt = f"Price {price:.2f} above the 50-day average ({sma50:.2f}) and the 20-day is above the 50-day"
            txt += ", 50-day rising" if rising50 else ", 50-day still flat"
            if structure and structure["pattern"] == "higher_high_higher_low":
                txt += "; swing structure makes higher highs and higher lows."
                out["trend"] = _p("pass", txt)
            elif structure and structure["pattern"] == "lower_high_lower_low":
                out["trend"] = _p("warn", txt + "; but the recent swings are lower highs and lower lows — the trend is tiring.")
            else:
                out["trend"] = _p("pass", txt + ".")
        elif sma50 and price < sma50 and sma20 and sma20 < sma50:
            out["trend"] = _p("fail", f"Price {price:.2f} below the 50-day average ({sma50:.2f}) and the 20-day is below the 50-day — a downtrend. Buying against it needs a reason.")
        else:
            out["trend"] = _p("warn", f"Mixed: price {price:.2f}, 20-day {sma20:.2f}, 50-day {sma50:.2f}. No clear trend yet." if sma20 and sma50 else "Not enough history for the averages.")
        wk = weekly.context(candles)
        if "error" not in wk:
            out["trend"]["text"] += " " + wk["text"]
            # A daily uptrend inside a weekly downtrend is a bounce, not a trend.
            if (out["trend"]["status"] in ("pass", "warn") and wk["trend"] == "down"
                    and sma50 and price > sma50):
                out["trend"]["status"] = "warn"
                out["trend"]["text"] += " Treat the daily uptrend as a counter-trend bounce."
            elif out["trend"]["status"] == "fail" and wk["trend"] == "up":
                out["trend"]["text"] += " A pullback inside a larger uptrend — watch for the daily trend to turn back up."
            out["trend"]["weekly"] = {k: wk.get(k) for k in ("trend", "structure", "sma10", "sma40", "above_sma10",
                                                                "above_sma40", "sma40_rising", "bars", "as_of")}

        # 2. Support / resistance
        pos = lv.get("position")
        near_s, near_r = lv.get("nearest_support"), lv.get("nearest_resistance")
        wk_note = ""
        for side, lvl in (("support", near_s), ("resistance", near_r)):
            if lvl and lvl.get("weekly"):
                wk_note = f" The nearest {side} {lvl['level']:.2f} is also a weekly zone (tested {lvl.get('weekly_touches', 0)}x on the weekly chart) — the larger trend respects it."
                break
        if "error" in lv:
            out["support_resistance"] = _p("warn", "Levels unavailable.")
        elif pos == "at support":
            out["support_resistance"] = _p("pass", lv["note"])
        elif pos == "breaking out":
            out["support_resistance"] = _p("pass", lv["note"] + " Breakouts need volume (see below).")
        elif pos == "at resistance":
            out["support_resistance"] = _p("fail", lv["note"])
        else:
            room_up = lv.get("room_up_pct") or 0.0
            room_dn = lv.get("room_down_pct") or 0.0
            if near_r and near_s and room_up >= 2 * room_dn and room_up >= 5:
                out["support_resistance"] = _p("pass", f"Mid-range but favourable: {room_up:.1f}% of room up to resistance {near_r['level']:.2f} versus {room_dn:.1f}% down to support {near_s['level']:.2f}.")
            else:
                out["support_resistance"] = _p("warn", (lv.get("note") or "Mid-range.") + (f" Room up {room_up:.1f}%, room down {room_dn:.1f}% — not an edge." if near_r and near_s else ""))
        if wk_note and "error" not in lv:
            out["support_resistance"]["text"] += wk_note

        # 3. Volume
        v20 = x.vavg[-1] or 0.0
        recent = sum(x.v[-5:]) / 5.0 if v20 else 0.0
        ratio = recent / v20 if v20 else None
        up_vol = sum(x.v[i] for i in range(len(x.c) - 20, len(x.c)) if x.c[i] > x.c[i - 1])
        tot_vol = sum(x.v[-20:]) or 1.0
        up_share = up_vol / tot_vol
        if ratio is None:
            out["volume"] = _p("warn", "No volume data.")
        elif up_share >= 0.55 and ratio >= 1.0:
            out["volume"] = _p("pass", f"{up_share * 100:.0f}% of the last 20 sessions' volume traded on up days, and this week runs at {ratio:.1f}x the 20-day average — buyers are doing the work.")
        elif up_share <= 0.40 and ratio >= 1.1:
            out["volume"] = _p("fail", f"Only {up_share * 100:.0f}% of recent volume traded on up days while activity is {ratio:.1f}x normal — heavy selling.")
        elif ratio < 0.7:
            out["volume"] = _p("warn", f"Volume this week is {ratio:.1f}x the 20-day average — quiet. Breakouts on quiet volume tend to fail.")
        else:
            out["volume"] = _p("warn", f"{up_share * 100:.0f}% of recent volume on up days, activity {ratio:.1f}x average — no clear message from volume.")

        # 4. Price action (events + candlesticks on the last sessions)
        # One event, several names (False Breakout + Bull Trap, HH/HL + BOS…): the
        # scanner clusters them; count and name events, not rows.
        events = [r for r in pats if r["category"] in ("price_action", "candlestick") and r["status"] == "confirmed"
                  and r.get("event_headline", True) and r.get("timeframe", "1D") == "1D"]  # weekly rows feed Trend
        bull = [r for r in events if r["direction"] == "bullish"]
        bear = [r for r in events if r["direction"] == "bearish"]
        red_names = {"bull_trap", "false_breakout", "change_of_character", "failed_retest", "upthrust"}
        red_flags = [r for r in bear if r["pattern"] in red_names
                     or any(m in red_names for m in _member_keys(r, pats))]

        def names(rs: list[dict]) -> str:
            parts = []
            for r in rs[:3]:
                also = r.get("also_seen_as") or []
                parts.append(r["label"] + (f" (also seen as {', '.join(also)})" if also else ""))
            return ", ".join(parts)

        def n_ev(rs: list[dict]) -> str:
            return f"{len(rs)} event" + ("" if len(rs) == 1 else "s")

        if red_flags:
            out["price_action"] = _p("fail", f"Bearish reversal on the tape — {n_ev(red_flags)}: {names(red_flags)}." + (f" Bullish — {n_ev(bull)}: {names(bull)}." if bull else ""))
        elif len(bull) > len(bear) and bull:
            out["price_action"] = _p("pass", f"Bullish — {n_ev(bull)}: {names(bull)}." + (f" Bearish — {n_ev(bear)}: {names(bear)}." if bear else ""))
        elif bear and len(bear) > len(bull):
            out["price_action"] = _p("fail", f"Bearish events outnumber bullish — {n_ev(bear)}: {names(bear)}.")
        else:
            out["price_action"] = _p("warn", "No decisive price-action event on the last sessions." + (f" ({names(bull + bear)})" if bull or bear else ""))

        # 5. Patterns (chart shapes)
        shapes = [r for r in pats if r["category"] in ("reversal", "triangle", "wedge", "channel", "continuation")]
        conf_bull = [r for r in shapes if r["status"] == "confirmed" and r["direction"] == "bullish"]
        conf_bear = [r for r in shapes if r["status"] == "confirmed" and r["direction"] == "bearish"]
        form_bull = [r for r in shapes if r["status"] == "forming" and r["direction"] == "bullish"]
        form_bear = [r for r in shapes if r["status"] == "forming" and r["direction"] == "bearish"]
        if conf_bear and not conf_bull:
            out["patterns"] = _p("fail", f"Confirmed bearish shape: {names(conf_bear)} (target {conf_bear[0]['target']:.2f}).")
        elif conf_bull:
            r0 = conf_bull[0]
            out["patterns"] = _p("pass", f"Confirmed bullish shape: {names(conf_bull)} — target {r0['target']:.2f} ({r0['target_pct']:+.1f}%), {r0.get('move_progress_pct') or 0:.0f}% of the move done." + (f" Watch: bearish {names(conf_bear)}." if conf_bear else ""))
        elif form_bull:
            out["patterns"] = _p("warn", f"Forming (not yet confirmed): {names(form_bull)} — trigger {form_bull[0]['neckline']:.2f}." + (f" Bearish forming: {names(form_bear)}." if form_bear else ""))
        elif form_bear:
            out["patterns"] = _p("warn", f"Bearish shape forming: {names(form_bear)} — trigger {form_bear[0]['neckline']:.2f}.")
        else:
            out["patterns"] = _p("warn", "No chart pattern on the daily chart right now (neutral).")

        # 6. Risk plan (levels-based, instant): stop under support, target at resistance.
        stop = (near_s["level"] - 0.5 * atr) if near_s else price - 2.0 * atr
        stop = min(stop, price - 0.75 * atr)                       # never absurdly tight
        target = near_r["level"] if near_r and near_r["level"] > price + 0.5 * atr else price + 3.0 * (price - stop)
        risk_ps = price - stop
        rr = (target - price) / risk_ps if risk_ps > 0 else None
        stop_pct = risk_ps / price * 100.0
        liquidity = None
        try:
            from app.services.market import median_daily_value

            liquidity = median_daily_value(sym)
        except Exception:  # noqa: BLE001
            pass
        vals = sorted(x.c[i] * x.v[i] for i in range(len(x.c) - 20, len(x.c)))
        median_value = vals[len(vals) // 2] if vals else None
        liq_ok = (liquidity if liquidity is not None else median_value or 0) >= settings.min_daily_value_egp
        account = float(settings.account_size) or 0.0
        shares = int((account * settings.risk_pct / 100.0) // risk_ps) if risk_ps > 0 and account else 0
        risk_txt = (f"Plan: buy ~{price:.2f}, stop {stop:.2f} ({stop_pct:.1f}% away" + (f", under support {near_s['level']:.2f}" if near_s else "") +
                    f"), first target {target:.2f} → {rr:.1f}R. " if rr is not None else "Plan: no valid stop. ")
        if account and shares:
            risk_txt += f"At {settings.risk_pct:g}% risk that is {shares} shares (~{shares * price:,.0f} EGP). "
        if not liq_ok:
            risk_txt += f"Illiquid: median daily value ~{(liquidity or median_value or 0):,.0f} EGP is below the {settings.min_daily_value_egp:,.0f} floor."
            out["risk"] = _p("fail", risk_txt)
        elif rr is None or rr < 1.0:
            out["risk"] = _p("fail", risk_txt + "Less than 1R of room to the first resistance — the reward does not pay for the risk here.")
        elif rr < 2.0 or stop_pct > 10:
            out["risk"] = _p("warn", risk_txt + ("Under 2R: acceptable only with a strong trend. " if rr < 2 else "") + ("The stop is more than 10% away — one limit-down session could gap through it." if stop_pct > 10 else ""))
        else:
            out["risk"] = _p("pass", risk_txt + "Reward covers the risk twice or more with a stop at a real level.")
        risk_plan = {"entry": round(price, 4), "stop": round(stop, 4), "target": round(target, 4),
                     "rr": round(rr, 2) if rr is not None else None, "stop_pct": round(stop_pct, 2),
                     "shares_at_risk_pct": shares, "liquid": liq_ok}

        passes = [k for k in PILLARS if out[k]["status"] == "pass"]
        fails = [k for k in PILLARS if out[k]["status"] == "fail"]
        warns = [k for k in PILLARS if out[k]["status"] == "warn"]
        score = len(passes)
        if fails and ("trend" in fails or "risk" in fails or len(fails) >= 2):
            verdict = "no_setup"
            headline = f"Not a setup: {len(fails)} pillar{'s' if len(fails) != 1 else ''} against it — " + ", ".join(LABELS[k].lower() for k in fails) + "."
        elif score >= 5 and not fails:
            verdict = "setup"
            headline = f"Setup: {score} of 6 pillars in favour" + (f", only {LABELS[warns[0]].lower()} unclear." if warns else ".")
        elif score >= 3 and not fails:
            verdict = "watch"
            headline = f"Watch, don't chase: {score} of 6 in favour; unclear on " + ", ".join(LABELS[k].lower() for k in warns) + "."
        elif fails and score >= 3:
            verdict = "watch"
            headline = f"Caution: {LABELS[fails[0]].lower()} is against it; {score} of 6 in favour."
        elif fails:
            verdict = "no_setup"
            headline = f"Not a setup: {LABELS[fails[0]].lower()} is against it and only {score} of 6 in favour."
        else:
            verdict = "no_setup"
            headline = f"Nothing to act on: only {score} of 6 pillars in favour."
        missing = [LABELS[k] for k in PILLARS if out[k]["status"] != "pass"]
        return {
            "symbol": sym, "price": round(price, 4), "score": score, "verdict": verdict, "headline": headline,
            "missing": missing, "pillars": [{"key": k, "label": LABELS[k], **out[k]} for k in PILLARS],
            "risk_plan": risk_plan, "levels_position": pos, "as_of": str(candles[-1]["time"]),
            "basis": ("Yahoo daily candles. Trend = price vs 50-day and 20-day averages + swing structure; S/R = "
                      "tested zones; Volume = up-day share and this week vs 20-day average; Price action & "
                      "Patterns = the pattern scanner; Risk = stop under the nearest support, first target at the "
                      "nearest resistance, liquidity floor."),
            "computed_at": datetime.now(CAIRO).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("checklist failed")
        return {"symbol": symbol, "error": str(exc)}
