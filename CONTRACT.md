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
scanner_hits(id PK, date TEXT, scanner TEXT, symbol TEXT, payload_json TEXT, created_at TEXT,
             source TEXT DEFAULT 'live')   -- 'replay' rows come from services/replay.py: track record only,
                                           -- excluded from latest_candidates/setups, exempt from prune
signal_outcomes(..., source TEXT DEFAULT 'live',    -- mirrors the hit's source
                ret_40/bench_40/excess_40, ret_60/bench_60/excess_60 REAL,  -- 2026-09-06: swing-pattern horizons
                regime TEXT)                         -- 'bull'|'neutral'|'bear' on the entry date (regime_daily.at)
regime_daily(date TEXT PRIMARY KEY, state TEXT, index_close REAL, sma50 REAL, sma200 REAL, breadth_pct REAL,
             breadth_members INTEGER, source TEXT, computed_at TEXT)   -- services/regime.py, one row per session
proven_edge(kind TEXT, name TEXT, label TEXT, period TEXT, n INTEGER, hit_rate REAL, edge_metric REAL,
            metric_label TEXT, verdict TEXT, verdict_text TEXT, extra_json TEXT, universe TEXT,
            computed_at TEXT, PRIMARY KEY(kind, name))   -- services/edge.py, rebuilt whole on each compute
watchlist(symbol TEXT PRIMARY KEY, note TEXT, added_at TEXT)
review_notes(week_start TEXT PRIMARY KEY, text TEXT, updated_at TEXT)   -- services/review.py, one lesson per trading week
corporate_actions(id PK, symbol TEXT, type TEXT, ex_date TEXT, amount REAL, ratio REAL, note TEXT, source TEXT DEFAULT 'manual',
                  created_at TEXT, UNIQUE(symbol, type, ex_date, source))   -- services/corporate_actions.py
investor_flows(date TEXT, scope TEXT DEFAULT 'all', net_egyptians REAL, net_arab REAL, net_foreign REAL, net_individuals REAL,
               net_institutions REAL, net_foreign_inst REAL, total_value REAL, payload_json TEXT, source TEXT DEFAULT 'paste',
               created_at TEXT, PRIMARY KEY(date, scope))   -- services/flows.py; one pasted EGX Investor-Type page per session
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
def snapshot_universe(universe_name="EGX100", timeframe="1D", include_held=True) -> dict  # include_held: open positions + watchlist are appended to the universe (market.held_and_watched_symbols)
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

### app/services/replay.py — historical replay (Phase 1, 2026-09-04)
```python
def rule_hits(symbol, candles) -> list[dict]      # every session an ENTRY_RULES signal fired (rules_backtest._SIGNALS)
def pattern_hits(symbol, candles) -> list[dict]   # confirmed, directional, quality>=50 patterns on their break_date
def run(universe='EGX100', period='5y', patterns=True, limit=None) -> dict  # journal (source='replay') + grade at once
def start(...) / status() / summary() / clear()   # background job (services/bgjob.BackgroundJob)
```
### app/services/edge.py — Proven-edge table
```python
REFERENCE_HORIZON = {scanner: 10, checklist: 10, candlestick: 10, price_action: 20,
                     reversal/triangle/continuation/wedge/channel: 40}     # 2026-09-06
def rule_verdict(n, avg_r) -> 'edge'|'marginal'|'negative'|'too_few'
def beat_verdict(n, rate_vs_random_pp, excess_vs_random, se_excess) -> same  # relative to the horizon's baseline
def reference_horizon(name) -> int
def compute_baselines(universe, period='5y', horizons=None) -> {h: stats}  # random entry per horizon, each with by_regime{state: stats};
                                                                           # stored as proven_edge kind='baseline' name='random_entry_{h}d'
def compute_baseline(universe, period='5y', horizon=10) -> dict            # one-horizon wrapper
def compute(universe='EGX100', period='3y', exit_rule='guardian', persist=True) -> dict  # 4 universe_runs + scorecard rows
def latest() -> dict            # stored table, rules first; headline + summary + baselines + regime{current, counts, bull_only}
def start(...) / status()       # background job; weekly_maintenance also calls compute()
# scanner/pattern rows: verdict at the reference horizon; extra.horizon, extra.horizons{h: n/beat/excess/verdict},
# extra.by_regime{state: n/hit_rate/edge_metric/verdict}; rule rows: extra.by_regime from universe_run pooled.by_regime
```
### Investor-type flows (2026-09-06, TA roadmap Task 9)
```python
# app/services/flows.py — table investor_flows(date, scope, net_egyptians, net_arab, net_foreign, net_individuals, net_institutions,
#                                             net_foreign_inst, total_value, payload_json, source, created_at, PK(date, scope))
NATIONALITIES = ('egyptians','arab','foreign'); GROUPS = ('totals','individuals','institutions'); SCOPES = ('all','securities','bonds')
def parse_egx_text(text) -> {ok, totals, individuals, institutions, warnings} | {ok: False, error, ...}
#   splits the paste on "Individuals by Nationality" / "Institutions by Nationality" (Arabic headings accepted), reads
#   "<label> sell buy net" per nationality, recomputes net = buy - sell, keeps net_reported, warns on mismatches
def record(text, date=None, scope='all') -> {ok, date, scope, net_*, total_value, warnings, reading} | {error}  # date default = last trading day
def delete(date, scope='all'); def history(days=60, scope='all') -> rows oldest first (payload_json -> tables)
def latest(scope='all'); def summary(scope='all') -> {stored, latest, windows: {"5": {...,"net_foreign_neg_sessions"}, "20": {...}},
                                                       reading, series: [{date, net_*, total_value}], basis}
def reading(last, rows) -> str     # actor sentence, institutions-vs-individuals (accumulation / distribution), 5-session foreign streak
```
Source: the EGX page (www.egx.com.eg/en/InvestorsTypePieChart.aspx) sits behind an F5 JavaScript bot challenge — scripted fetches
receive the challenge page, so there is deliberately no scraper; the user pastes the page text. Routes (routes_flows.py):
GET /api/flows?scope=, GET /api/flows/history?days=&scope=, POST /api/flows/parse {text} (dry run), POST /api/flows/paste
{text, date?, scope?}, DELETE /api/flows/{date}?scope=. UI: Dashboard card "Investor flows — who bought, who sold" (tiles,
5/20-session lines, foreign-net bars, reading, paste panel).

### Corporate actions (2026-09-06, TA roadmap Task 8)
```python
# app/services/corporate_actions.py — table corporate_actions(id, symbol, type, ex_date, amount, ratio, note, source, created_at,
#                                                            UNIQUE(symbol,type,ex_date,source)); source = 'yahoo' | 'manual'
TYPES = ('dividend','split','rights','capital_increase','bonus','other'); EX_DATE_WARN_DAYS = 5; GAP_TOLERANCE_DAYS = 1
def record_yahoo(symbol, events) -> int          # from history payload["events"] (leaders.daily_candles books them on a fresh fetch)
def add(symbol, type_, ex_date, amount=None, ratio=None, note='') -> {ok,...}|{error}; def delete(id) (manual rows only)
def for_symbol(symbol, since=None) / upcoming(symbols=None, days=30, today=None) / next_for(symbol, within_days=5, today=None)
def warning_text(ev) -> str; def events_near(symbol, day) -> list; def tag_suspect(symbol, rows) -> int   # rows gain suspect, suspect_event
```
history.get_history requests `events=div,splits` and returns `events: [{type, date, amount|ratio, note}]`.
patterns.detect tags suspect rows before the view filter; checklist pillars 4–5 ignore suspect rows; checklist Risk pillar
appends `warning_text(next_for(sym))` (live only) with `event` and pass→warn; guardian gains `EX_DATE_SOON` (advice) via
`apply_corporate_actions(row, event=None)` after the sell checklist. Routes: GET /api/corporate-actions?symbol=&days=&mine=,
POST /api/corporate-actions {symbol,type,ex_date,amount?,ratio?,note?}, DELETE /api/corporate-actions/{id},
GET /api/stocks/{symbol}/corporate-actions. charts.js `opts.markers` → candleSeries.setMarkers (snaps to the next existing bar).
UI: Portfolio "Corporate actions" panel (form + upcoming for held/watchlist), stock chart markers + next-event chip,
pattern rows "event gap" chip.

### Sector relative strength (2026-09-06, TA roadmap Task 7)
```python
# app/services/leaders.py
SECTOR_PREFIX = "SECTOR:"; MIN_SECTOR_MEMBERS = 2
def sector_of(symbol) -> str|None; def sector_label(key) -> str|None
def sector_strength(rows, bench) -> [{sector, label, members, symbols, rank, rs_score, ret_1m/3m/6m, excess_1m/3m/6m, as_of}]
def attach_sectors(rows, sectors) -> None   # rows gain sector, sector_label, sector_rank, sector_count, sector_rs_score,
                                            #   rank_in_sector, sector_size, rs_vs_sector_1m, rs_vs_sector_3m
def sector_context(symbol, universe='EGX100') -> dict|None   # from the stored ranking (instant); {sector: None} if unclassified
def sector_sentence(ctx) -> str
compute() -> adds "sectors"; _persist stores sector rows as symbol 'SECTOR:<key>' in rs_leaders;
latest(universe, limit, sector=None) -> {rows, sectors, ranked, sector, ...}
```
checklist Trend pillar appends `leaders.sector_sentence(sector_context(sym))` (live only; replays skip it) and carries
`sector` on the pillar; compare columns carry `sector_rs`. Route GET /api/screener/leaders gains `sector=`.
UI: Screener Leaders tab (Sector select, collapsible sector table, Sector / In sector / vs sector 1m columns);
Compare "Sector strength" row; dashboard heatmap card links to the Leaders tab.

### Weekly review (2026-09-06, TA roadmap Task 6)
```python
# app/services/review.py
def week_bounds(ref: date|None) -> (sunday, thursday)     # Fri/Sat -> the week just ended
def attribute(symbol, opened_at) -> list[str]             # live non-pattern/non-checklist hits on the fill session or 4 days before
def you_vs_system(closed_rows) -> {rows[{rule, n, avg_r, win_rate, system_avg_r, system_win_rate, system_n, system_verdict, gap_r, read, symbols}], unattributed, basis}
def discipline(closed_rows) -> {followed_n, deviated_n, unanswered_n, avg_r_followed, avg_r_deviated, stops_lowered, discretionary_exits, exits_by_how, read}
def guardian_week(start, end) -> {rows[{date, symbol, position_id, verdict, severity, r_now, suggested_stop, acted, how, repeats, reason}], actionable, ignored, read}
def heat_series(start, end) -> [{date, open_positions, risk_egp, heat_pct}]   # current stops (approximation)
def compute(week: str|None) -> {week{start,end,label,sessions,prev,next}, headline, closed, opened, week_pnl_net, week_avg_r,
                                you_vs_system, discipline, guardian, heat, performance, regime, note, recent_notes, closed_all_count, basis}
def get_note(week_start) / save_note(week_start, text) / notes(limit)   # table review_notes(week_start PK, text, updated_at)
def digest_text(rev) -> str; def digest(send=True, week=None) -> {sent, text, week, error}
```
Routes (routes_review.py): GET /api/review?week=, POST /api/review/note {week_start, text}, GET /api/review/notes?limit=,
POST /api/review/digest {send, week}. Page web/review.html (sidebar "Review"). weekly_maintenance stage `review_digest`
sends the Saturday Telegram digest. Trade `exit_how`: stop (<= stop×1.002) / target (>= T1×0.998) / discretionary.

### Chart indicators (2026-09-06, TA roadmap Task 5)
`Charts.renderCandles(containerId, candles, overlays, opts)` — `opts = {indicators: bool, legendEl: id|Element,
chandelier: {since: 'YYYY-MM-DD', atrMult} | null}`. With `indicators`, draws SMA 20/50/200 line series (client-side
from the candles), colours volume bars by relative volume (>= 1.5x median bright, < 0.7x faint) and, when
`chandelier.since` is given, the Guardian's trail (highest close since entry − atrMult × ATR14, never lowered).
Legend chips toggle each layer; prefs in localStorage `egxde.chart.indicators.v1`. Pure helpers exposed as
`Charts.indicators.{sma, atr, rvol, chandelier}`; node test `tests/js/chart_indicators.test.js`.
`GET /api/portfolio/config` adds `guardian_atr_mult`. stock.html: legend host `#chart-legend`; chandelier uses the
first held position's `opened_at` (from /api/portfolio/guardian rows).

### Relative volume (2026-09-06, TA roadmap Task 4)
```python
pattern_common.rvol(candles, idx=None, lookback=20) -> float|None   # volume / MEDIAN(previous 20 volumes); None < 10 prior bars
pattern_common.rvol_bucket(v) -> 'lt1'|'1_1.5'|'ge1.5'|None; RVOL_BUCKETS, RVOL_LABELS
rules_backtest.Ind.rvol: list[float|None]                           # per bar
```
Stamped as `rvol` on: rule_scanner rows + scanner_hits payload, replay rule/pattern/checklist payloads, patterns.detect rows
(break-day bar, else last bar) + pattern_hits scanner_hits payload, checklist volume pillar (`rvol`, `up_share`, `week_ratio`)
and top-level `rvol`, setups rows (`rvol`, `market`), compare columns (`rvol`), candidates entries (`rvol`, from the rule
payload else `leaders.daily_candles`), `snapshots.rvol` (migration; `market.stamp_session_rvol(date)` post-close stage after
the rule scanner), `stocks.detail()["volume"]` = {rvol, bucket, volume, median_volume_20d, as_of}.
Scorecard: `by_rvol{bucket: {h: stats}}` per scanner, `rvol_multipliers{bucket: {scanner: bucket beat / overall beat,
clamped [0.7, 1.3]}}` (proxies inherit), `outcomes_with_rvol`; `signal_weights(regime, rvol_bucket)` multiplies;
`regrade(only_incomplete=True)` also selects hits whose payload lacks rvol and stamps it (`rvol_stamped`). Edge rows carry
`extra.by_rvol` at the reference horizon; `edge.latest()/compute()` add `volume{measured, volume_matters[], volume_indifferent[]}`.
Checklist volume pillar: pass on rvol >= 1.5 on an up day; fail on rvol >= 1.5 on a down day; quiet on rvol < 0.7.

### Pattern pruning (2026-09-06, TA roadmap Task 2)
```python
edge.pattern_edges(force=False) -> {key: {verdict, horizon, n, hit_rate, edge_metric, rate_vs_random_pp, excess_vs_random, horizons, by_regime}}
edge.invalidate_pattern_edges()                       # called by edge._persist
pattern_catalog.VIEWS = ('proven', 'not_negative', 'all'); DEFAULT_VIEW = 'proven'; UNMEASURED = 'unmeasured'
pattern_catalog.attach_edge(row, edges) -> row        # edge_verdict ('edge'|'marginal'|'negative'|'unmeasured'), edge_horizon, edge_n, edge_metric, edge_hit_rate, proven
pattern_catalog.passes_view(row, view) -> bool
pattern_catalog.enrich(row, edges=None)               # catalog meta (+ attach_edge when edges given)
patterns.detect(symbol, candles_in=None, view='all')  # filters before cluster_events / decisive_level
patterns.latest(universe, status, category, view='all')
```
checklist pillars 4 (price action) and 5 (patterns) skip rows with `edge_verdict == 'negative'`; pillar 5 text appends
"Ignored N shape(s) …" and carries `ignored_negative: [keys]`. Trend (pillar 1) keeps structure rows. Candidates never
merged pattern hits, so nothing changes there. UI default view is 'proven' (localStorage `egxde.patterns.view`) on the
stock page and Screener Patterns tab; the dashboard "Patterns on your stocks" column requests `view=not_negative`.

### app/services/regime.py — market regime (2026-09-06, TA roadmap Task 1)
```python
STATES = ('bull','neutral','bear'); BULL_BREADTH = 50; BEAR_BREADTH = 35; SLOPE_BARS = 10
def classify(close, sma50, sma50_prev, breadth_pct) -> state|None   # pure
def sentence(row) -> str
class RegimeSeries: .at(date, max_gap_days=10) -> state|None       # latest row on/before date
def series(force=False) -> RegimeSeries   # cached 10 min from regime_daily
def state_at(date) / current() -> {state, date, index_close, sma50, sma200, breadth_pct, text, stale, measured} / current_state()
def compute(range_='1y', universe='EGX100', persist=True) -> dict  # EGX30 benchmark_series + breadth (% members above SMA50)
def update_today() -> dict    # post_close stage (after rule_scanner, before candidates)
def backfill(range_='5y') -> dict   # inside scorecard.regrade
def history(limit=260) -> list[dict]
```
Consumers: `checklist.checklist(symbol, candles=None, regime_state=None)` → `market{state, text, raw_verdict, applied}`; a bear
regime turns SETUP into WATCH (never promotes). `screeners.candidates()`/`latest_candidates()` pass `regime.current_state()` to
`scorecard.signal_weights(regime)` and return `regime`. `replay.checklist_hits` passes the regime of each window's last session.
`rules_backtest.universe_run` pooled gains `by_regime{state: {trades, win_rate, avg_r}}`.
Routes: GET /api/market/regime?history=N, POST /api/market/regime/refresh, POST /api/edge/regrade {source?, only_incomplete}.
### app/services/scorecard.py additions
`PROXY_FOR = {squeeze: squeeze_breakout, momentum: momentum_3, volume_breakout: range_breakout}` — a live scanner with
< MIN_SAMPLE graded hits at 10d inherits its proxy's weight (`weight_basis` starts with 'proxy:'; `proxy` key set).
`invalidate_weights()`; outcomes carry `source`; `scorecard()` returns `sources` per scanner and `outcomes_by_source`.
2026-09-06: `HORIZONS = (5, 10, 20, 40, 60)`, `FINAL_HORIZON = 60` (a row is "fully graded" when ret_60 is set);
`grade_hit(hit, candles, bench, regimes=None)` stamps `regime`; `_upsert_many`; `regrade(source=None, only_incomplete=True,
range_='5y')` + `regrade_job`/`start_regrade`/`regrade_status` (background: regime.backfill then re-grade stored outcomes from
5y candles, no new detection); `baseline(horizon)`/`baselines()` read `random_entry_{h}d` rows incl. `by_regime`;
`scorecard()` adds `by_regime{state: {h: stats}}` per scanner (judged against the regime's own baseline), `regime_weights`,
`regime`, `horizons`, `baselines`, `outcomes_with_regime`; `signal_weights(regime=None)` overlays regime weights (MIN_SAMPLE in that regime).
`signal_direction(scanner)` (pattern_catalog direction; rules/scanners = bullish) — bearish outcomes are sign-flipped so
beat_rate/avg_excess read "in the signal's favour"; `baseline()` reads the stored random-entry yardstick (default 50%);
weight = 1 + 2 × (right-way rate − baseline rate), clamped [0.5, 1.5]; horizons carry `se_excess`, `beat_vs_random_pp`, `excess_vs_random`.

### app/services/compare.py — side-by-side comparison (2026-09-05)
```python
MAX_SYMBOLS = 4
def compare(symbols) -> dict   # {symbols, truncated, columns[{symbol, verdict, score, pillars, fails, fatal_fail, risk_plan,
                               #   extension_atr, rs{...}, signals[{name,weight,edge}], evidence_weight, strongest_signal, sector,
                               #   held_in_sector, heat_after_pct, held, sell, position, rank}], ranking, winner, headline, open_heat_pct, basis}
# rank key: (has fails, verdict rank, -rr, -evidence_weight, -excess_1m); Trend/Risk are fatal pillars
```
Route: GET /api/compare?symbols=A,B,C (routes_compare). Page: web/compare.html (sidebar "Compare"; Screener `Compare top 3`, Portfolio `Compare holdings`).

### app/services/rule_scanner.py — proven-rules scanner (2026-09-05)
```python
RULES = ('range_breakout','squeeze_breakout','momentum_3','pullback_trend')   # rules_backtest._SIGNALS on the LAST bar
def rule_hits_last_bar(symbol, candles) -> list[dict]      # pure
def scan(universe='ALL', persist=True, limit=None, rules=None) -> dict   # journals scanner_hits(source='live') under the rule name
def stored_hits(date=None) / latest() / start(universe) / status()
```
screeners.candidates() merges stored_hits(last_trading_day) into the live merge; _SCANNER_FAMILY maps the rules
(squeeze_breakout→coil, range_breakout/momentum_3→thrust, pullback_trend→pullback); post_close runs scan('ALL') before candidates.
checklist.checklist(symbol, candles=None); replay.checklist_hits(symbol, candles, step=5) journals checklist_{verdict} (replay);
setups._persist journals live checklist_{verdict}; latest_candidates excludes 'checklist_%'; edge kind 'checklist' + edge.checklist_summary().
Routes: GET /api/screener/rules, POST /api/screener/rules/scan {universe}, GET /api/screener/rules/status; POST /api/edge/replay accepts `checklist`.

### app/services/sell_checklist.py — holder's six pillars (Phase 3, 2026-09-05)
```python
PILLARS = ('thesis','weekly','relative_strength','distribution','bearish_events','exit_plan')  # pass = supports holding, fail = says exit
def sell_checklist(symbol, position=None, candles=None, mark=None) -> dict
#   {verdict: hold|reduce|exit, headline (cites prices), pillars[], decision_levels{exit_below, exit_reason,
#    bearish_trigger{level,label,status}, reduce_at, reduce_reason, trail_stop_to, trail_reason, ladder[]}, fresh_bearish[]}
def compact(sc) -> dict|None   # slice attached to each Guardian row as row['sell_checklist']
```
guardian.apply_sell_checklist(row, compact) adds BEARISH_EVENT (warning; fresh <= 3 sessions), a structure TIGHTEN_STOP
(suggested_stop = trail_stop_to when above the current stop), the exit-ladder reason on target hits, and row keys
exit_below / reduce_at / trail_stop_to / bearish_trigger (also in the Telegram text as a 'Levels:' line).

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
def open_position(symbol, qty, entry, stop, target1=None, target2=None, plan: dict|None=None, note="",
                  allow_override=False, raised_stop=False) -> dict
# 2026-09-06 (TA roadmap Task 3) — plan-quality gate at commitment:
def atr14(symbol) -> float|None                       # 14-day ATR from leaders.daily_candles (cached)
def plan_quality(entry, risk_stop, target1, target2, atr=None, min_rr=None, min_atr=None) -> dict
#   {rr_t1, rr_t2, t1_atr, risk, atr, faults[], ok, checked, min_rr_t1, min_target_atr}; nearest target must pay
#   >= settings.min_rr_t1 (MIN_RR_T1, 1.5) x initial risk AND sit >= settings.min_target_atr (MIN_TARGET_ATR, 1.0) ATR
#   above entry; open_position/update_position return {"error": "BLOCKED: the recorded plan does not pay…",
#   "requires_override": True, "plan_quality"} unless allow_override (then an "OVERRIDDEN plan-quality gate" warning);
#   results carry plan_quality. size_position(..., target1=None, target2=None) adds plan_quality + a note sentence.
# guardian.assess_position: a target inside MIN_TARGET_ATR x ATR14 of entry is a plan fault (PLAN_INVALID, never "hit").
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
| GET /api/stocks/{symbol}?timeframe= | stocks.detail — `timeframe=1W` runs the same analysis on weekly candles (the Score / Trade plan `1D | 1W` toggle) |
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
| POST /api/portfolio/positions | portfolio.open_position (stop/targets/note optional → filled from plan_defaults; allow_override bypasses the open-heat cap AND the plan-quality gate) |
| POST /api/portfolio/positions/{id}/update {stop?, target1?, target2?, note?, initial_stop?, allow_override?} | portfolio.update_position (new targets pass the plan-quality gate) |
| GET /api/portfolio/plan-quality?entry=&stop=&target1=&target2=&symbol= | portfolio.plan_quality preview (form hint) |
| POST /api/portfolio/size {…, target1?, target2?} | portfolio.size_position (+ plan_quality when a target is given) |
| GET /api/portfolio/config | + min_rr_t1, min_target_atr |
| GET /api/portfolio/plan-defaults/{symbol}?entry= | portfolio.plan_defaults (stop/targets/note from the stock's trade plan) |
| POST /api/portfolio/positions/{id}/close | portfolio.close_position |
| POST /api/portfolio/positions/{id}/update | portfolio.update_position (current stop / targets / note; targets must be > entry and T2 > T1; `initial_stop` may be set ONCE while NULL, must be < entry) |
| DELETE /api/portfolio/positions/{id} | portfolio.delete_position (erase a mistaken record; refused if partial sales exist) |
| POST /api/portfolio/positions/{id}/fill | portfolio.adjust_position (qty>0 buy → blended entry; qty<0 partial sell → realized PnL; whole qty → close) |
| GET /api/portfolio/fills?position_id=&limit= | portfolio.position_fills (fill journal) |
| GET /api/portfolio/performance | portfolio.performance |
| GET /api/backtest/rules | rules_backtest catalog (entry/exit rules, defaults) |
| POST /api/backtest/rules | rules_backtest.run (app's own entry+exit rules, plain-language verdict) |
| POST /api/backtest/rules/exits | rules_backtest.compare_exits |
| POST /api/backtest/rules/stops | rules_backtest.stop_sweep |
| POST /api/backtest/rules/universe | rules_backtest.universe_run |
| GET /api/backtest/rules/replay | rules_backtest.replay_positions (open positions under Guardian rules) |
| GET /api/screener/scorecard | scorecard.scorecard (per-scanner 5/10/20d track record + weights) |
| POST /api/screener/scorecard/grade | scorecard.grade (grade pending scanner_hits) |
| GET /api/screener/scorecard/outcomes?scanner=&symbol=&limit= | scorecard.outcomes |
| GET /api/edge | edge.latest (stored Proven-edge table) |
| POST /api/edge/refresh {universe, period} | edge.start (background compute) |
| GET /api/edge/status | {edge: edge.status(), replay: replay.status(), regrade: scorecard.regrade_status()} |
| POST /api/edge/regrade {source?, only_incomplete} | scorecard.start_regrade (background re-grade: 40/60d columns + regime stamp) |
| GET /api/market/regime?history=N | regime.current (+ history rows) |
| POST /api/market/regime/refresh | regime.update_today |
| POST /api/edge/replay {universe, period, patterns, limit} | replay.start (background historical replay) |
| GET /api/edge/replay/status | replay.status |
| POST /api/edge/replay/clear | replay.clear (delete replayed hits + outcomes) |
| GET /api/screener/setups?limit=&min_score= | setups.latest (stored six-pillar checklist across candidates/leaders/watchlist/holdings) |
| POST /api/screener/setups/refresh | setups.compute(persist=True) |
| GET /api/screener/leaders?universe=&limit= | leaders.latest (stored RS ranking) |
| GET /api/screener/patterns?universe=&status=&category=&view= | patterns.latest (stored pattern scan, 7 categories; rows re-stamped with `edge_verdict`/`edge_horizon`/`edge_n`/`edge_metric`/`proven`; `view` = proven \| not_negative \| all; adds `total`, `hidden`, `hidden_by_verdict`, `by_verdict`, `edge_measured`) |
| GET /api/screener/patterns/catalog | patterns.catalog (all ~75 patterns: category, direction, kind, tiers, EGX stats; each row `edge_verdict`/`proven`, `egx_stats.{verdict,horizon,n,edge_metric,verdict_by_horizon,excess_by_horizon,by_regime}`; top-level `by_verdict`, `proven[]`, `negative[]`, `edge_measured`) |
| POST /api/screener/patterns/refresh | patterns.compute(persist=True) |
| GET /api/stocks/{symbol}/patterns?view= | patterns.detect (one symbol, live; `view` = proven \| not_negative \| all filters by measured verdict BEFORE clustering; adds `view`, `total`, `hidden`, `hidden_by_verdict`, `by_verdict`, `edge_measured`). Rows carry `event_id`, `event_headline`, `also_seen_as`, `age_days`, `horizon`; `weekly_*` structure rows carry `timeframe: "1W"` and never cluster with daily rows; response adds `events` (one per clustered event, newest first), `distinct_events`, `events_by_direction`, `decisive_level` |
| (module) app.services.weekly | `resample(candles)` daily → Sunday–Thursday weekly OHLCV; `context(candles)` weekly trend (structure, 10/40-week averages, one sentence); `zones(candles)` tested weekly swing zones; `structure_rows(candles)` weekly HH/HL, LH/LL, BOS, CHoCH as `weekly_*` pattern rows. No I/O — callers pass daily candles |
| GET /api/stocks/{symbol}/levels | levels.compute (tested S/R zones, 52w, round numbers, SMAs). Adds `weekly_supports` / `weekly_resistances` (daily candles resampled to weeks, 2+ weekly touches) and flags `weekly` + `weekly_touches` on daily levels that sit on one; `key_levels` may include `timeframe: "1W"` zones |
| GET /api/stocks/{symbol}/sell-checklist | sell_checklist.sell_checklist (holder's six pillars + decision levels exit_below / reduce_at / trail_stop_to / ladder; uses the open position when held) |
| GET /api/stocks/{symbol}/checklist | checklist.checklist (six-pillar decision checklist). Trend pillar text ends with a `Weekly:` sentence and carries `weekly` {trend, structure, sma10, sma40, …}; weekly pattern rows are excluded from the Price-action pillar |
| POST /api/screener/leaders/refresh | leaders.compute(persist=True) |
| GET /api/portfolio/guardian | guardian.evaluate(persist=False, notify=False) |
| POST /api/portfolio/guardian/run | guardian.evaluate(persist=True, notify=body.notify) |
| GET /api/portfolio/guardian/history?position_id=&limit= | guardian.history |
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
