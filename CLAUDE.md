# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-user, local-first decision-support web app for the Egyptian Exchange (EGX): FastAPI + SQLite + APScheduler backend, vanilla-JS dark-dashboard frontend, no auth, no order execution. Analytics come from `tradingview_mcp.core`, an **editable install of a separate repo at `D:\MyApps\tradingview-mcp`** (not in this tree; `/api/health` reports where it resolved from). The user is a trader, not a programmer — plain-language verdicts with visible reasons matter more than raw data.

`CONTRACT.md` is the original build spec (interfaces, DB schema, route table, design system) and is still the reference for payload shapes; `PANEL_REVIEW.md` / `REVIEW_UIUX.md` record the 2026-08-31 expert review and what was fixed. `USER_GUIDE.md` (and `_AR.md`) describe every UI element and are updated when features ship.

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

**Scheduler pipeline** (`app/scheduler.py`): `intraday` every 10 min in session → alerts + guardian; `post_close` 15:00 Sun–Thu → snapshot universe → EGX30 index → rule scanner → candidates → alerts → guardian → scorecard grading → leaders → patterns → setups (order matters: later stages read what earlier ones persisted); `morning_brief` 09:30 (needs `ANTHROPIC_API_KEY`); `weekly_maintenance` Sat (prune, proven-edge recompute, VACUUM backup, symbol probe); hourly `catchup` re-runs post_close if a session's snapshot is missing. Every job is wrapped so it never raises, records a `job_runs` row (nested stage errors count as failure), and pings Telegram once on the transition into failure. Jobs gate on `calendar_egx.is_trading_day()` because cron only knows weekdays.

**Decision loop the services implement.** Scanners and rules journal hits into `scanner_hits` → `scorecard` grades each hit by 5/10/20-session excess return vs EGX30 → per-scanner beat rates become weights in `screeners.candidates()` ranking → `replay` seeds this from years of history (`source='replay'` rows are track record only, never shown as today's candidates and never pruned) → `edge` summarises which rules/scanners/patterns actually work. `checklist` (buy, six pillars) and `sell_checklist` (hold/sell, six pillars) reuse `levels`, `patterns`, `leaders`, `weekly`; `setups` runs the buy checklist across candidates + leaders + watchlist + holdings; `guardian` issues exit verdicts for open positions; `compare` ranks 2–4 symbols using all of the above. Long computations (replay, edge) run through `bgjob` (one daemon-thread slot, UI polls status).

**Frontend.** Five pages, each self-contained; shared `web/assets/{api.js, ui.js, charts.js, pg.js, app.css, pg.css}`. `ui.js` provides `el()` (no innerHTML path, on purpose — XSS), formatters, sidebar/topbar/footer, symbol autocomplete; `pg.js` is the table/panel framework used by screener/backtest/portfolio. Non-`/api` responses carry `Cache-Control: no-cache` so users see new frontends after an update. State-changing requests with a foreign `Origin` are rejected (CSRF guard for body-less cost-bearing POSTs).

## Trip hazards (verified in past sessions)

- `tradingview_mcp` batched screeners need the exchange key lowercase `"egx"`; uppercase silently falls back to the crypto screener. MTF/debate calls need the `EGX:`-prefixed form.
- APScheduler weekdays are mon=0..sun=6, so `day_of_week="sun-thu"` raises; spell days out (`"sun,mon,tue,wed,thu"`).
- Trade-plan payload nests levels under `trade_setup.{entry_points.{breakout_entry,pullback_entry}, stop_loss, targets.{target_1,target_2}, risk_reward.{...}}`; live score is `analysis.stock_score`, sub-scores at `trade_plan.score_breakdown`.
- `positions.stop` is the *current* protective stop (the guardian raises it); `positions.initial_stop` is the frozen risk anchor for R-multiples. Portfolio PnL is net of `FEE_PCT_PER_SIDE` on both legs.
- `app/services/briefs.py` uses the current Anthropic SDK pattern (`client.beta.messages.stream(model="claude-opus-5", thinking={"type":"adaptive"}, betas=[...], fallbacks="default")`) — do not "modernize" it backwards. Dependency versions in `requirements.txt` are pinned deliberately.
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