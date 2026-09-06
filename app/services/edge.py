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
#: Reference grading horizon per kind of signal. Candlesticks and scanner thrusts
#: resolve inside two weeks; swing patterns (cups, triangles, wedges, channels,
#: reversals) take one to three months, and a 10-session verdict on them is a
#: horizon artefact in both directions. Price-action events sit in between.
REFERENCE_HORIZON: dict[str, int] = {
    "scanner": 10, "checklist": 10, "candlestick": 10, "price_action": 20,
    "reversal": 40, "triangle": 40, "continuation": 40, "wedge": 40, "channel": 40,
}
#: Regime states shown in the bull / bear split.
REGIMES = ("bull", "neutral", "bear")

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


def _baseline_stats(xs: list[float]) -> dict:
    xs = sorted(xs)
    n = len(xs)
    return {
        "sessions": n,
        "beat_rate": round(sum(1 for x in xs if x > 0) / n * 100.0, 1),
        "under_rate": round(sum(1 for x in xs if x < 0) / n * 100.0, 1),
        "avg_excess": round(sum(xs) / n, 2), "median_excess": round(xs[n // 2], 2),
    }


def compute_baselines(universe: str = "EGX100", period: str = "5y",
                      horizons: Optional[tuple[int, ...]] = None) -> dict[int, dict]:
    """What a RANDOM long entry did over each horizon on every stock and session of
    the universe, versus EGX30 — the yardstick every signal is measured against —
    split by the market regime on the entry date.

    On EGX single-stock returns are skewed (median session lags the index, a few fly),
    so the random beat rate sits well under 50%; judging signals against 50% would
    condemn everything. A bull tape lifts every stock, so a signal fired in one must
    beat the bull-tape random entry, not the all-weather one. Returns {horizon: stats}
    (each may be {"error": ...}); never raises.
    """
    from app.services import scorecard

    hs = tuple(horizons or scorecard.HORIZONS)
    try:
        from app.services import leaders, regime, rules_backtest as RB
        from app.symbols import universe as universe_symbols

        bench = leaders.benchmark_series(range_="5y")
        if not bench.get("dates"):
            bench = leaders.benchmark_series()
        regimes = regime.series()
        bars = RB.PERIOD_BARS.get(period, 1250)
        rng = "5y" if bars > 500 else ("2y" if bars > 250 else "1y")
        xs: dict[int, list[float]] = {h: [] for h in hs}
        by_reg: dict[int, dict[str, list[float]]] = {h: {} for h in hs}
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
            for i in range(150, len(c) - min(hs)):
                d0 = str(c[i]["time"])
                state = regimes.at(d0)
                try:
                    c0 = float(c[i]["close"])
                except (TypeError, ValueError):
                    continue
                if c0 <= 0:
                    continue
                for h in hs:
                    if i + h >= len(c):
                        continue
                    b = leaders.benchmark_return(bench, d0, str(c[i + h]["time"]))
                    if b is None:
                        continue
                    try:
                        x = (float(c[i + h]["close"]) / c0 - 1.0 - b) * 100.0
                    except (TypeError, ValueError):
                        continue
                    xs[h].append(x)
                    if state:
                        by_reg[h].setdefault(state, []).append(x)
        out: dict[int, dict] = {}
        for h in hs:
            if len(xs[h]) < 500:
                out[h] = {"error": f"baseline too thin ({len(xs[h])} sessions)", "sessions": len(xs[h]),
                          "horizon": h}
                continue
            out[h] = {
                "horizon": h, "universe": universe, "period": period, "symbols": symbols,
                **_baseline_stats(xs[h]),
                "by_regime": {st: _baseline_stats(v) for st, v in by_reg[h].items() if len(v) >= 200},
                "benchmark": bench.get("source"),
            }
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("compute_baselines failed")
        return {h: {"error": str(exc), "horizon": h} for h in hs}


def compute_baseline(universe: str = "EGX100", period: str = "5y", horizon: int = HORIZON) -> dict:
    """One-horizon convenience wrapper over ``compute_baselines``. Never raises."""
    return compute_baselines(universe, period, (horizon,)).get(horizon) or {"error": "baseline unavailable"}


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
        by_regime = {}
        for state, st in (pooled.get("by_regime") or {}).items():
            by_regime[state] = {"n": st.get("trades"), "hit_rate": st.get("win_rate"),
                                "edge_metric": st.get("avg_r"),
                                "verdict": rule_verdict(st.get("trades"), st.get("avg_r"))}
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
                "by_regime": by_regime,
            },
        })
    return rows


def reference_horizon(name: str) -> int:
    """Grading horizon a signal is judged at (see REFERENCE_HORIZON)."""
    n = str(name or "")
    if n.startswith("pattern_"):
        try:
            from app.services import pattern_catalog

            cat = str((pattern_catalog.info(n[len("pattern_"):]) or {}).get("category") or "")
            return REFERENCE_HORIZON.get(cat, HORIZON)
        except Exception:  # noqa: BLE001
            return HORIZON
    if n.startswith("checklist_"):
        return REFERENCE_HORIZON["checklist"]
    return REFERENCE_HORIZON["scanner"]


def _scorecard_rows() -> list[dict]:
    from app.services import scorecard

    card = scorecard.scorecard()
    rows: list[dict] = []
    if not isinstance(card, dict) or "error" in card:
        return rows
    for name, sc in (card.get("scanners") or {}).items():
        href = reference_horizon(name)
        hz = sc.get("horizons") or {}
        hr = hz.get(str(href)) or {}
        h10 = hz.get(str(HORIZON)) or {}
        n = int(hr.get("n") or 0)
        beat, excess = hr.get("beat_rate"), hr.get("avg_excess")
        kind = ("pattern" if str(name).startswith("pattern_") else
                "checklist" if str(name).startswith("checklist_") else "scanner")
        verdict = beat_verdict(n, hr.get("beat_vs_random_pp"), hr.get("excess_vs_random"), hr.get("se_excess"))
        label = (_pattern_label(str(name)[len("pattern_"):]) if kind == "pattern" else
                 "Checklist verdict: " + str(name)[len("checklist_"):].replace("_", " ").upper()
                 if kind == "checklist" else str(name).replace("_", " "))
        # Every horizon's headline numbers, so the UI can show 10 / 20 / 40 / 60 side by side.
        horizons = {h: {"n": v.get("n"), "beat_rate": v.get("beat_rate"), "avg_excess": v.get("avg_excess"),
                        "rate_vs_random_pp": v.get("beat_vs_random_pp"),
                        "excess_vs_random": v.get("excess_vs_random"),
                        "verdict": beat_verdict(int(v.get("n") or 0), v.get("beat_vs_random_pp"),
                                                v.get("excess_vs_random"), v.get("se_excess"))}
                    for h, v in hz.items()}
        # The same signal split by the regime it fired in, at the reference horizon.
        by_regime = {}
        for state, hs in (sc.get("by_regime") or {}).items():
            v = hs.get(str(href)) or {}
            by_regime[state] = {"n": v.get("n"), "hit_rate": v.get("beat_rate"), "edge_metric": v.get("avg_excess"),
                                "rate_vs_random_pp": v.get("beat_vs_random_pp"),
                                "excess_vs_random": v.get("excess_vs_random"),
                                "verdict": beat_verdict(int(v.get("n") or 0), v.get("beat_vs_random_pp"),
                                                        v.get("excess_vs_random"), v.get("se_excess"))}
        # ...and by the relative volume of the signal day (Task 4).
        by_rvol = {}
        for bucket, hs in (sc.get("by_rvol") or {}).items():
            v = hs.get(str(href)) or {}
            by_rvol[bucket] = {"n": v.get("n"), "hit_rate": v.get("beat_rate"), "edge_metric": v.get("avg_excess"),
                               "rate_vs_random_pp": v.get("beat_vs_random_pp"),
                               "excess_vs_random": v.get("excess_vs_random"),
                               "verdict": beat_verdict(int(v.get("n") or 0), v.get("beat_vs_random_pp"),
                                                       v.get("excess_vs_random"), v.get("se_excess"))}
        rows.append({
            "kind": kind, "name": name, "label": label, "period": "graded history",
            "n": n, "hit_rate": beat, "edge_metric": excess,
            "metric_label": (f"avg excess vs EGX30 over {href} sessions, % (signed: + = the stock moved the "
                             "signal's way)"),
            "verdict": verdict, "verdict_text": VERDICT_TEXT[verdict],
            "extra": {
                "direction": sc.get("direction"), "horizon": href,
                "rate_vs_random_pp": hr.get("beat_vs_random_pp"),
                "excess_vs_random": hr.get("excess_vs_random"), "se_excess": hr.get("se_excess"),
                "win_rate": hr.get("win_rate"),
                "win_rate_10": h10.get("win_rate"), "n_10": h10.get("n"), "beat_10": h10.get("beat_rate"),
                "excess_10": h10.get("avg_excess"),
                "horizons": horizons, "by_regime": by_regime, "by_rvol": by_rvol,
                "weight": sc.get("weight"),
                "weight_basis": sc.get("weight_basis"), "proxy": sc.get("proxy"),
                "sources": sc.get("sources"),
            },
        })
    return rows


def _baseline_row(b: dict, universe: str) -> dict:
    h = b.get("horizon", HORIZON)
    return {
        "kind": "baseline", "name": f"random_entry_{h}d",
        "label": "Random entry (any stock, any session)", "period": str(b.get("period")),
        "n": b.get("sessions"), "hit_rate": b.get("beat_rate"), "edge_metric": b.get("avg_excess"),
        "metric_label": f"avg excess vs EGX30 over {h} sessions, %", "verdict": "baseline",
        "verdict_text": "The yardstick: what buying at random did", "extra": {**b, "universe": universe},
    }


_pattern_edges_cache: tuple[float, dict[str, dict]] | None = None
_PATTERN_EDGES_TTL = 600.0


def invalidate_pattern_edges() -> None:
    global _pattern_edges_cache
    _pattern_edges_cache = None


def pattern_edges(force: bool = False) -> dict[str, dict]:
    """Stored verdict per pattern key (``double_bottom`` -> {...}) from the Proven-edge
    table — the arbiter that decides which patterns the UI shows by default.

    Each value: {verdict, horizon, n, hit_rate, edge_metric, rate_vs_random_pp,
    excess_vs_random, horizons{h: {...verdict}}, by_regime{state: {...}}}. Empty
    when the table has never been computed. Cached 10 minutes; never raises.
    """
    global _pattern_edges_cache
    now = time.monotonic()
    if not force and _pattern_edges_cache and now - _pattern_edges_cache[0] < _PATTERN_EDGES_TTL:
        return _pattern_edges_cache[1]
    out: dict[str, dict] = {}
    try:
        for r in db.query("SELECT name, verdict, n, hit_rate, edge_metric, extra_json FROM proven_edge "
                          "WHERE kind = 'pattern'"):
            key = str(r["name"])[len("pattern_"):]
            try:
                extra = json.loads(r.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            out[key] = {
                "verdict": r.get("verdict") or "too_few", "horizon": extra.get("horizon", HORIZON),
                "n": r.get("n"), "hit_rate": r.get("hit_rate"), "edge_metric": r.get("edge_metric"),
                "rate_vs_random_pp": extra.get("rate_vs_random_pp"), "excess_vs_random": extra.get("excess_vs_random"),
                "horizons": extra.get("horizons") or {}, "by_regime": extra.get("by_regime") or {},
            }
    except Exception as exc:  # noqa: BLE001 — table may not exist yet
        logger.warning("pattern_edges failed: %s", exc)
    _pattern_edges_cache = (now, out)
    return out


def _persist(rows: list[dict], universe: str, wipe: bool = True) -> None:
    now = _now_iso()
    invalidate_pattern_edges()
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
    # The checklist is a swing tool: a 10-session verdict undersells it, so the
    # 20- and 40-session spreads are reported next to it (from extra.horizons).
    def _h(v: str, h: str) -> Optional[float]:
        r = by.get(f"checklist_{v}") or {}
        return ((r.get("extra") or {}).get("horizons") or {}).get(h, {}).get("avg_excess")
    spreads = {}
    for h in ("20", "40"):
        a, b = _h("setup", h), _h("no_setup", h)
        spreads[h] = round(a - b, 2) if (a is not None and b is not None) else None
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
    longer = [f"{spreads[h]:+.2f} at {h}" for h in ("20", "40") if spreads.get(h) is not None]
    if longer:
        text += f" Over longer holds the gap is {' and '.join(longer)} sessions."
    return {"setup": setup, "watch": watch, "no_setup": no, "spread_10d": spread,
            "spread_20d": spreads.get("20"), "spread_40d": spreads.get("40"), "verdict": verdict,
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
        # 1. The yardsticks first (one per horizon, each split by regime): they must
        #    be stored before the Scorecard reads them.
        bases = compute_baselines(universe, "5y")
        good = [b for b in bases.values() if "error" not in b]
        base = bases.get(HORIZON) or {"error": "no 10-session baseline"}
        if good:
            if persist:
                db.execute("DELETE FROM proven_edge WHERE kind = 'baseline'")
                _persist([_baseline_row(b, universe) for b in good], universe, wipe=False)
            from app.services import scorecard
            scorecard.invalidate_weights()
        if include_rules:
            rows.extend(_rule_rows(universe, period, exit_rule))
        job.progress(phase="scorecard", detail=None)
        rows.extend(_scorecard_rows())
        rows.extend(_baseline_row(b, universe) for b in good)
        if persist:
            _persist(rows, universe)
        out = {
            "rows": rows, "summary": _summary(rows), "headline": _headline(rows, base),
            "baseline": base if "error" not in base else None,
            "baselines": {str(h): b for h, b in bases.items()},
            "checklist": checklist_summary(rows, base if "error" not in base else None),
            "regime": _regime_block(rows), "volume": _volume_block(rows),
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
        f"'negative' = average R at or below zero. Scanners and patterns: close-to-close return after the "
        "signal versus EGX30 at the signal's reference horizon — 10 sessions for scanners, candlesticks and "
        "checklist verdicts, 20 for price-action events, 40 for chart patterns (reversals, triangles, "
        "continuations, wedges, channels) — signed so a bearish signal is right when the stock falls, and "
        "compared with a RANDOM entry over the same stocks, years and horizon; 'edge' = average "
        f"excess at least {EXCESS_EDGE_PP:.1f} points above random and beyond two standard errors, "
        "with a right-way rate not below random; 'negative' = the mirror image. Every row is also split "
        "by the market regime (bull / neutral / bear, from EGX30 versus its 50-day average and breadth) the "
        "signal fired in, each judged against the random entry in that same regime. Rows marked replay come "
        "from the historical replay; live rows accumulate as the scanners run. Past edge is a "
        "reason to keep a rule, not a promise about the next trade."
    )


def _volume_block(rows: list[dict]) -> dict:
    """Does the signal day's volume change the outcome? Per row: heavy (≥1.5×) vs
    quiet (<1×) excess at the reference horizon; lists the signals where heavy
    volume is an edge and quiet volume is not — the ones worth waiting for volume on."""
    matters: list[dict] = []
    indifferent: list[dict] = []
    measured = False
    for r in rows:
        if r.get("kind") == "baseline":
            continue
        br = (r.get("extra") or {}).get("by_rvol") or {}
        heavy, quiet = br.get("ge1.5") or {}, br.get("lt1") or {}
        if int(heavy.get("n") or 0) >= MIN_SAMPLE and int(quiet.get("n") or 0) >= MIN_SAMPLE:
            measured = True
            item = {"name": r["name"], "label": r["label"], "kind": r["kind"],
                    "heavy": heavy.get("edge_metric"), "quiet": quiet.get("edge_metric"),
                    "heavy_n": heavy.get("n"), "quiet_n": quiet.get("n"),
                    "heavy_verdict": heavy.get("verdict"), "quiet_verdict": quiet.get("verdict")}
            if heavy.get("verdict") == "edge" and quiet.get("verdict") != "edge":
                matters.append(item)
            elif heavy.get("edge_metric") is not None and quiet.get("edge_metric") is not None \
                    and abs(heavy["edge_metric"] - quiet["edge_metric"]) < 0.3:
                indifferent.append(item)
    matters.sort(key=lambda x: (x["heavy"] or 0) - (x["quiet"] or 0), reverse=True)
    return {"measured": measured, "volume_matters": matters[:12], "volume_indifferent": indifferent[:12]}


def _regime_block(rows: list[dict]) -> dict:
    """Bull-vs-bear summary across rows: how many signals keep their edge in each tape,
    plus today's regime so the reader knows which column applies."""
    try:
        from app.services import regime

        now = regime.current()
    except Exception:  # noqa: BLE001
        now = {"state": None, "text": "", "measured": False}
    counts = {s: {"edge": 0, "marginal": 0, "negative": 0, "too_few": 0} for s in REGIMES}
    flips: list[dict] = []
    for r in rows:
        if r.get("kind") == "baseline":
            continue
        br = (r.get("extra") or {}).get("by_regime") or {}
        for s in REGIMES:
            v = (br.get(s) or {}).get("verdict")
            if v in counts[s]:
                counts[s][v] += 1
        bull, bear = (br.get("bull") or {}).get("verdict"), (br.get("bear") or {}).get("verdict")
        if bull == "edge" and bear in ("negative", "marginal"):
            flips.append({"name": r["name"], "label": r["label"], "kind": r["kind"], "bull": bull, "bear": bear,
                          "bull_metric": (br.get("bull") or {}).get("edge_metric"),
                          "bear_metric": (br.get("bear") or {}).get("edge_metric")})
    measured = any(any(c.values()) for c in counts.values())
    return {"current": {"state": now.get("state"), "date": now.get("date"), "text": now.get("text"),
                        "stale": now.get("stale"), "measured": now.get("measured")},
            "counts": counts, "bull_only": flips[:12], "measured": measured}


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
        base = next((r["extra"] for r in base_rows if r["name"] == f"random_entry_{HORIZON}d"),
                    base_rows[0]["extra"] if base_rows else None)
        order = {"edge": 0, "marginal": 1, "negative": 2, "too_few": 3}
        rows.sort(key=lambda x: ({"rule": 0, "checklist": 1, "scanner": 2, "pattern": 3}.get(x["kind"], 9),
                                 order.get(x["verdict"], 9),
                                 -((x.get("extra") or {}).get("excess_vs_random") or x.get("edge_metric") or 0)))
        return {"rows": rows, "summary": _summary(rows), "headline": _headline(rows, base),
                "baseline": base, "baselines": {r["name"].split("_")[-1].rstrip("d"): r["extra"] for r in base_rows},
                "checklist": checklist_summary(rows, base), "regime": _regime_block(rows),
                "volume": _volume_block(rows),
                "as_of": as_of, "universe": universe, "stored": True, "basis": _basis()}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "rows": [], "stored": True}


def start(universe: str = "EGX100", period: str = "3y") -> dict:
    return job.start(compute, universe, period)


def status() -> dict:
    return job.status()
