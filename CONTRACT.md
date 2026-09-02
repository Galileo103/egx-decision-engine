# EGX Decision Engine — Build Contract

This document is the single source of truth for the multi-agent build. Every builder
MUST read this file fully before writing code, MUST only create/modify the files it
owns, and MUST match the interfaces here exactly. Where a core-library signature is
marked "READ SOURCE", open the referenced file and match the real signature.

## Product

Single-user, local-first decision-support web app for the Egyptian Exchange (EGX).
Analytics come from the locally installed `tradingview_mcp.core` package (editable
install of `C:\Users\galal\OneDrive\Desktop\galal_borsa\tradingview-mcp`).
No auth. No order execution. Every verdict shows its reasons. Visible
"analysis, not financial advice" disclaimer in the UI footer.

## Environment

- Windows 11. Project root: `D:\MyApps\egx-decision-engine`
- Python venv: `D:\MyApps\egx-decision-engine\.venv` (already created; deps installing:
  fastapi, uvicorn[standard], apscheduler, jinja2, anthropic, tzdata, python-dotenv,
  httpx, pytest, and `tradingview-mcp-server` editable).
- Run server: `.venv\Scripts\python.exe run.py` → uvicorn on `127.0.0.1:8642`.
- Syntax check your own files: `.venv\Scripts\python.exe -m py_compile <file>` —
  if the venv is not ready yet, use system `python` for py_compile only.
- DO NOT launch the server as a builder (the integrator does that).

## Project layout & file ownership

```
egx-decision-engine/
  CONTRACT.md               (this file — read-only)
  run.py                    A
  requirements.txt          A
  .env.example              A
  README.md                 A
  app/__init__.py           A (empty)
  app/config.py             A
  app/db.py                 A
  app/calendar_egx.py       A
  app/symbols.py            A
  app/services/__init__.py  A (empty)
  app/services/history.py   A
  app/services/market.py    B
  app/services/stocks.py    B
  app/services/screeners.py C
  app/services/backtests.py C
  app/services/alerts.py    D
  app/services/portfolio.py D
  app/scheduler.py          D
  app/services/briefs.py    H
  app/api/__init__.py       E (empty)
  app/api/routes_market.py  E
  app/api/routes_stocks.py  E
  app/api/routes_screener.py E
  app/api/routes_backtest.py E
  app/api/routes_portfolio.py E
  app/api/routes_alerts.py  E
  app/api/routes_brief.py   E
  app/main.py               E
  web/assets/app.css        F
  web/assets/api.js         F
  web/assets/ui.js          F
  web/assets/charts.js      F
  web/index.html            F   (dashboard)
  web/stock.html            F
  web/screener.html         G
  web/backtest.html         G
  web/portfolio.html        G
  tests/test_smoke.py       E
```

## Core library usage (tradingview_mcp)

Source root: `C:\Users\galal\OneDrive\Desktop\galal_borsa\tradingview-mcp\src\tradingview_mcp\`
Import as installed package, e.g. `from tradingview_mcp.core.services import egx_service`.
ALL core functions return plain dicts/lists; error results are dicts with an `"error"` key —
always propagate them as-is (HTTP 200 with `{"error": ...}` is fine for v1).

Key entry points (READ SOURCE for exact params before calling):

| Module | Functions |
|---|---|
| `core.services.egx_service` | `get_egx_market_overview(timeframe, limit)`, `scan_egx_sector(sector, timeframe, limit)`, `run_egx_sector_scanner(...)`, `analyze_egx_index(index, timeframe, limit)`, `screen_egx_stocks(...)`, `generate_egx_trade_plan(symbol, timeframe)`, `analyze_egx_fibonacci(...)` |
| `core.services.screener_service` | `analyze_coin(symbol, exchange, timeframe)` (full TA; use exchange="EGX"), `run_multi_timeframe_analysis(symbol, exchange)`, `fetch_bollinger_analysis(...)`, `scan_consecutive_candles(...)`, `scan_advanced_candle_patterns_single_tf(...)` |
| `core.services.scanner_service` | `volume_breakout_scan(...)`, `volume_confirmation_analyze(...)`, `smart_volume_scan(...)` |
| `core.services.smart_money_service` | `analyze_smart_money(symbol, exchange, ...)`, `scan_egx_smart_money(index, ...)`, `yahoo_symbol_for(symbol, exchange)` |
| `core.services.backtest_service` | `run_backtest(symbol, strategy, ...)`, `compare_strategies(...)`, `walk_forward_backtest(...)` — these take YAHOO symbols (EGX → `SYM.CA`) |
| `core.services.yahoo_finance_service` | `get_price(symbol)`, `get_prices_bulk(symbols)`, `get_market_snapshot()` |
| `core.services.marketaux_service` | `fetch_news_summary(...)`, `analyze_sentiment(...)` (needs MARKETAUX_API_TOKEN env; degrade gracefully) |
| `core.services.multi_agent_service` | `run_multi_agent_analysis(...)` |
| `core.data.egx_indices` | `EGX30_CONSTITUENTS`, `EGX70_CONSTITUENTS`, plus others (READ SOURCE; there is a dict mapping index name → list) |
| `core.data.egx_sectors` | sector → symbols mapping (READ SOURCE) |
| `core.services.coinlist` | `load_symbols("egx")` → full EGX symbol list |

Timeframes: TradingView intervals `"15m" "1h" "4h" "1D" "1W"`. Default `"1D"` everywhere.

## Module A — foundation (interfaces other agents code against)

### app/config.py
```python
class Settings:  # loaded once, from .env via python-dotenv (load_dotenv at import)
    host: str = "127.0.0.1"; port: int = 8642
    db_path: str  # default "<project>/data/egx.db"; parent dir auto-created
    anthropic_api_key: str | None
    telegram_bot_token: str | None; telegram_chat_id: str | None
    scheduler_enabled: bool = True   # env SCHEDULER_ENABLED=0 disables
    account_size: float = 100_000.0  # env ACCOUNT_SIZE, EGP, for position sizing default
    risk_pct: float = 1.0            # env RISK_PCT
settings = Settings()  # module-level singleton
```

### app/db.py  (sqlite3 stdlib, no ORM)
```python
def get_conn() -> sqlite3.Connection   # row_factory=sqlite3.Row, check_same_thread=False, WAL mode
def init_db() -> None                  # CREATE TABLE IF NOT EXISTS for all tables below
def query(sql, params=()) -> list[dict]
def execute(sql, params=()) -> int     # returns lastrowid; commits
```
A single module-level connection guarded by a `threading.Lock` is acceptable.

Tables (init_db creates exactly these):
```sql
snapshots(id INTEGER PK AUTOINCREMENT, symbol TEXT, date TEXT, timeframe TEXT,
          price REAL, change_pct REAL, volume REAL, rsi REAL, bbw REAL,
          rating INTEGER, signal TEXT, score REAL, score_json TEXT, created_at TEXT,
          UNIQUE(symbol, date, timeframe))
scanner_hits(id PK, date TEXT, scanner TEXT, symbol TEXT, payload_json TEXT, created_at TEXT)
watchlist(symbol TEXT PRIMARY KEY, note TEXT, added_at TEXT)
alert_rules(id PK, name TEXT, rule_type TEXT, params_json TEXT, enabled INTEGER DEFAULT 1, created_at TEXT)
alerts_fired(id PK, rule_id INTEGER, symbol TEXT, message TEXT, fired_at TEXT, delivered INTEGER DEFAULT 0)
positions(id PK, symbol TEXT, side TEXT DEFAULT 'long', qty REAL, entry REAL, stop REAL,
          target1 REAL, target2 REAL, opened_at TEXT, closed_at TEXT, exit_price REAL,
          plan_json TEXT, note TEXT, status TEXT DEFAULT 'open')
briefs(id PK, date TEXT, kind TEXT, symbol TEXT, content TEXT, created_at TEXT)
job_runs(id PK, job TEXT, started_at TEXT, finished_at TEXT, ok INTEGER, detail TEXT)
```

### app/calendar_egx.py
```python
CAIRO = ZoneInfo("Africa/Cairo")
def now_cairo() -> datetime
def is_trading_day(d: date | None = None) -> bool      # Sun–Thu, minus EGX_HOLIDAYS set (hardcode 2026 Egyptian public holidays, best effort)
def is_market_open(dt: datetime | None = None) -> bool # trading day and 10:00 <= t < 14:30 Cairo
def session_state() -> dict  # {"open": bool, "now_cairo": iso, "next_open": iso, "is_trading_day": bool}
```

### app/symbols.py
```python
def tv_to_yahoo(symbol: str) -> str        # "COMI" -> "COMI.CA" (strip "EGX:" prefix if present)
def universe(name: str) -> list[str]       # "EGX30"|"EGX70"|"EGX100"|"ALL"|... -> symbols, from core.data.egx_indices / coinlist
def universes() -> list[str]               # available names
def is_valid_symbol(symbol: str) -> bool   # membership in load_symbols("egx")
```

### app/services/history.py
```python
def get_history(symbol: str, range_: str = "1y", interval: str = "1d") -> dict
# Yahoo v8 chart API via httpx GET
# https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval={interval}&range={range_}
# with User-Agent header "Mozilla/5.0". Map symbol via tv_to_yahoo().
# Returns {"symbol", "candles": [{"time": "YYYY-MM-DD", "open","high","low","close","volume"}...]}
# or {"error": "..."}. In-memory TTL cache 10 min. Skip null candles.
```

### run.py — argparse-free: load settings, uvicorn.run("app.main:app", host, port, reload=False)
### requirements.txt — list the deps named above (pin nothing except what pyproject pins)
### .env.example — every env var with comments
### README.md — quickstart (venv activate, copy .env, run.py, open http://127.0.0.1:8642), feature tour, disclaimer

## Module B — market & stocks services

### app/services/market.py
```python
def overview(timeframe="1D", limit=10) -> dict       # egx_service.get_egx_market_overview + adds "breadth": {advancers, decliners, unchanged, pct_advancing} computed from its data; adds "session": calendar_egx.session_state(); adds "as_of"
def index_analysis(index="EGX30", timeframe="1D") -> dict
def sectors(timeframe="1D") -> dict                  # run_egx_sector_scanner output
def sector_detail(sector: str, timeframe="1D") -> dict
def global_snapshot() -> dict                        # yahoo_finance_service.get_market_snapshot()
def snapshot_universe(universe_name="EGX100", timeframe="1D") -> dict
# snapshot_universe: for each symbol in universe pull overview data via egx_service internals OR
# reuse get_egx_market_overview(limit=20) plus screen_egx_stocks; persist one row per symbol
# into snapshots table (INSERT OR REPLACE, date = today Cairo). Returns {"saved": n, "date": ...}.
# Include per-symbol score via indicators.compute_stock_score where indicators are available.
```
In-memory TTL cache (60s intraday) on overview/sectors/index. Module-level `_cache` dict is fine.

### app/services/stocks.py
```python
def detail(symbol: str, timeframe="1D") -> dict
# Composite: analyze_coin(symbol, "EGX", timeframe) + generate_egx_trade_plan + analyze_egx_fibonacci
# + score history from snapshots table (last 90 rows) + watchlist membership flag.
# Run the three core calls; tolerate individual failures ({"error": ...} sub-keys).
def mtf(symbol: str) -> dict                  # run_multi_timeframe_analysis(symbol, "EGX")
def smart_money(symbol: str) -> dict          # analyze_smart_money(symbol, "EGX")
def news(symbol: str) -> dict                 # marketaux fetch_news_summary/analyze_sentiment; {"error": "..."} if no token
def debate(symbol: str, timeframe="1D") -> dict  # run_multi_agent_analysis
```

## Module C — screeners & backtests services

### app/services/screeners.py
```python
SCANNERS: dict[str, dict]  # registry: key -> {"label", "description", "params": {name: default}}
# keys: "squeeze" (bollinger BBW), "volume_breakout", "smart_volume", "momentum" (consecutive candles),
#        "smart_money" (scan_egx_smart_money), "custom" (screen_egx_stocks passthrough)
def run_scanner(key: str, params: dict) -> dict   # dispatch to core; always exchange/universe EGX; normalize to {"scanner": key, "results": [...], "as_of": iso}
def candidates(timeframe="1D", persist=False) -> dict
# THE flagship: run squeeze + volume_breakout + smart_money + momentum with sane defaults,
# merge hits by symbol, count scanner_hits per symbol, attach score (compute_stock_score via analyze_coin
# for the top ~15 merged symbols only — keep it bounded), rank by (hit_count, score), and return
# {"candidates": [{symbol, scanners: [...], score, price, change_pct, signal, ...}], "as_of"}.
# persist=True → write rows into scanner_hits table.
```

### app/services/backtests.py
```python
STRATEGIES: list[str]  # read the literal strategy names from backtest_service source (9 of them)
def run(symbol, strategy, period="1y", interval="1d", commission_pct=0.3, slippage_pct=0.1, initial_capital=100000) -> dict   # maps symbol via tv_to_yahoo
def compare(symbol, period="1y", interval="1d") -> dict
def walk_forward(symbol, strategy, period="2y", interval="1d") -> dict
```
Match the real `run_backtest`/`compare_strategies`/`walk_forward_backtest` signatures (READ SOURCE);
pass costs through if supported.

## Module D — alerts, portfolio, scheduler

### app/services/alerts.py
Rule types (`rule_type` + `params_json`):
- `price_above` / `price_below`: {"symbol", "level"}
- `score_min`: {"universe" or "symbol", "threshold"}
- `squeeze`: {"universe", "bbw_max"}          (fires per symbol entering squeeze)
- `signal_change`: {"symbol"}                 (signal in latest snapshot differs from previous)
- `entry_hit`: {"symbol"}                     (price crosses stored trade-plan entry from detail; params carry "entry")
```python
def create_rule(name, rule_type, params: dict) -> dict
def list_rules() -> list[dict];  def delete_rule(rule_id) -> None;  def toggle_rule(rule_id, enabled) -> None
def evaluate_all() -> dict   # {"evaluated": n, "fired": [...]}; dedupe: don't refire same rule+symbol within 6h (check alerts_fired)
def send_telegram(text: str) -> bool  # httpx POST api.telegram.org/bot{token}/sendMessage; False + log if unconfigured
```
Fired alerts always insert into alerts_fired; delivered=1 only if telegram send succeeded.
Price checks use `yahoo_finance_service.get_price(tv_to_yahoo(sym))` (fast) with EGX screener fallback.

### app/services/portfolio.py
```python
def size_position(account: float, risk_pct: float, entry: float, stop: float) -> dict
# {"shares": int, "risk_amount", "position_cost", "risk_reward_note"}; validate stop < entry for long; risk_pct cap warning >2
def open_position(symbol, qty, entry, stop, target1=None, target2=None, plan: dict|None=None, note="") -> dict
def close_position(position_id, exit_price) -> dict     # computes pnl, pnl_pct, r_multiple = (exit-entry)/(entry-stop)
def list_positions(status="all") -> list[dict]
def performance() -> dict  # open positions marked to market (get_prices_bulk), realized pnl, win_rate, avg_r, open_risk (Σ per-position risk if stop hit), vs EGX30 note if snapshot data allows
```

### app/scheduler.py
```python
def start_scheduler(app) -> None  # called from main.py startup if settings.scheduler_enabled
```
APScheduler BackgroundScheduler, timezone Africa/Cairo. Jobs (each wrapped: log to job_runs, never raise):
- `intraday`: cron sun–thu, 10:00–14:29 every 10 min → alerts.evaluate_all()
- `post_close`: cron sun–thu 15:00 → market.snapshot_universe("EGX100"), screeners.candidates(persist=True), alerts.evaluate_all()
- `morning_brief`: cron sun–thu 09:30 → briefs.morning_brief() only if anthropic key set
- `weekly_maintenance`: cron sat 12:00 → symbols validation: count symbols in load_symbols("egx") that return no data from a 1-batch screener probe; log to job_runs
Also `def job_status() -> dict` (last run per job from job_runs + next fire times).

## Module H — LLM briefs (app/services/briefs.py)

Python `anthropic` SDK. Model **`claude-opus-5`**. Pattern (this is current API — do not "fix" it):
```python
from anthropic import Anthropic
client = Anthropic(api_key=settings.anthropic_api_key)
with client.beta.messages.stream(
    model="claude-opus-5", max_tokens=16000,
    thinking={"type": "adaptive"},
    betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    system=SYSTEM, messages=[{"role": "user", "content": prompt}],
) as stream:
    msg = stream.get_final_message()
if msg.stop_reason == "refusal": return {"error": "brief refused"}
text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
```
If the installed SDK rejects `fallbacks`/`betas` kwargs (TypeError), retry once with plain
`client.messages.stream(model=..., thinking={"type":"adaptive"}, ...)`.
```python
def morning_brief() -> dict   # gathers market.overview + screeners.candidates + alerts fired since yesterday + open positions, builds ONE prompt, saves to briefs(kind='morning'), returns {"content", "date"}
def stock_thesis(symbol: str) -> dict  # stocks.detail + mtf + smart_money + news → prompt → briefs(kind='thesis', symbol=...)
def latest(kind="morning", symbol=None) -> dict
```
No key → `{"error": "ANTHROPIC_API_KEY not configured"}`. System prompt: senior EGX analyst,
Arabic-aware English output, cite numbers from the provided JSON only, end with "Not financial advice."

## Module E — API layer

FastAPI. All routes under `/api`. JSON only. Route → service mapping is 1:1, thin handlers;
run blocking service calls via `await asyncio.to_thread(...)` (services are sync).
`app/main.py`: create app, `init_db()` + `start_scheduler(app)` on startup (lifespan),
include all routers, then `app.mount("/", StaticFiles(directory="web", html=True))` LAST.

| Method+Path | Service call |
|---|---|
| GET /api/health | {"ok": true, "session": calendar_egx.session_state()} |
| GET /api/status | scheduler.job_status() |
| GET /api/market/overview?timeframe= | market.overview |
| GET /api/market/index/{index} | market.index_analysis |
| GET /api/market/sectors | market.sectors |
| GET /api/market/sector/{name} | market.sector_detail |
| GET /api/market/global | market.global_snapshot |
| POST /api/market/snapshot | market.snapshot_universe |
| GET /api/stocks/{symbol}?timeframe= | stocks.detail |
| GET /api/stocks/{symbol}/mtf | stocks.mtf |
| GET /api/stocks/{symbol}/smart-money | stocks.smart_money |
| GET /api/stocks/{symbol}/news | stocks.news |
| GET /api/stocks/{symbol}/debate | stocks.debate |
| GET /api/stocks/{symbol}/history?range=&interval= | history.get_history |
| GET /api/screener/list | screeners.SCANNERS |
| GET /api/screener/run/{key}?... (query params passed as dict) | screeners.run_scanner |
| GET /api/screener/candidates | screeners.candidates |
| GET/POST/DELETE /api/watchlist[/{symbol}] | direct db (watchlist table); GET enriches with get_prices_bulk |
| POST /api/backtest | backtests.run (body: symbol, strategy, period, interval, costs) |
| POST /api/backtest/compare | backtests.compare |
| POST /api/backtest/walkforward | backtests.walk_forward |
| GET /api/backtest/strategies | backtests.STRATEGIES |
| GET/POST /api/alerts/rules, DELETE /api/alerts/rules/{id}, POST /api/alerts/rules/{id}/toggle | alerts.* |
| GET /api/alerts/fired?limit=50 | db query |
| POST /api/alerts/evaluate | alerts.evaluate_all |
| POST /api/portfolio/size | portfolio.size_position |
| GET /api/portfolio/positions?status= | portfolio.list_positions |
| POST /api/portfolio/positions | portfolio.open_position |
| POST /api/portfolio/positions/{id}/close | portfolio.close_position |
| GET /api/portfolio/performance | portfolio.performance |
| POST /api/brief/morning | briefs.morning_brief |
| POST /api/brief/thesis/{symbol} | briefs.stock_thesis |
| GET /api/brief/latest?kind=&symbol= | briefs.latest |

`tests/test_smoke.py`: TestClient over app.main:app — /api/health 200, /api/screener/list 200,
/api/backtest/strategies 200, portfolio size math, watchlist CRUD. No live-network asserts.

## Modules F & G — frontend

Vanilla JS + HTML, no build step. Served statically. Shared assets are owned by F; G uses them.

Design system (both agents follow exactly):
- Dark financial UI. Tokens in app.css `:root`:
  `--bg:#0E1316; --panel:#161D22; --panel2:#1C242A; --line:#26313A; --ink:#E8E6DE;
   --muted:#8B958F; --accent:#2FBFA0; --up:#34C77B; --down:#E5534B; --warn:#D2A44C;`
- Fonts (Google Fonts link in every page): Archivo (headings/UI), IBM Plex Mono (numbers/tickers).
  `font-variant-numeric: tabular-nums` on all numeric cells.
- Every page: left sidebar nav (Dashboard, Screener, Backtest, Portfolio + watchlist quick list),
  top bar with market open/closed pill (from /api/health session) + symbol search box
  (datalist populated from /api/market/overview symbols; Enter → stock.html?symbol=X),
  footer disclaimer "Analysis tooling — not financial advice. Data delayed ~15 min."
- `web/assets/api.js`: `window.API = { get(path), post(path, body), del(path) }` returning parsed
  JSON; on `{"error": ...}` in payload, throw with that message; `ui.js` provides
  `toast(msg, kind)`, `fmtNum`, `fmtPct` (color class up/down), `el(tag, attrs, children)` helper,
  `renderSidebar(active)`, `renderTopbar()` — pages call these on load.
- `charts.js`: Lightweight Charts **v4** CDN
  `<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js">`
  helper `renderCandles(containerId, candles, overlays)` (candlestick + volume histogram; overlay
  horizontal price lines for entry/stop/targets/fib levels via createPriceLine).
- Loading states: skeleton shimmer or "Loading…" pill on every fetch; failed fetch → inline error box, never blank page.

Pages (each self-contained: fetches on DOMContentLoaded):
- F `index.html` Dashboard: market stat row (breadth, EGX session pill, global snapshot strip),
  top gainers/losers/most-active tables (symbol cells link to stock page), sector heatmap
  (CSS grid tiles colored by change), candidates panel (top 10 from /api/screener/candidates
  with hit badges), latest morning brief (rendered as text, "Generate" button → POST /api/brief/morning).
- F `stock.html?symbol=X`: header (price, change, signal badge, watchlist star toggle),
  candlestick chart with trade-plan overlay lines, score card with sub-score bars,
  trade plan card (entry/stop/T1/T2, R:R, quality grade; "Reject: R:R < 2" red banner when so),
  MTF alignment grid (5 timeframes × trend/momentum), tabs: Smart Money / Fibonacci / News / Debate / Thesis
  (thesis tab: latest + "Generate" button), position-size widget (account, risk% → shares; prefilled from plan).
- G `screener.html`: scanner picker (from /api/screener/list) + dynamic param form, run button,
  results table (sortable by column click), "Candidates" mode showing merged ranked list with
  per-scanner badges; row click → stock page.
- G `backtest.html`: form (symbol w/ datalist, strategy select from /api/backtest/strategies, period,
  interval, costs), results: metric cards (return, win rate, max DD, sharpe, trades, vs buy-and-hold),
  equity curve via charts.js line series, trade log table; "Compare all" tab → strategy ranking table;
  "Walk-forward" tab → in/out-of-sample result panels.
- G `portfolio.html`: performance cards (realized PnL, win rate, avg R, open risk), open positions
  table with mark-to-market + close button (prompt for exit price), closed positions history,
  "New position" form (symbol, qty, entry, stop, targets), alerts section: rules table
  (create form with rule-type select + dynamic params, toggle/delete), fired alerts feed.

## Conventions

- Python 3.12, type hints, docstrings on public functions. No new third-party deps beyond requirements.txt.
- All timestamps stored as ISO strings; "date" = Cairo local date string YYYY-MM-DD.
- Never let a scheduler job or route handler raise uncaught: catch Exception → {"error": str(exc)}.
- Frontend: no frameworks, no modules/bundlers — plain `<script src>` includes; ES2020 ok.
- Keep each file under ~500 lines where feasible; split helpers within the same owned file only.
