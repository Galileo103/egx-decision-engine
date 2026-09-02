# Handover — EGX Decision Engine

**Date:** 2026-08-27 → 2026-08-28 · **Project:** `D:\MyApps\egx-decision-engine` · **App URL:** http://127.0.0.1:8646

---

## Current Status

### Finished (verified working)
- **Full application built end-to-end** via a 14-agent ultracode workflow (8 parallel builders → integrator → live smoke test → 3 adversarial reviewers → fix engineer), all coding against `CONTRACT.md`.
- **Backend:** FastAPI app importing `tradingview_mcp.core.*` directly (editable install of the user's fork at `C:\Users\galal\OneDrive\Desktop\galal_borsa\tradingview-mcp`). ~35 endpoints: market overview/breadth, EGX30/70/100 index analysis, sector rotation, stock detail (score + trade plan + Fibonacci + MTF + smart money + debate), 6 scanners + merged candidates ranking, 9-strategy backtests (single/compare/walk-forward), watchlist, portfolio with R-multiples and open-risk, alert rules (5 types) + Telegram delivery, Claude-powered morning brief / stock thesis.
- **Frontend:** 5 vanilla-JS pages (dashboard, stock, screener, backtest, portfolio) on a shared dark-terminal design system; Lightweight Charts v4 with entry/stop/target/fib overlays.
- **Scheduler:** APScheduler on Africa/Cairo, 4 jobs (intraday alerts every 10 min in session, post-close snapshot+candidates 15:00, morning brief 09:30, weekly maintenance Sat). Verified `scheduler_running=True, jobs=4`.
- **Verification:** 13/13 live-data smoke checks passed; 8 review defects found, fixed, re-verified; `pytest tests -q` → 6/6 pass; server boots and serves the dashboard.
- **The server was left RUNNING** (hidden process; PID in `%TEMP%\egx_pid.txt`). Stop: `taskkill /PID (Get-Content $env:TEMP\egx_pid.txt) /F`. Start: `.venv\Scripts\python.exe run.py` from project root.

### Half-done / not yet exercised
- **Snapshots table is nearly empty** — score history, snapshot-backed alerts (`score_min`, `squeeze`, `signal_change`), and the portfolio-vs-EGX30 comparison stay thin until the first post-close job runs (15:00 Cairo, Sun–Thu) or a manual `POST /api/market/snapshot`.
- **LLM briefs, Telegram alerts, and news sentiment are wired but never run live** — no `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, or `MARKETAUX_API_TOKEN` in `.env` yet.
- **No end-to-end browser test of the UI** — endpoints and asset loading verified over HTTP; nobody has clicked through the pages in a real browser.

## Active Blockers

None hard. Soft blockers:
1. **Missing API keys** (above) gate briefs/Telegram/news — user must supply.
2. **TradingView scanner rate-limiting:** after heavy request bursts the upstream returns empty bodies for a few minutes (observed during integration; recovered on its own). App degrades to `{"error": ...}` payloads by design.
3. **Port 8642 is unusable on this machine** (inside Windows' reserved TCP range) — `.env` pins `PORT=8646`. Don't "fix" this back.
4. Stale Pyright import warnings may appear in the IDE; `pyrightconfig.json` points at `.venv` — they are noise (`py_compile`, pytest, and boot all pass).

## Next Steps (in order)

1. Click-through QA in a real browser on http://127.0.0.1:8646 — dashboard, `stock.html?symbol=COMI` (chart overlays, R:R banner, tabs), screener run + candidates, one backtest + compare + walk-forward, portfolio position open/close, alert rule create/toggle/fire.
2. Run `POST /api/market/snapshot` once to seed the snapshots table; confirm score history appears on stock pages and snapshot-backed alert rules evaluate.
3. Ask the user for the three optional keys; put them in `.env`; then test `POST /api/brief/morning`, a Telegram-delivered alert, and the News tab.
4. Let the scheduler run through one full trading day (Sun–Thu); check `GET /api/status` and the `job_runs` table for `ok=1` rows on all 4 jobs.
5. (Backlog, from the plan artifact) Limit-locked stock flagging, liquidity filters as first-class screener params, journal plan-vs-actual analytics, signal-performance feedback loop into score weights.

## Key Context

- **Contract-first architecture:** `CONTRACT.md` (project root) is the authoritative spec — file ownership, interfaces, DB schema, route table, frontend design system. Read it before changing anything.
- **Layout:** `app/config.py` (Settings singleton from `.env`), `app/db.py` (sqlite3 + WAL + lock; DB at `data/egx.db`; 8 tables incl. `snapshots`, `alert_rules`, `positions`, `job_runs`), `app/calendar_egx.py` (Cairo session Sun–Thu 10:00–14:30 + 2026 holidays), `app/symbols.py` (**`tv_to_yahoo`: `EGX:COMI` → `COMI.CA` — required on every Yahoo path**), `app/services/{market,stocks,screeners,backtests,alerts,portfolio,briefs,history}.py`, `app/scheduler.py`, `app/api/routes_*.py`, `app/main.py`, `web/` (static, no build step; shared `web/assets/{app.css,api.js,ui.js,charts.js}`).
- **Core-library conventions (trip hazards):** exchange key must be lowercase `"egx"` for batched screeners (uppercase silently falls back to the crypto screener); core functions never raise — they return `{"error": ...}` dicts, which the API passes through as HTTP 200; MTF/debate calls need the `EGX:`-prefixed symbol form.
- **APScheduler gotcha (was the critical bug):** `day_of_week="sun-thu"` is an inverted range and raises — use `"sun,mon,tue,wed,thu"`.
- **Trade-plan payload shape:** levels are nested under `trade_setup.{entry_points.{breakout_entry,pullback_entry}, stop_loss, targets.{target_1,target_2}, risk_reward.{to_target_1,to_target_2}}`; live score is `analysis.stock_score`, sub-scores at `trade_plan.score_breakdown` (was the big frontend bug).
- **LLM pattern (current 2026 API — do not "modernize" backwards):** `client.beta.messages.stream(model="claude-opus-5", thinking={"type":"adaptive"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default", ...)` in `app/services/briefs.py`.
- **Docs:** implementation plan artifact: https://claude.ai/code/artifact/8b0f880a-06ea-4310-8a13-0a69036c4380 · workflow run `wf_bd175583-18a` (resumable) · project memory saved at `~/.claude/projects/D--MyApps/memory/egx-decision-engine.md`.

*Analysis tooling, not financial advice.*
