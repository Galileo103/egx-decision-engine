"""Proven edge — one table that says which of the app's rules, scanners and
patterns actually made money on EGX history, and which did not.

Three kinds of rows, one vocabulary:

* ``rule``     — an entry rule of the rules backtester traded universe-wide
                 with the Guardian's exits (the trade you would actually take):
                 trades, win rate, average R (= expectancy per unit of risk).
* ``scanner``  — a live scanner or replayed proxy rule graded by the Scorecard:
                 10-session beat rate vs EGX30 and average excess return.
* ``pattern``  — a confirmed chart pattern graded the same way.

Every row gets a verdict in plain words — ``edge`` / ``marginal`` / ``negative``
/ ``too_few`` — so the reader does not have to interpret a beat rate. The
thresholds are deliberately modest and stated in ``basis``: an edge is not a
profit guarantee, it is "did better than the index more often than not, on a
sample big enough to mean something".

``compute`` is slow (four universe backtests); it runs in a background job or
from the weekly maintenance job and persists to ``proven_edge``. ``latest``
is the instant read the dashboard uses.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app import db
from app.services.bgjob import BackgroundJob

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

MIN_SAMPLE = 20
#: rule verdicts (average R per trade after fees and slippage)
RULE_EDGE_R, RULE_MARGINAL_R = 0.20, 0.0
#: scanner / pattern verdicts are RELATIVE to a random entry over the same
#: universe and window: the signal's average excess (signed so that a bearish
#: signal is right when the stock falls) must exceed the random-entry excess by
#: at least EXCESS_EDGE_PP and by two standard errors, and its right-way rate
#: must not be below the random rate. Symmetric on the downside.
EXCESS_EDGE_PP = 0.5
RATE_TOLERANCE_PP = 3.0
HORIZON = 10

VERDICT_TEXT = {
    "edge": "Proven edge on this sample",
    "marginal": "Coin flip — no reliable edge",
    "negative": "Worse than the index — avoid or downweight",
    "too_few": "Too few signals to judge",
}

job = BackgroundJob("edge")


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


# ── verdict helpers (pure) ───────────────────────────────────────────────────


def rule_verdict(n: Optional[int], avg_r: Optional[float]) -> str:
    if not n or n < MIN_SAMPLE or avg_r is None:
        return "too_few"
    if avg_r >= RULE_EDGE_R:
        return "edge"
    if avg_r > RULE_MARGINAL_R:
        return "marginal"
    return "negative"


def beat_verdict(n: Optional[int], rate_vs_random_pp: Optional[float],
                 excess_vs_random: Optional[float], se_excess: Optional[float] = None) -> str:
    """Verdict for a graded signal, relative to a random entry.

    ``rate_vs_random_pp``: right-way rate minus the random-entry rate (points).
    ``excess_vs_random``: signed average excess minus the random-entry excess (%).
    ``se_excess``: standard error of the signal's excess — the bar a difference must
    clear (2 SE) before a few lucky trades can call themselves an edge.
    """
    if not n or n < MIN_SAMPLE or excess_vs_random is None:
        return "too_few"
    bar = max(EXCESS_EDGE_PP, 2.0 * (se_excess or 0.0))
    rate = rate_vs_random_pp if rate_vs_random_pp is not None else 0.0
    if excess_vs_random >= bar and rate > -RATE_TOLERANCE_PP:
        return "edge"
    if excess_vs_random <= -bar or rate <= -RATE_TOLERANCE_PP:
        return "negative"
    return "marginal"


def compute_baseline(universe: str = "EGX100", period: str = "5y", horizon: int = HORIZON) -> dict:
    """What a RANDOM long entry did over ``horizon`` sessions on every stock and session
    of the universe, versus EGX30 — the yardstick every signal is measured against.

    On EGX single-stock returns are skewed (median session lags the index, a few fly),
    so the random beat rate sits well under 50%; judging signals against 50% would
    condemn everything. Never raises.
    """
    try:
        from app.services import leaders, rules_backtest as RB
        from app.symbols import universe as universe_symbols

        bench = leaders.benchmark_series(range_="5y")
        if not bench.get("dates"):
            bench = leaders.benchmark_series()
        bars = RB.PERIOD_BARS.get(period, 1250)
        rng = "5y" if bars > 500 else ("2y" if bars > 250 else "1y")
        xs: list[float] = []
        symbols = 0
        syms = universe_symbols(universe)
        job.progress(phase="baseline", done=0, total=len(syms))
        for k, s in enumerate(syms):
            job.progress(done=k, detail=s)
            c = leaders.daily_candles(s, rng)
            if len(c) < 200:
                continue
            c = c[-(bars + 60):]
            symbols += 1
            for i in range(150, len(c) - horizon):
                b = leaders.benchmark_return(bench, str(c[i]["time"]), str(c[i + horizon]["time"]))
                if b is None:
                    continue
                try:
                    xs.append((float(c[i + horizon]["close"]) / float(c[i]["close"]) - 1.0 - b) * 100.0)
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
        if len(xs) < 500:
            return {"error": f"baseline too thin ({len(xs)} sessions)", "sessions": len(xs)}
        xs.sort()
        n = len(xs)
        return {
            "horizon": horizon, "universe": universe, "period": period, "symbols": symbols, "sessions": n,
            "beat_rate": round(sum(1 for x in xs if x > 0) / n * 100.0, 1),
            "under_rate": round(sum(1 for x in xs if x < 0) / n * 100.0, 1),
            "avg_excess": round(sum(xs) / n, 2), "median_excess": round(xs[n // 2], 2),
            "benchmark": bench.get("source"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("compute_baseline failed")
        return {"error": str(exc)}


def _pattern_label(name: str) -> str:
    try:
        from app.services import pattern_catalog

        info = pattern_catalog.info(name)
        if isinstance(info, dict) and info.get("label"):
            return str(info["label"])
    except Exception:  # noqa: BLE001
        pass
    return name.replace("_", " ")


# ── compute ──────────────────────────────────────────────────────────────────


def _rule_rows(universe: str, period: str, exit_rule: str) -> list[dict]:
    from app.services import rules_backtest as RB

    rows: list[dict] = []
    rules = list(RB.ENTRY_RULES)
    job.progress(phase="rules", done=0, total=len(rules))
    for k, rule in enumerate(rules):
        job.progress(done=k, detail=RB.ENTRY_RULES[rule]["label"])
        res = RB.universe_run(universe, rule, exit_rule, period, limit=200)
        pooled = (res.get("pooled") or {}) if isinstance(res, dict) else {}
        n = int(pooled.get("trades") or 0)
        avg_r = pooled.get("avg_r")
        win = pooled.get("win_rate")
        traded = int(pooled.get("symbols_traded") or 0)
        beat_bh = int(pooled.get("symbols_beat_buy_hold") or 0)
        verdict = rule_verdict(n, avg_r) if "error" not in res else "too_few"
        rows.append({
            "kind": "rule", "name": rule, "label": RB.ENTRY_RULES[rule]["label"],
            "period": period, "n": n, "hit_rate": win, "edge_metric": avg_r,
            "metric_label": "avg R per trade",
            "verdict": verdict, "verdict_text": VERDICT_TEXT[verdict],
            "extra": {
                "exit_rule": exit_rule, "symbols_traded": traded, "symbols_beat_buy_hold": beat_bh,
                "median_stock_return_pct": pooled.get("median_return_pct"),
                "universe": universe, "error": res.get("error") if isinstance(res, dict) else None,
                "summary": res.get("summary") if isinstance(res, dict) else None,
            },
        })
    return rows


def _scorecard_rows() -> list[dict]:
    from app.services import scorecard

    card = scorecard.scorecard()
    rows: list[dict] = []
    if not isinstance(card, dict) or "error" in card:
        return rows
    for name, sc in (card.get("scanners") or {}).items():
        h10 = (sc.get("horizons") or {}).get(str(HORIZON)) or {}
        h20 = (sc.get("horizons") or {}).get("20") or {}
        n = int(h10.get("n") or 0)
        beat, excess = h10.get("beat_rate"), h10.get("avg_excess")
        kind = ("pattern" if str(name).startswith("pattern_") else
                "checklist" if str(name).startswith("checklist_") else "scanner")
        verdict = beat_verdict(n, h10.get("beat_vs_random_pp"), h10.get("excess_vs_random"),
                               h10.get("se_excess"))
        label = (_pattern_label(str(name)[len("pattern_"):]) if kind == "pattern" else
                 "Checklist verdict: " + str(name)[len("checklist_"):].replace("_", " ").upper()
                 if kind == "checklist" else str(name).replace("_", " "))
        rows.append({
            "kind": kind, "name": name, "label": label, "period": "graded history",
            "n": n, "hit_rate": beat, "edge_metric": excess,
            "metric_label": ("avg excess vs EGX30 over 10 sessions, % (signed: + = the stock moved the "
                             "signal's way)"),
            "verdict": verdict, "verdict_text": VERDICT_TEXT[verdict],
            "extra": {
                "direction": sc.get("direction"), "rate_vs_random_pp": h10.get("beat_vs_random_pp"),
                "excess_vs_random": h10.get("excess_vs_random"), "se_excess": h10.get("se_excess"),
                "win_rate_10": h10.get("win_rate"), "n_20": h20.get("n"), "beat_20": h20.get("beat_rate"),
                "excess_20": h20.get("avg_excess"), "weight": sc.get("weight"),
                "weight_basis": sc.get("weight_basis"), "proxy": sc.get("proxy"),
                "sources": sc.get("sources"),
            },
        })
    return rows


def _baseline_row(b: dict, universe: str) -> dict:
    return {
        "kind": "baseline", "name": f"random_entry_{b.get('horizon', HORIZON)}d",
        "label": "Random entry (any stock, any session)", "period": str(b.get("period")),
        "n": b.get("sessions"), "hit_rate": b.get("beat_rate"), "edge_metric": b.get("avg_excess"),
        "metric_label": "avg excess vs EGX30 over 10 sessions, %", "verdict": "baseline",
        "verdict_text": "The yardstick: what buying at random did", "extra": {**b, "universe": universe},
    }


def _persist(rows: list[dict], universe: str, wipe: bool = True) -> None:
    now = _now_iso()
    if wipe:
        db.execute("DELETE FROM proven_edge")
    db.executemany(
        "INSERT OR REPLACE INTO proven_edge (kind, name, label, period, n, hit_rate, edge_metric, "
        " metric_label, verdict, verdict_text, extra_json, universe, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["kind"], r["name"], r["label"], r["period"], r["n"], r["hit_rate"], r["edge_metric"],
          r["metric_label"], r["verdict"], r["verdict_text"], json.dumps(r.get("extra") or {}),
          universe, now) for r in rows],
    )


def _summary(rows: list[dict]) -> dict:
    by_verdict: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    rows = [r for r in rows if r.get("kind") != "baseline"]
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    edge = sorted([r for r in rows if r["verdict"] == "edge"],
                  key=lambda r: (r.get("edge_metric") or 0), reverse=True)
    negative = sorted([r for r in rows if r["verdict"] == "negative"],
                      key=lambda r: (r.get("edge_metric") or 0))
    return {
        "rows": len(rows), "by_verdict": by_verdict, "by_kind": by_kind,
        "best": [{"kind": r["kind"], "name": r["name"], "label": r["label"], "n": r["n"],
                  "edge_metric": r["edge_metric"]} for r in edge[:5]],
        "worst": [{"kind": r["kind"], "name": r["name"], "label": r["label"], "n": r["n"],
                   "edge_metric": r["edge_metric"]} for r in negative[:5]],
    }


def checklist_summary(rows: list[dict], base: Optional[dict] = None) -> Optional[dict]:
    """Does a SETUP verdict actually beat a NO SETUP? Built from the checklist rows."""
    by = {r["name"]: r for r in rows if r.get("kind") == "checklist"}
    if not by:
        return None
    def _get(v: str) -> dict:
        r = by.get(f"checklist_{v}") or {}
        x = r.get("extra") or {}
        return {"n": r.get("n") or 0, "right_rate": r.get("hit_rate"), "avg_excess": r.get("edge_metric"),
                "excess_vs_random": x.get("excess_vs_random"), "rate_vs_random_pp": x.get("rate_vs_random_pp"),
                "verdict": r.get("verdict")}
    setup, watch, no = _get("setup"), _get("watch"), _get("no_setup")
    spread = None
    if setup["avg_excess"] is not None and no["avg_excess"] is not None:
        spread = round(setup["avg_excess"] - no["avg_excess"], 2)
    enough = setup["n"] >= MIN_SAMPLE and no["n"] >= MIN_SAMPLE
    if not enough:
        verdict, text = "too_few", (f"Too few graded verdicts yet ({setup['n']} SETUP, {no['n']} NO SETUP) — run the "
                                  "replay with the checklist option.")
    elif spread is not None and spread >= 1.0 and (setup["excess_vs_random"] or 0) > 0:
        verdict, text = "edge", (f"The checklist works: over the next 10 sessions a SETUP beat EGX30 by "
                               f"{setup['avg_excess']:+.2f}% on average ({setup['n']} verdicts) versus "
                               f"{no['avg_excess']:+.2f}% for a NO SETUP ({no['n']}) — a {spread:+.2f}-point gap, and "
                               f"{setup['excess_vs_random']:+.2f} above a random buy.")
    elif spread is not None and spread > 0:
        verdict, text = "marginal", (f"SETUP edges NO SETUP by only {spread:+.2f} points over 10 sessions "
                                   f"({setup['n']} vs {no['n']} verdicts) — the checklist sorts, but weakly.")
    else:
        verdict, text = "negative", (f"SETUP did not beat NO SETUP over 10 sessions ({spread:+.2f} points, "
                                   f"{setup['n']} vs {no['n']} verdicts) — the pillars need recalibrating."
                                   if spread is not None else "Checklist verdicts could not be compared.")
    return {"setup": setup, "watch": watch, "no_setup": no, "spread_10d": spread, "verdict": verdict,
            "verdict_text": VERDICT_TEXT.get(verdict, verdict), "text": text,
            "random_excess": (base or {}).get("avg_excess")}


def _headline(rows: list[dict], base: Optional[dict] = None) -> str:
    s = _summary(rows)
    rows = [r for r in rows if r.get("kind") != "baseline"]
    judged = [r for r in rows if r["verdict"] != "too_few"]
    if not rows:
        return "Nothing measured yet — run the historical replay, then refresh."
    if not judged:
        return (f"{len(rows)} rules/signals measured, none with {MIN_SAMPLE}+ samples yet — "
                "the replay fills this in.")
    n_edge = s["by_verdict"].get("edge", 0)
    n_neg = s["by_verdict"].get("negative", 0)
    best = s["best"][0] if s["best"] else None
    parts = [f"Of {len(judged)} rules and signals with enough history, {n_edge} beat a random entry, "
             f"{n_neg} do worse than one."]
    if base and base.get("beat_rate") is not None:
        parts.append(f"Yardstick: a random buy beats EGX30 only {base['beat_rate']:.0f}% of the time "
                     f"over 10 sessions here, so rates are judged against that, not 50%.")
    if best:
        parts.append(f"Strongest: {best['label']} ({best['n']} samples).")
    if n_neg:
        parts.append("Negative ones are downweighted in Candidates and should not be traded on their own.")
    return " ".join(parts)


def compute(universe: str = "EGX100", period: str = "3y", exit_rule: str = "guardian",
            persist: bool = True, include_rules: bool = True) -> dict:
    """Recompute the whole edge table. Slow (minutes). Never raises."""
    try:
        started = time.monotonic()
        rows: list[dict] = []
        # 1. The yardstick first: it must be stored before the Scorecard reads it.
        base = compute_baseline(universe, "5y")
        if "error" not in base:
            if persist:
                db.execute("DELETE FROM proven_edge WHERE kind = 'baseline'")
                _persist([_baseline_row(base, universe)], universe, wipe=False)
            from app.services import scorecard
            scorecard.invalidate_weights()
        if include_rules:
            rows.extend(_rule_rows(universe, period, exit_rule))
        job.progress(phase="scorecard", detail=None)
        rows.extend(_scorecard_rows())
        if "error" not in base:
            rows.append(_baseline_row(base, universe))
        if persist:
            _persist(rows, universe)
        out = {
            "rows": rows, "summary": _summary(rows), "headline": _headline(rows, base),
            "baseline": base if "error" not in base else None,
            "checklist": checklist_summary(rows, base if "error" not in base else None),
            "universe": universe, "period": period, "exit_rule": exit_rule,
            "elapsed_s": round(time.monotonic() - started, 1), "as_of": _now_iso(),
            "basis": _basis(),
        }
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("edge.compute failed")
        return {"error": str(exc)}


def _basis() -> str:
    return (
        f"Rules: every stock in the universe, entries at the next open, Guardian exits, fees and "
        f"slippage included; 'edge' = average R of at least {RULE_EDGE_R:+.2f} over {MIN_SAMPLE}+ trades, "
        f"'negative' = average R at or below zero. Scanners and patterns: 10-session close-to-close "
        "return after the signal versus EGX30, signed so a bearish signal is right when the stock "
        "falls, and compared with a RANDOM entry over the same stocks and years; 'edge' = average "
        f"excess at least {EXCESS_EDGE_PP:.1f} points above random and beyond two standard errors, "
        "with a right-way rate not below random; 'negative' = the mirror image. Rows marked replay come "
        "from the historical replay; live rows accumulate as the scanners run. Past edge is a "
        "reason to keep a rule, not a promise about the next trade."
    )


def latest() -> dict:
    """Stored edge table (instant). Empty rows when never computed."""
    try:
        recs = db.query("SELECT * FROM proven_edge ORDER BY kind, verdict, n DESC")
        rows: list[dict] = []
        as_of: Optional[str] = None
        universe: Optional[str] = None
        for r in recs:
            try:
                extra = json.loads(r.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            rows.append({
                "kind": r["kind"], "name": r["name"], "label": r["label"], "period": r["period"],
                "n": r["n"], "hit_rate": r["hit_rate"], "edge_metric": r["edge_metric"],
                "metric_label": r["metric_label"], "verdict": r["verdict"],
                "verdict_text": r["verdict_text"], "extra": extra,
            })
            as_of = as_of or r.get("computed_at")
            universe = universe or r.get("universe")
        base_rows = [r for r in rows if r["kind"] == "baseline"]
        rows = [r for r in rows if r["kind"] != "baseline"]
        base = base_rows[0]["extra"] if base_rows else None
        order = {"edge": 0, "marginal": 1, "negative": 2, "too_few": 3}
        rows.sort(key=lambda x: ({"rule": 0, "checklist": 1, "scanner": 2, "pattern": 3}.get(x["kind"], 9),
                                 order.get(x["verdict"], 9),
                                 -((x.get("extra") or {}).get("excess_vs_random") or x.get("edge_metric") or 0)))
        return {"rows": rows, "summary": _summary(rows), "headline": _headline(rows, base),
                "baseline": base, "checklist": checklist_summary(rows, base),
                "as_of": as_of, "universe": universe, "stored": True, "basis": _basis()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "rows": [], "stored": True}


def start(universe: str = "EGX100", period: str = "3y") -> dict:
    return job.start(compute, universe, period)


def status() -> dict:
    return job.status()
