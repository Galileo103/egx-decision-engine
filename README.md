# EGX Decision Engine

Single-user, local-first decision-support web app for the Egyptian Exchange
(EGX). It wraps the locally installed `tradingview_mcp` analytics core with a
FastAPI backend, a SQLite store, a background scheduler, and a dark
financial-dashboard frontend — all running on your machine, no accounts, no
order execution.

> **Disclaimer:** This is analysis tooling, **not financial advice**. Data is
> delayed (~15 minutes) and index/holiday/lunar-calendar data is best-effort.
> Every verdict shows its reasons; you make the decisions.

## Quickstart

```powershell
cd D:\MyApps\egx-decision-engine

# 1. Activate the virtualenv (already created)
.venv\Scripts\Activate.ps1

# 2. Configure (optional — the app runs fine with all defaults)
copy .env.example .env
# edit .env: add ANTHROPIC_API_KEY for LLM briefs, Telegram tokens for alerts

# 3. Run
python run.py
```

Then open **http://127.0.0.1:8642** in your browser (or whatever `PORT` your
`.env` sets — the port is printed on startup).

> **Windows port note:** on some Windows machines the default port 8642 falls
> inside a dynamically *reserved* TCP range (Hyper-V/WinNAT), and binding fails
> with `WinError 10013`. Check with
> `netsh interface ipv4 show excludedportrange protocol=tcp` and, if 8642 is
> reserved, set a free port in `.env` (this repo's `.env` already sets
> `PORT=8646` for that reason). The frontend uses relative URLs, so any port
> works.

Dependencies are listed in `requirements.txt`; the analytics core is an
editable install of `tradingview-mcp` from
`C:\Users\galal\OneDrive\Desktop\galal_borsa\tradingview-mcp`.

## Feature tour

- **Dashboard** (`/`) — market breadth, EGX session open/closed pill (Cairo
  time, Sun–Thu 10:00–14:30, 2026 holiday calendar), global market strip,
  top gainers / losers / most-active, sector heatmap, ranked candidate list
  from the merged scanners, and the latest AI morning brief.
- **Stock page** (`/stock.html?symbol=COMI`) — candlestick chart with
  trade-plan overlay (entry / stop / targets / Fibonacci levels), composite
  score card, generated trade plan with R:R quality grade, multi-timeframe
  alignment grid, smart-money analysis, news & sentiment, multi-agent
  bull/bear debate, AI thesis, and a position-size calculator.
- **Screener** (`/screener.html`) — run individual scanners (Bollinger
  squeeze, volume breakout, smart volume, momentum candles, smart money,
  custom screen) or the flagship **Candidates** mode that merges all scanners
  and ranks symbols by hit count and score.
- **Backtest** (`/backtest.html`) — run any of the built-in strategies over
  Yahoo history with commission/slippage costs, compare all strategies, or
  walk-forward test; equity curve and trade log included.
- **Portfolio & alerts** (`/portfolio.html`) — open/close positions with
  risk-based position sizing, mark-to-market performance (win rate, average
  R, open risk), and alert rules (price levels, score threshold, squeeze,
  signal change, entry hit) with optional Telegram delivery.
- **Scheduler** — background jobs in Cairo time: intraday alert evaluation
  every 10 minutes during the session, post-close universe snapshot +
  candidate scan, optional AI morning brief at 09:30, weekly symbol-list
  maintenance on Saturdays. Disable with `SCHEDULER_ENABLED=0`.

## Architecture

```
browser (vanilla JS + Lightweight Charts)
   │  static files from web/
   ▼
FastAPI  app/main.py  ──  /api/* routes (app/api/routes_*.py)
   │        thin handlers → asyncio.to_thread → sync services
   ▼
services  app/services/
   market · stocks · screeners · backtests · alerts · portfolio · briefs · history
   │                                   │
   │ tradingview_mcp.core              │ SQLite (data/egx.db, WAL)
   │ (TradingView scanners, TA,        │ snapshots · scanner_hits · watchlist
   │  Yahoo prices, backtests,         │ alert_rules · alerts_fired · positions
   │  Marketaux news, Claude agents)   │ briefs · job_runs
   ▼                                   ▼
foundation  app/config.py · app/db.py · app/calendar_egx.py · app/symbols.py
scheduler   app/scheduler.py (APScheduler, Africa/Cairo)
```

Data sources: TradingView scanner data via `tradingview_mcp`, Yahoo Finance
v8 chart API for OHLCV history and prices, Marketaux for news (optional
token), Anthropic Claude for briefs (optional key).

## Configuration

All settings live in `.env` (see `.env.example` for the full annotated
list): `HOST`, `PORT`, `DB_PATH`, `ANTHROPIC_API_KEY`,
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `SCHEDULER_ENABLED`,
`ACCOUNT_SIZE`, `RISK_PCT`, `MARKETAUX_API_TOKEN`.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests\
```

---

*Analysis tooling — not financial advice. Data delayed ~15 min.*
