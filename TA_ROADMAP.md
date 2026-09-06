# Technical-Analyst Review Roadmap — 2026-09-06

Source: senior technical-analyst review of the app on 2026-09-06 (rating 7.5/10).
Nine gaps ranked by expected P&L impact. This file is the working plan: one task
at a time, each shipped with tests, docs (USER_GUIDE EN/AR, CONTRACT) and a
status line here. Item 10 of the review (Arabic UI) is deliberately out of scope.

Ground rules for every task
- Services stay sync and never raise; routes stay thin; no new dependencies.
- Additive `ALTER TABLE` migrations only (`db._MIGRATIONS`).
- Anything that claims an edge must be *measured* on the replay data before the UI
  shows it as a rule. The Proven-edge table is the arbiter.
- Tests offline (monkeypatch `leaders.daily_candles`, `leaders.benchmark_series`).

Legend: ☐ not started · ◐ in progress · ☑ shipped

---

## Task 1 ☑ — Market regime + grading foundation (review items 1 and 2, part 1)

**Problem.** No decision consumes the state of the index or breadth. Random entries
beat EGX30 only 43.9% of the time with a positive mean and negative median, the
signature of a market where the index regime drives single-stock outcomes. Every
signal is graded at 5/10/20 sessions only, too short for swing patterns.

**Build.**
1. `app/services/regime.py` — `series(range_="5y")` builds a daily regime table from
   the EGX30 benchmark (`leaders.benchmark_series`) plus breadth (% of EGX100
   above their SMA50, from the cached daily candles):
   - `bull`: close > SMA50 and SMA50 rising over 10 sessions and breadth ≥ 50%
   - `bear`: close < SMA50 and SMA50 falling, or breadth < 35%
   - `neutral`: otherwise
   Persist to `regime_daily(date PK, state, index_close, sma50, sma200, breadth_pct,
   source)`; `current()` returns today's row with one plain-language sentence.
2. `signal_outcomes` gains `regime TEXT` plus `ret_40/bench_40/excess_40` and
   `ret_60/bench_60/excess_60`; `scorecard.HORIZONS = (5,10,20,40,60)`;
   `grade_hit` stamps the regime at entry.
3. `scorecard.regrade(source="replay")` — background job (via `bgjob`) that re-grades
   every existing outcome from cached 5y candles so the 97k replay rows get the new
   columns without re-running detection. Route `POST /api/edge/regrade` + status.
4. `edge.compute` adds per-regime rows (`kind` = `rule_regime` / `pattern_regime`,
   `label` = "range_breakout · bull") and picks the *reference horizon* per kind
   (rules: Guardian exits as today; candlestick 10; reversal/continuation/triangle/
   wedge/channel 40; price_action 20). `latest()` exposes `regime_split`.
5. Consumers: `checklist` downgrades SETUP→WATCH in a bear regime with the reason
   as an extra `market` line (pillar count stays 6 so the UI does not change shape);
   `screeners.candidates` multiplies evidence by the regime-conditional beat rate
   when it is measured; `setups`, `compare` carry `regime`.
6. UI: regime chip beside the session pill on every page (`ui.js`); dashboard
   Proven-edge card shows the bull/bear split; Screener Scorecard gains horizon
   selector 10/20/40/60.
7. Scheduler: `post_close` computes today's regime row before the rule scanner.

**Accept.** Edge table shows every rule/pattern with bull vs bear n and excess;
checklist on a bear day says why it holds back; 40/60-session columns populated
for ≥ 90% of replay rows; tests for regime states, regrade, checklist downgrade.

**Status 2026-09-06 — SHIPPED; live re-grade + edge refresh done the same evening** (117,194 outcomes re-graded, 110,165 with a 60-session result, all stamped with a regime; regime_daily 2021-11 → 2026-09-06: 696 bull / 261 neutral / 209 bear sessions; today = bull, 84% breadth; browser-verified chip, checklist line, Proven-edge columns, Scorecard columns). `app/services/regime.py`
(classify / compute / update_today / backfill / current / RegimeSeries.at), table
`regime_daily`, `signal_outcomes` + ret/bench/excess_40/60 + regime; `scorecard`
HORIZONS (5,10,20,40,60), FINAL_HORIZON 60, `grade_hit(..., regimes)`, `regrade`
background job, per-regime stats + `regime_weights`, `signal_weights(regime)`,
per-horizon baselines; `edge` REFERENCE_HORIZON per pattern category, `compute_baselines`
(per horizon × regime), `extra.horizons` / `extra.by_regime`, `regime` block with
`bull_only`; `rules_backtest.universe_run` pooled `by_regime`; `checklist(...,
regime_state)` + `market{state,text,raw_verdict,applied}` (bear → SETUP becomes WATCH);
`screeners` pass today's regime to the weights; replay checklist uses the historical
regime; post_close `regime` stage; routes `GET /api/market/regime`, `POST
/api/market/regime/refresh`, `POST /api/edge/regrade`, regrade in `/api/edge/status`.
UI: regime chip in the topbar (ui.js), checklist market line (stock.html), Proven-edge
card horizon chips + Bull/Bear columns + bull-only line + `Re-grade` button
(index.html), Scorecard 40/60 columns + bull/bear vs random + regime line
(screener.html). Tests: `tests/test_regime.py` (13) — suite 292. Docs: USER_GUIDE 2.4a /
3.6.1 / 4.9 / 5.9, USER_GUIDE_AR, CONTRACT, CLAUDE.md. Design change vs the plan: the
regime split lives in each row's `extra.by_regime` rather than separate `*_regime` kinds
(same information, no table bloat).

## Task 2 ☑ — Prune the pattern catalog to survivors (review item 2, part 2)

**Problem.** ~70 patterns, 6 with edge, 15 negative, the rest marginal. Noise.

**Build.** `pattern_catalog` rows carry `edge_verdict` + `edge_horizon` from the
Proven-edge table; Patterns tab and stock-page Chart-patterns card default to
"proven only" (edge at the reference horizon, or bearish patterns with right-way
rate ≥ 55%) with a "show all" toggle remembered in `localStorage`; negative
patterns are hidden from the checklist's Patterns pillar and from candidates
evidence; catalog view shows per-horizon verdicts. Docs list the survivors.

**Accept.** Default stock page shows only surviving patterns; checklist Patterns
pillar ignores negative-verdict rows; a test pins the filter.

**Status 2026-09-06 — SHIPPED.** `edge.pattern_edges()` (cached verdict per pattern key, invalidated on
`_persist`); `pattern_catalog.attach_edge / passes_view / enrich(row, edges)` with views `proven` (default) ·
`not_negative` · `all`; `patterns.detect(..., view)` filters BEFORE event clustering and the decisive level so
counts match what is shown, returns `hidden_by_verdict`; `patterns.latest(..., view)` re-stamps stored rows at
read time; `patterns.catalog()` adds verdict, reference horizon, verdict-by-horizon and regime split per pattern
plus `proven[]` / `negative[]`; checklist pillars 4–5 ignore negative-record types and say so. Routes gain
`?view=`. UI: `Record` selector + chips on the stock card (empty state names what was hidden, `Show all`
button), Screener Patterns tab (`Record` select, `Record` column, hidden counts) and Catalog (`Record`,
`By horizon` columns, sorted by verdict); dashboard column requests `not_negative`. Tests:
`tests/test_pattern_pruning.py` (6) — suite 298. Docs EN/AR 3.2.3, 4.9, 4.14, 5.7, 5.8; CONTRACT; CLAUDE.md.
Design change vs the plan: the "bearish patterns with right-way rate ≥ 55%" survivor rule was dropped — the
random-entry under-rate on EGX is already 56%, so 55% right-way is not evidence; the verdict alone decides.
Candidates never merged pattern hits, so no change there. Today's survivors at their reference horizons:
three white soldiers, marubozu (10d); bull trap, upthrust (20d); bull pennant, triple top (40d).

## Task 3 ☑ — Minimum reward-to-risk gate at open (review item 3)

**Problem.** CLHO opened 2026-09-06 with entry 17.47, stop 16.70, T1 17.53 — T1 is
0.3% away against a 4.4% stop. The plan card warned; the ledger accepted it and
the Guardian immediately said TARGET1_HIT.

**Build.** `portfolio.open_position` / `update_position` compute R:R to T1 and T2
from the frozen risk; reject when `T1 < entry + MIN_TARGET_ATR × ATR14` (default
1.0) or `RR(T1) < MIN_RR_T1` (default 1.5) unless `allow_override` (recorded as a
warning, as the heat cap does). `.env` gains `MIN_RR_T1`, `MIN_TARGET_ATR`.
Guardian: a target inside 1 ATR of entry is treated like PLAN_INVALID (flag, never
"hit"). Portfolio New-position form shows the block + override tick; stock-page
sizer shows RR to T1 in red below 1.5. Repair the CLHO record with the user.

**Accept.** Tests for the gate, override, guardian flag; CLHO shows a real plan.

**Status 2026-09-06 — SHIPPED, CLHO repaired.** User chose T1 18.07 (just under the 18.21 wall, 0.78R) / T2 19.01 (2R) with the override recorded on the position; the Guardian now reads CHECKLIST_EXIT for CLHO (a real sell-checklist verdict) instead of TARGET1_HIT. `settings.min_rr_t1`
(MIN_RR_T1 1.5) / `settings.min_target_atr` (MIN_TARGET_ATR 1.0); `portfolio.atr14`, `portfolio.plan_quality`
(pure), `_blocked_plan`; gate in `open_position` (after target/note validation, before heat) and in
`update_position` (new `allow_override` param; risk anchor = initial stop); `size_position(target1, target2)`
returns `plan_quality`; Guardian flags a target inside MIN_TARGET_ATR × ATR14 as PLAN_INVALID and never
"hits" it. Routes: `GET /api/portfolio/plan-quality`, config exposes the thresholds, update body gains
`allow_override`, size body gains targets. UI: New-position form previews the gate while typing and offers the
override on BLOCKED; `Targets` row button does the same; stock-page sizer gains a Target 1 box and an
`R:R to target 1` line (red when it would be blocked). Tests: `tests/test_rr_gate.py` (7); three older
Guardian tests had synthetic targets that the gate now refuses and were given real ones — suite 305. Docs
EN/AR 1.4, 4.15, 7.2, 7.3, 7.4; CONTRACT; CLAUDE.md. Finding while repairing CLHO: the stock's OWN trade plan
proposes T1 17.52 (0.1 ATR above entry) — the bad target came from the plan; the nearest tested resistance
18.21 (4 touches) pays only 0.96R against the 16.70 stop, so no target under the wall passes 1.5R.

## Task 4 ☑ — Relative volume as a first-class number (review item 4)

**Problem.** Volume analysis is a weekly average ratio in the buy checklist and a
down-day share in the sell checklist. Breakout quality on EGX is decided by the
volume of the trigger day versus normal.

**Build.** `rvol = volume / median(volume, 20)` computed in `rules_backtest.Ind`
and stamped in `snapshots` (`rvol` column, from the TV batch volume). Carried on:
`scanner_hits.payload_json`, rule-scanner rows, candidates, setups rows, checklist
Volume pillar (trigger-day RVOL first, weekly ratio second), stock header chip,
screener columns, Compare. Edge: `edge.compute` buckets rule/scanner hits by RVOL
(< 1 · 1–1.5 · ≥ 1.5) so the volume weighting is measured, not assumed; candidates
evidence uses the measured bucket multiplier.

**Accept.** RVOL visible everywhere a hit is shown; edge table has RVOL buckets;
tests for the computation and the pillar wording.

**Status 2026-09-06 — SHIPPED.** `pattern_common.rvol` (median-based) + `rvol_bucket`; `Ind.rvol`; rvol stamped
on rule-scanner rows/payloads, replay rule + pattern + checklist payloads, pattern rows (break day) + pattern_hits
payloads, checklist volume pillar (today's RVOL leads: pass ≥1.5× up day, fail ≥1.5× down day, quiet <0.7×),
setups, compare, candidates (payload else cached candles), `snapshots.rvol` via a post-close `stamp_session_rvol`
stage, stock detail `volume` block. Scorecard `by_rvol` + `rvol_multipliers` (bucket beat / overall, [0.7, 1.3],
proxies inherit); `signal_weights(regime, bucket)`; Candidates rank with per-symbol bucket weights. Edge rows
`extra.by_rvol`, `edge.latest()["volume"]` (volume_matters list). `regrade` backfills payload rvol. UI: header
RVOL chip (stock), RVOL column + chip (Screener candidates, dashboard candidates), Patterns RVOL column,
Scorecard heavy/quiet columns + regime line, Proven-edge "Volume matters for" line, Compare row. Tests:
`tests/test_rvol.py` (9) — suite 314. Docs EN/AR 3.6.1, 4.1, 4.9, 5.4, 5.7, 5.9, 5.10; CONTRACT; CLAUDE.md.
Design note: the multiplier is bucket-beat / overall-beat, applied only with 20+ hits in the bucket — a rule
whose heavy-volume hits do no better keeps 1.0, so the volume premium is measured, never assumed.

## Task 5 ☑ — Chart overlays a technical analyst can verify (review item 6)

**Build.** `charts.js renderCandles` gains optional `indicators`: SMA 20/50/200
lines computed client-side from the candles, a chandelier trail line for held
stocks (from Guardian `suggested_stop` history or recomputed client-side as
highest close − 2.5 × ATR14), volume bars coloured by RVOL (≥ 1.5 bright, < 0.7
dim). Legend with toggles remembered in `localStorage`; works on the 1D|1W switch.

**Accept.** Stock page shows the averages the Trend pillar cites; no layout shift.

**Status 2026-09-06 — SHIPPED.** `charts.js`: pure `smaSeries` / `atrSeries` (simple mean of true ranges,
matching `guardian._atr`) / `rvolSeries` (median-based, matching `pattern_common.rvol`) / `chandelierSeries`
(never lowered); `renderCandles(..., opts)` draws SMA 20/50/200, RVOL-intensity volume bars and the chandelier
from the held position's `opened_at`; legend chips toggle layers with prefs in localStorage; the chart re-renders
in place. stock.html hosts the legend in the chart card title and passes `guardian_atr_mult` from
`/api/portfolio/config`. `tests/js/chart_indicators.test.js` (node, 12 assertions). Docs EN/AR 4.2, CONTRACT,
CLAUDE.md. Design note: the 1D|1W toggle switches Score and Trade plan only (chart stays daily, as before), so
"works on the 1D|1W switch" is satisfied by re-rendering with the same daily candles.

## Task 6 ☑ — Weekly review page (review item 7, the skipped Phase 2)

**Build.** `app/services/review.py` + `web/review.html` + `routes_review.py`:
- closed trades grouped by entry rule/setup type: live avg R, hit rate, n versus
  the replay expectation for the same rule (from Proven edge) — "you vs system";
- `plan_followed` split (followed vs deviated avg R), stop-moved-early count;
- this week's Guardian verdicts and whether the ledger shows an action after them;
- open heat over time, equity vs EGX30 since first trade;
- free-text "lessons" saved per week (`review_notes` table).
Saturday `weekly_maintenance` sends one Telegram digest with the headline numbers.

**Accept.** Page renders with zero closed trades (empty states), with the current
book, and the digest is one message.

**Status 2026-09-06 — SHIPPED.** `app/services/review.py` (week_bounds Sun–Thu with Fri/Sat → week just
ended; attribution from live entry-rule hits on the fill session ±4 days; you-vs-system per rule against
`proven_edge` kind=rule; discipline: plan_followed split, stops lowered, discretionary exits, exits-by-how;
guardian_week with acted-detection via close / sell fill / stop ≥ suggested; heat per session from the
positions open that day; notes table `review_notes`; digest_text + digest), `routes_review.py`,
`web/review.html` (week nav, six panels, lesson box, Send digest), sidebar/mobile/fallback nav entries,
`weekly_maintenance` stage `review_digest`. Tests: `tests/test_review.py` (7) — suite 321. Docs EN/AR 7.8–7.9,
CONTRACT, CLAUDE.md. Design note: heat history is reconstructed from current stops because stop changes are not
journaled — the page says so; journaling stop changes is a follow-up if the approximation misleads.

## Task 7 ☑ — Sector relative strength feeding decisions (review item 9)

**Build.** `leaders.compute` also builds equal-weight sector series from
`egx_sectors` groups over the cached candles; each row gains `sector`, `sector_rs_rank`
and `rs_vs_sector_1m/3m`. Checklist Trend pillar appends "sector ranks N of M";
Compare shows sector rank; Screener Leaders tab gets a sector filter and a small
sector RS table; dashboard heatmap card links to it.

**Accept.** Sector table matches hand-computed returns on a fixture; UI shows rank.

**Status 2026-09-06 — SHIPPED.** `leaders.sector_of/sector_label/sector_strength/attach_sectors/sector_context/
sector_sentence`; `compute()` builds equal-weight sector indices from the ranked members' cached candles, ranks
them with the stocks' 30/40/30 weighting, stamps every stock with sector rank, rank-in-sector and 1m/3m return vs
sector, and persists sector rows in `rs_leaders` under `SECTOR:<key>`; `latest(sector=)` filters. Checklist Trend
pillar appends the sector sentence (live only); Compare gains a Sector strength row; Screener Leaders tab gains a
Sector select, a collapsible sector table (click to filter) and three columns; dashboard heatmap links to it.
Tests: `tests/test_sector_rs.py` (3) — suite 324. Docs EN/AR 3.5, 4.9, 5.6, 5.10; CONTRACT; CLAUDE.md.

## Task 8 ☑ — Corporate-actions awareness (review item 8)

**Build.** `history.py` keeps the Yahoo `events` block (dividends, splits) that it
currently discards; `corporate_actions` table (symbol, type, ex_date, amount,
source) filled from Yahoo history plus a manual entry form for upcoming ex-dates,
rights and capital increases; chart markers on ex-dates; `patterns.detect` tags
events whose trigger bar is an ex-date gap as `suspect`; Guardian/checklist warn
when a known ex-date is within 5 sessions. An automatic upcoming-events source is
an open question (see below).

**Accept.** Historical ex-div gaps stop producing bear traps in a fixture; manual
entry round-trips; warnings render.

**Status 2026-09-06 — SHIPPED.** `app/services/corporate_actions.py` + table; `history` requests and parses
`events=div,splits`; `leaders.daily_candles` books Yahoo events on fresh fetches; `patterns.detect` tags
`suspect` rows (trigger bar within a day of an event) and the checklist ignores them; checklist Risk pillar and
Guardian (`EX_DATE_SOON`, advice) warn inside 5 days; routes + `routes_actions.py`; chart markers via
`opts.markers`; stock next-event chip and "event gap" chips; Portfolio "Corporate actions" panel (manual form +
upcoming for held/watchlist). Tests: `tests/test_corporate_actions.py` (6) — suite 330. Docs EN/AR 3.6.1, 4.2,
7.2, 7.10; CONTRACT; CLAUDE.md. Open question (user): an automatic source for UPCOMING ex-dates — manual entry for now.

**Checklist re-replay (2026-09-06, after Tasks 1–4).** Old replayed checklist rows (19,427) cleared and the
six-pillar checklist re-run over 5y with the regime gate, RVOL pillar and negative-pattern filter: SETUP n=232
(0 in bear regimes — the gate works), 10-session excess +1.09% vs NO SETUP +0.40% (spread +0.69 pp, was +0.06),
+0.71 above a random entry; at 20 sessions SETUP +2.78% vs +0.86% (spread +1.9 pp), at 40 sessions +3.78% vs
+1.56% (spread +2.2 pp). Verdict at 10d still "marginal" by the ≥1 pp rule; `edge.checklist_summary` now reports
the 20/40-session spreads (`spread_20d`, `spread_40d`) in its text.

## Task 9 ☑ — Investor-type flows (review item 5)

**Build (depends on data source, see open questions).** `investor_flows` table
(date, egyptian/arab/foreign × buy/sell × retail/institutional, source); ingestion
(paste form or scraper); dashboard row "Who bought today" with 5- and 20-session
net foreign/institutional flow; edge check: regime rows conditioned on 5-session
net foreign flow sign.

**Status 2026-09-06 — SHIPPED (manual-paste route).** The EGX website route FELL THROUGH: www.egx.com.eg answers
every scripted request (curl, server-side fetch) with an F5 "TSPD" JavaScript bot challenge, and the Investor Type page
carries no date and no download. Circumventing the challenge is not appropriate, so per the user's answer ("if not easy,
another option") the app takes a paste: `app/services/flows.py` (`parse_egx_text`, `record`, `summary`, `reading`) +
`investor_flows` table (PK date, scope); routes `routes_flows.py` (GET /api/flows, /history, POST /parse, /paste,
DELETE /{date}); Dashboard card "Investor flows — who bought, who sold" with five tiles, 5/20-session sums and
seller-session counts, a foreign-net bar strip, a plain-language reading (actor line, institutions-vs-individuals
accumulation/distribution, 5-session foreign streak) and the paste panel (date default = last trading day, EGX radio
scope). Parser verified on the real page of 2026-09-06: foreigners −255m, Arabs −38m, Egyptians +293m; institutions
−598m vs individuals +598m (distribution). Tests: `tests/test_flows.py` (7) — suite 337. Docs EN/AR 3.3a, CONTRACT,
CLAUDE.md. NOT built (needs ≥20 stored sessions first): the edge check conditioning regime rows on the 5-session foreign
flow sign — revisit once a month of pastes exists.

---

## Open questions for the user

1. **Investor flows (Task 9):** ANSWERED 2026-09-06 — try the EGX website daily
   report first; fall back to another option (manual paste) if it is not easy.
   RESOLVED: website blocked by a bot challenge → manual paste shipped.
2. **Corporate actions (Task 8):** still open — preferred source for *upcoming*
   ex-dividend dates and capital increases, or manual entry for now?
3. **CLHO record (Task 3):** ANSWERED 2026-09-06 — the app proposes targets from
   the trade-plan defaults and shows them before saving; entry 17.47 is correct.
