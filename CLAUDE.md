# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-user, local-first decision-support web app for the Egyptian Exchange (EGX): FastAPI + SQLite + APScheduler backend, vanilla-JS dark-dashboard frontend, no auth, no order execution. Analytics come from `tradingview_mcp.core`, an **editable install of a separate repo at `D:\MyApps\tradingview-mcp`** (not in this tree; `/api/health` reports where it resolved from). The user is a trader, not a programmer — plain-language verdicts with visible reasons matter more than raw data.

`CONTRACT.md` is the original build spec (interfaces, DB schema, route table, design system) and is still the reference for payload shapes; `PANEL_REVIEW.md` / `REVIEW_UIUX.md` record the 2026-08-31 expert review and what was fixed; `TA_ROADMAP.md` is the 2026-09-06 technical-analyst review and its nine-task plan with per-task status — read it before proposing features. `USER_GUIDE.md` (and `_AR.md`) describe every UI element and are updated when features ship.

## Commands

All commands run from the project root on Windows PowerShell with the repo venv (Python 3.12).

```powershell
.venv\Scripts\python.exe run.py                        # start server (port from .env; this machine uses 8646 — see README port note)
.venv\Scripts\python.exe -m pytest tests -q            # full test suite
.venv\Scripts\python.exe -m pytest tests\test_guardian.py -q                  # one file
.venv\Scripts\python.exe -m pytest tests\test_compare.py::TestCompare::test_needs_two_symbols_and_caps_at_four -q
.venv\Scripts\python.exe -m py_compile app\services\foo.py                    # syntax check one file
```

No linter/formatter is configured; `pyrightconfig.json` points Pyright at `.venv`. There is no frontend build step — edit `web/*.html` and `web/assets/*` directly and hard-reload the browser.

Do not "fix" `PORT=8646` in `.env` back to 8642: 8642 sits in this machine's Windows reserved TCP range.

## Architecture

```
web/ (static, vanilla JS + Lightweight Charts v4)  →  fetch /api/*
app/main.py  FastAPI: lifespan (logging, DB init, scheduler), two middlewares, /api/health, /api/status, mounts web/ last
app/api/routes_*.py  thin async handlers: parse query/body → asyncio.to_thread(service.fn) → return dict
app/services/*.py    sync, pure-Python business logic; each returns a plain dict
app/db.py · app/config.py · app/calendar_egx.py · app/symbols.py   foundation
app/scheduler.py     APScheduler (Africa/Cairo) jobs calling services
```

**Two data sources, two symbol forms.** TradingView (via `tradingview_mcp` screeners) gives live-ish 15-min-delayed snapshots and uses `EGX:COMI` / `COMI`; Yahoo Finance v8 (via `app/services/history.py`, cached with TTL + negative cache + global 429 backoff) gives daily OHLCV history and uses `COMI.CA`. `app.symbols.tv_to_yahoo` must be applied on every Yahoo path (backtests, leaders, patterns, checklist, levels, guardian). Yahoo publishes the EGX daily bar about a session late, so `leaders.daily_candles` grafts the just-closed session's OHLC from the `snapshots` table onto the Yahoo series — most Yahoo-based cards go through that shared candle cache rather than calling `history` directly.

**Error contract.** Core-library functions and services never raise; they return `{"error": "..."}` and routes pass that through as HTTP 200. The frontend `API` helper (`web/assets/api.js`) throws on an `error` key so pages render inline error boxes. Keep this: a raised exception in a handler is a bug, and `{"ok": true}` must only be returned after checking the rowcount.

**Persistence.** `app/db.py` is stdlib sqlite3, one shared WAL connection behind a `threading.Lock`, no ORM. Schema is `CREATE TABLE IF NOT EXISTS` DDL plus additive `ALTER TABLE` migrations (duplicate-column errors swallowed) plus indexes — add new columns to `_MIGRATIONS`, never edit an existing `CREATE TABLE`. Use `db.executemany` for bulk writes (single transaction). `date` columns are Cairo local `YYYY-MM-DD` strings; `snapshots.date` is stamped with `calendar_egx.last_trading_day()`, not "today".

**Scheduler pipeline** (`app/scheduler.py`): `intraday` every 10 min in session → alerts + guardian; `post_close` 15:00 Sun–Thu → snapshot universe → EGX30 index → rule scanner → rvol stamp (`market.stamp_session_rvol`) → **regime** (needs the scanner's cached candles for breadth) → candidates → alerts → guardian → scorecard grading → leaders → patterns → setups (order matters: later stages read what earlier ones persisted); `morning_brief` 09:30 (needs `ANTHROPIC_API_KEY`); `weekly_maintenance` Sat (prune, weekly review Telegram digest, proven-edge recompute, VACUUM backup, symbol probe); hourly `catchup` re-runs post_close if a session's snapshot is missing. Every job is wrapped so it never raises, records a `job_runs` row (nested stage errors count as failure), and pings Telegram once on the transition into failure. Jobs gate on `calendar_egx.is_trading_day()` because cron only knows weekdays.

**Decision loop the services implement.** Scanners and rules journal hits into `scanner_hits` → `scorecard` grades each hit by 5/10/20/40/60-session excess return vs EGX30 and stamps the market `regime` at entry → per-scanner beat rates (regime-conditional when the sample allows) become weights in `screeners.candidates()` ranking → `replay` seeds this from years of history (`source='replay'` rows are track record only, never shown as today's candidates and never pruned) → `edge` summarises which rules/scanners/patterns actually work. `flows` (investor-type buy/sell by nationality and kind, pasted from EGX) is market context on the Dashboard, not yet a checklist input. `regime` (EGX30 vs its SMA50 + EGX100 breadth → bull/neutral/bear per session in `regime_daily`; `edge` splits every row by it and judges patterns at a per-category reference horizon: 10/20/40 sessions); `checklist` (buy, six pillars, downgraded SETUP→WATCH in a bear regime; pillars 4–5 ignore pattern types with a `negative` edge verdict) and `sell_checklist` (hold/sell, six pillars) reuse `levels`, `patterns`, `leaders`, `weekly`; `setups` runs the buy checklist across candidates + leaders + watchlist + holdings; `guardian` issues exit verdicts for open positions; `compare` ranks 2–4 symbols using all of the above; `review` (weekly) attributes closed trades to the live entry-rule hits on their fill session and compares realised R with the Proven-edge rule record, checks Guardian follow-through against fills/closes/stop raises, and stores one lesson per week (`review_notes`). Long computations (replay, edge) run through `bgjob` (one daemon-thread slot, UI polls status).

**Frontend.** Six pages (dashboard, stock, screener, backtest, portfolio, compare, plus review), each self-contained; shared `web/assets/{api.js, ui.js, charts.js, pg.js, app.css, pg.css}`. `charts.js` computes SMA/ATR/RVOL/chandelier client-side (`Charts.indicators`, node-tested via `node tests/js/chart_indicators.test.js`) — keep its ATR a simple mean of true ranges so the chandelier line matches `guardian._atr`. `ui.js` provides `el()` (no innerHTML path, on purpose — XSS), formatters, sidebar/topbar/footer, symbol autocomplete; `pg.js` is the table/panel framework used by screener/backtest/portfolio. Non-`/api` responses carry `Cache-Control: no-cache` so users see new frontends after an update. State-changing requests with a foreign `Origin` are rejected (CSRF guard for body-less cost-bearing POSTs).

## Trip hazards (verified in past sessions)

- `tradingview_mcp` batched screeners need the exchange key lowercase `"egx"`; uppercase silently falls back to the crypto screener. MTF/debate calls need the `EGX:`-prefixed form.
- APScheduler weekdays are mon=0..sun=6, so `day_of_week="sun-thu"` raises; spell days out (`"sun,mon,tue,wed,thu"`).
- Trade-plan payload nests levels under `trade_setup.{entry_points.{breakout_entry,pullback_entry}, stop_loss, targets.{target_1,target_2}, risk_reward.{...}}`; live score is `analysis.stock_score`, sub-scores at `trade_plan.score_breakdown`.
- `positions.stop` is the *current* protective stop (the guardian raises it); `positions.initial_stop` is the frozen risk anchor for R-multiples. Portfolio PnL is net of `FEE_PCT_PER_SIDE` on both legs.
- `portfolio.open_position` / `update_position` refuse targets that fail `plan_quality` (R:R to the nearest target < `MIN_RR_T1`, or inside `MIN_TARGET_ATR` × ATR14 of entry) with an error starting `BLOCKED:` and `requires_override: True`; the frontends treat any `BLOCKED` error as a confirm-then-`allow_override` flow. Tests that open positions with targets must either pass the gate (≥ 1.5R, ≥ 1 ATR) or monkeypatch `portfolio.atr14` and use `allow_override=True`.
- `app/services/briefs.py` uses the current Anthropic SDK pattern (`client.beta.messages.stream(model="claude-opus-5", thinking={"type":"adaptive"}, betas=[...], fallbacks="default")`) — do not "modernize" it backwards. Dependency versions in `requirements.txt` are pinned deliberately.
- `scorecard.FINAL_HORIZON` (60) is what marks an outcome row fully graded; adding a horizon means a migration, `_OUTCOME_COLS` picks it up, and the stored rows need `POST /api/edge/regrade` (background, ~25 min) before the edge table can use it. `edge.compute_baselines` stores one `random_entry_{h}d` row per horizon — a verdict must be judged against its own horizon's yardstick.
- Relative volume is `pattern_common.rvol` (volume / 20-day MEDIAN, None until 10 prior bars) — never a mean-based ratio, never 1.0 as a stand-in. Every journaled hit payload carries `rvol`; the Scorecard splits by `rvol_bucket` and `signal_weights(regime, bucket)` applies the measured multiplier. Old payloads without it are stamped by `scorecard.regrade`.
- Pattern rows carry `edge_verdict` from `edge.pattern_edges()` (stamped in `patterns.detect`/`latest`, never stored as truth — `latest` re-stamps at read time). UI defaults to `view=proven`; when the edge table is empty every row is `unmeasured` and the proven view is empty by design — say so, do not loosen the filter.
- `corporate_actions` rows come from two sources: Yahoo dividends/splits are booked by `leaders.daily_candles` on every fresh fetch (idempotent upsert), manual rows via the Portfolio panel. Pattern rows on an event day carry `suspect`; treat it like a `negative` edge verdict (non-evidence). The Guardian's `EX_DATE_SOON` is advice-level and must never outrank a stop breach.
- `investor_flows` rows come only from the user's paste of the EGX "Investor Type" page (`flows.record`). The EGX site answers scripted requests with an F5 "TSPD" JavaScript challenge, so do not add a scraper or a scheduler stage for it; the parser recomputes net as buy − sell and warns instead of failing on partial pastes. Dates are the session the page describes (default `calendar_egx.last_trading_day()`), and `(date, scope)` is the primary key, so re-pasting replaces.
- `rs_leaders` holds sector index rows under `SECTOR:<key>` symbols next to the stock rows; anything that reads the table by symbol must skip that prefix (`leaders.latest` does). `sector_context` is read-only from the stored ranking and is live-only in the checklist (a replayed window must not see today's sector rank).
- `regime.compute` reads the EGX30 series through `leaders.benchmark_series` and breadth through `leaders.daily_candles` for all of EGX100; run it after a universe sweep (post-close) or in a background job, never inline in a request. `checklist(..., regime_state=)` must receive the historical regime in replays — the live default reads today's row.
- Tests have no `conftest.py`: each test module sets `SCHEDULER_ENABLED=0` and a temp `DB_PATH` via `os.environ` *before* importing `app.*`, and stubs network collaborators with `monkeypatch` (e.g. `leaders.daily_candles`, `alerts._live_quote`). Follow the same pattern; tests must not hit TradingView or Yahoo. Because settings load once per process, `test_compare.py` (alphabetically first) pins `ACCOUNT_SIZE`/`RISK_PCT`/`FEE_PCT_PER_SIDE` for the whole session.

## Conventions

- Python 3.12, type hints, docstrings on public functions, no new third-party deps beyond `requirements.txt`. Services stay sync; only routes are async.
- Config is read once via `app.config.settings` from `.env` (see `.env.example` for every variable); never read `os.environ` elsewhere.
- Comments in this codebase explain *why* (the bug a guard prevents) — keep that style when adding guards.
- When a user-visible feature ships, update `USER_GUIDE.md`, `USER_GUIDE_AR.md` (and `CONTRACT.md` when an interface or table changes).

# Self-Maintenance Rule
After every major change (new model, new page, new controller, route changes, migration changes, new test files, architectural shifts), update this CLAUDE.md file to reflect the current state. Specifically:

Add new models/controllers/pages/routes to the relevant tables below
Update test count if new tests are added
Add any new gotchas or patterns to the "Gotchas & Pitfalls" section
Update the "Current State" section if the status changes
Keep this file as the single source of truth for AI sessions working on this project