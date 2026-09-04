# EGX Decision Engine — Complete User Guide

**A plain-English manual for every page, every card, and every button.**

This guide assumes you love stocks but are not a programmer. Every feature is explained the same way:
**What it is** → **What you see** → **What the buttons do** → **How to benefit from it**.

> ⚠️ **Important:** This app is an *analysis assistant*, not a broker and not a fortune teller. It never
> places orders. It shows you evidence and does the arithmetic; **you** make the decision and place the
> trade with your real broker. Prices from TradingView and Yahoo are delayed roughly 15 minutes.

---

## What's new in this guide

- **Decision checklist** — six pillars (Trend, Support/resistance, Volume, Price action, Patterns, Risk plan) scored on every Stock page, with one verdict: SETUP, WATCH or NO SETUP.
- **Support & resistance** — tested price zones found from a year of daily candles, drawn on the chart and used to sanity-check every trade plan.
- **Chart patterns library and Patterns tab** — 79 chart, candlestick, price-action and weekly-structure patterns in 7 categories, forming or confirmed, with neckline, target, stop hint and quality score, grouped into events so one move is never counted twice; a full `Catalog` with the app's own EGX track record.
- **Best setups today** — the checklist run after every close across Candidates, Leaders, your watchlist and your holdings, on the Dashboard and the Screener's `Setups` tab.
- **Relative-strength Leaders** — the stocks actually beating EGX30 over one, three and six months, filtered for liquidity.
- **Signal Scorecard** — every scanner hit and confirmed pattern graded by what the stock did 5, 10 and 20 sessions later versus EGX30; the beat rate becomes the scanner's weight in Candidates.
- **Position Guardian** — one exit verdict per open position (EXIT STOP, TRAIL EXIT, TARGET HIT, STOP TOUCHED, THESIS BROKEN, TIGHTEN STOP, TIME STOP, HOLD), on the Dashboard, the Stock page and the Portfolio page, pushed to Telegram.
- **App-rules backtester** — the scanners' own entries with the Guardian's exits replayed on real history, with `Compare exits`, `Stop sweep`, `Run on universe` and `Replay my positions`.
- **Redesigned Portfolio** — fills recorded with `+` (buy more), `−` (sell part), `Stop` (move the stop), `Close` and `×` (remove a typo), net-of-fees performance, the plan-followed question and the 6% open-heat cap.
- **Today card on the Dashboard** — `Today — what needs a decision`: your positions' Guardian verdicts, the best setups, patterns on your stocks and the strongest names versus EGX30, in one place.

---

## Table of Contents

1. [Starting and stopping the app](#1-starting-and-stopping-the-app)
2. [The frame around every page](#2-the-frame-around-every-page)
3. [Page 1 — Dashboard](#3-page-1--dashboard)
4. [Page 2 — Stock page](#4-page-2--stock-page)
5. [Page 3 — Screener](#5-page-3--screener)
6. [Page 4 — Backtest](#6-page-4--backtest)
7. [Page 5 — Portfolio](#7-page-5--portfolio)
8. [Your daily routine (how to actually use this)](#8-your-daily-routine-how-to-actually-use-this)
9. [Glossary — every term explained](#9-glossary--every-term-explained)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Starting and stopping the app

The EGX Decision Engine runs entirely on your own computer. Nothing leaves your machine except the requests that fetch market data (TradingView and Yahoo prices, optional news, the optional AI brief, optional Telegram messages). There are no accounts, no logins, and the app **never places an order** — it is analysis tooling that shows you evidence and does the arithmetic; you make the decision and trade with your real broker.

### 1.1 Starting the app

**What it is** — A small local web server that you start once, then use through your normal browser.

**What you do** — Open PowerShell and run these two lines, pressing Enter after each:

```powershell
cd D:\MyApps\egx-decision-engine
.venv\Scripts\python.exe run.py
```

A few lines of start-up text appear, ending with the address the app is listening on. Leave that PowerShell window open — it *is* the app. If you close it, the app stops.

**What you may see**

| Message on start-up | Meaning |
|---|---|
| A line ending in `http://127.0.0.1:8642` | The app is running. Open that address in your browser. |
| A complaint that the port is refused or in use (Windows error 10013) | Windows has reserved that port number. Change `PORT` in your settings (see 1.4) to another free number and start again — whatever address is printed at start-up is the right one. |
| A warning that the analytics core is unavailable / the app is serving in a degraded mode | The analysis library that powers scanners and scores is missing or has moved (it lives in a synced folder that can be moved). The pages still load and the session pill still works, but every data card shows an error. Restart after the folder is back; if it persists, ask whoever set the app up. |

**How to benefit from it**
- Start the app before the session opens (EGX trades Sunday–Thursday, 10:00–14:30 Cairo time) so the background jobs actually run: the optional AI morning brief at 09:30, then alert checks and the Position Guardian every 10 minutes from 10:00 to 14:20, then the post-close run at 15:00. The app cannot watch your positions while it is not running.
- Leave it running in the evening after the close: the 15:00 run takes the daily snapshot of the EGX100 universe, re-ranks Candidates, checks alerts, runs the Guardian, grades the Signal Scorecard, rebuilds Leaders and Patterns, and recomputes the best Setups — all of which is what makes tomorrow morning's Dashboard useful. If the computer was asleep at 15:00, an hourly catch-up check (at seven minutes past each hour) notices the missing snapshot and runs it as soon as the app is back.
- On a Friday, Saturday or public holiday the background jobs deliberately do nothing, so do not expect a fresh snapshot on those days.
- If the browser shows `API offline` in the top bar, the first thing to check is whether the PowerShell window is still open and still shows the app running.

### 1.2 Opening the app in the browser

**What it is** — The address you type into Chrome, Edge or any browser.

**What you see** — Go to **http://127.0.0.1:8642**. The Dashboard opens. From there the sidebar reaches the other pages: Stock page, Screener, Backtest, Portfolio.

**How to benefit from it**
- Bookmark the address. You can also bookmark a specific Stock page (its browser address ends with the ticker) so your core names are one click away.
- Only your own computer can reach this address. It does not work from your phone unless you deliberately change the `HOST` setting — and the guide does not recommend that.

### 1.3 Stopping the app

**What you do** — Click into the PowerShell window and press `Ctrl+C`, or simply close the window. The app stops its background jobs and closes your database cleanly before exiting.

**How to benefit from it**
- Stopping the app does not lose anything: watchlist, positions, alert rules, snapshots and fired alerts are all saved on disk the moment you create them (see 1.5).
- Remember that a stopped app cannot send Telegram alerts or run the Guardian. If you rely on those, keep it running on trading days.

### 1.4 Settings you may want to change (the `.env` file)

**What it is** — A small text file called `.env` in the app folder (`D:\MyApps\egx-decision-engine`). Every setting is optional; the app runs fine with all the defaults. If the file does not exist yet, copy `.env.example` to `.env` and edit it in Notepad. Each line is `NAME=value`; a line starting with `#` is switched off.

**Settings are read once, when the app starts.** After you change anything here, stop the app and start it again (1.3 then 1.1).

**What you see** — every setting, what it does, and its default:

| Setting | Plain-English effect | Default |
|---|---|---|
| `HOST` | Which network address the app listens on. Leave it alone. | `127.0.0.1` (this computer only) |
| `PORT` | The port number in the browser address. Change it only if Windows refuses the default. | `8642` |
| `DB_PATH` | Where your data file lives (see 1.5). Leave it alone unless you want the database somewhere else. | the `data\egx.db` file inside the app folder |
| `ANTHROPIC_API_KEY` | An AI key for the Morning brief, the stock Thesis and the bull/bear Debate. Leave it off and the rest of the app works; those three buttons will report that the key is not configured. | off |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | The bot token (from Telegram's BotFather) and your chat id. With both set, fired alerts and Guardian verdicts are pushed to your phone. Without them, alerts stay in-app only. | off |
| `SCHEDULER_ENABLED` | `1` runs the background jobs (intraday alert checks and Guardian, the 15:00 post-close run, the 09:30 morning brief, Saturday maintenance and backup, the hourly catch-up). `0` turns them all off — you then have to press the buttons yourself. | `1` |
| `ACCOUNT_SIZE` | Your trading capital in EGP. The Position size calculator and the "New position" form use it to turn a risk percentage into a number of shares. | `100000` |
| `RISK_PCT` | The default percentage of `ACCOUNT_SIZE` you are willing to lose on one trade if the stop is hit. | `1.0` |
| `FEE_PCT_PER_SIDE` | Your all-in trading cost per side, as a percentage: brokerage + stamp duty + exchange/FRA/MCDR fees + risk insurance. It is charged on the buy *and* on the sell, and every portfolio profit, win-rate and R figure is shown net of it. | `0.25` |
| `RISK_FREE_RATE_PCT` | The yearly EGP risk-free rate (T-bill yield) used when the Backtest page works out a Sharpe ratio. Update it when T-bill yields move. | `25.0` |
| `PRICE_BAND_PCT` | The daily price limit the app assumes when it sanity-checks a trade plan's stop and targets (EGX main market is ±20%; some boards are tighter). | `20` |
| `MIN_DAILY_VALUE_EGP` | The liquidity floor. Candidates whose typical daily traded value (20-day median) is known to be below this are filtered out as illiquid; positions that would be more than about 15% of it get a warning. | `5000000` (5 million EGP) |
| `MARKETAUX_API_TOKEN` | A key for the News & sentiment tab on the Stock page. Without it that tab says it is not configured; everything else works. | off |
| `GUARDIAN_ATR_MULT` | How loose the Guardian's trailing stop is. The trailing stop sits this many ATR(14) below the highest close since you entered. Bigger = more room, smaller = tighter. | `2.5` |
| `GUARDIAN_SCORE_DROP` | How many points the stock's composite score must fall since your entry before the Guardian calls the thesis "broken". | `15` |
| `GUARDIAN_TIME_STOP_BARS` | How many sessions a position may sit inside ±0.5R (going nowhere) before the Guardian advises a time stop. | `15` |

**How to benefit from it**
- The two settings worth getting right on day one are `ACCOUNT_SIZE` and `FEE_PCT_PER_SIDE`. If `ACCOUNT_SIZE` is wrong, every suggested share count is wrong. If the fee is wrong, your recorded win rate and R figures flatter or punish you unfairly — ask your broker for your true all-in cost per side and enter that.
- Keep `RISK_PCT` at 1.0 (or lower) until you have a track record in the Portfolio page. Raising it is the fastest way to turn a normal losing streak into a damaged account.
- Set up Telegram if you cannot watch the screen during the session. An alert that fires into an app you are not looking at protects nothing.
- Do not loosen the Guardian settings because it told you to sell something you liked. Change them only after the App-rules backtest shows a different value works better across many trades.
- Leave `SCHEDULER_ENABLED=1`. Turning it off means no snapshots, so the score-change alerts, the Scorecard, the Leaders table, the Patterns scan and the Setups list stop updating, and no Saturday backup is made.

### 1.5 Where your data lives

**What it is** — One file, `data\egx.db` inside the app folder (unless you moved it with `DB_PATH`). It holds your watchlist, open and closed positions and their fills, alert rules, fired alerts, the daily snapshots, stored scanner hits and their Scorecard grades, Leaders rankings, pattern hits, Setups results, Guardian verdicts, backtest runs, morning briefs and a log of background jobs.

**What you see** — Nothing on screen; this is background housekeeping. Every Saturday at 12:00 Cairo the weekly maintenance job writes a dated backup copy into a `backup` folder next to the data file and keeps the 7 most recent copies.

**How to benefit from it**
- This file *is* your trading record. The Saturday backup only helps if the app is running on Saturday at noon, so also copy the file to a backup location of your own now and then (with the app stopped) — losing it means losing your position history, your Scorecard statistics and your alert rules.
- If you ever want a clean start, stop the app, rename the file, and start again: a fresh empty one is created automatically. Your old history stays in the renamed copy.
- Do not edit or move the file while the app is running; stop it first (1.3).

### 1.6 After an update: reload the browser properly

**What it is** — When the app's pages are updated, your browser may keep showing an old copy of the page while the server behind it is already new. Symptoms: a card that never fills, a button that does nothing, a panel described in this guide that you cannot find.

**What you do** — Press `Ctrl+F5` (or `Ctrl+Shift+R`) on the page to force a full reload. The server tells browsers to always re-check pages, so this is usually only needed once. The symbol search list is also remembered for the life of the browser tab; opening a new tab picks up any new tickers.

**How to benefit from it**
- Make a hard reload your first fix whenever something looks broken *only in the browser* but the PowerShell window shows no errors. It costs two seconds and rules out the most common cause before you start doubting your data.
- If the top bar says `API offline` after a hard reload, the problem is the server, not the browser — go back to 1.1 and restart the app.
- Do it once after every update, on each of the five pages, *before* the market opens. Discovering a stale `Position Guardian` panel at 13:50 with an `EXIT STOP` pending is the wrong moment to learn about browser caching.
- If the search box does not suggest a ticker that was newly added to the app, open a fresh browser tab: the suggestion list is remembered per tab, and a new tab fetches the current list.
- Never assume a card that "never fills" means the market data is gone. Reload first; only then read the red message in the card (2.10) and the troubleshooting table (10).

---

## 2. The frame around every page

Every one of the five pages (Dashboard, Stock page, Screener, Backtest, Portfolio) is wrapped in the same frame: a dark sidebar on the left, a top bar with a live session indicator and a search box, and a footer. Learn it once and you know your way around all five pages.

### 2.1 Panel — sidebar brand and navigation (`EGX//DE` · `Decision Engine`)

**What it is** — The left-hand column. At its top is the app's name badge and the four page links.

**What you see**

| Item | What it shows |
|---|---|
| `EGX//DE` with `Decision Engine` underneath | The app's name badge. It is a label, not a link. |
| `▦ Dashboard` | Link to the market overview page. |
| `⌗ Screener` | Link to the stock-hunting page (scanners, Candidates, Setups, Leaders, Patterns, Scorecard). |
| `↻ Backtest` | Link to the strategy-testing page (App rules and indicator strategies). |
| `☷ Portfolio` | Link to your positions, the Position Guardian and your alert rules. |

The link for the page you are on is highlighted so you always know where you are. The Stock page has no sidebar link of its own — you reach it through the search box, the watchlist, or by clicking any ticker anywhere in the app.

If, on the Screener, Backtest or Portfolio page, the sidebar ever appears as a plain list headed `EGX Engine` instead of the styled badge, the page's helper scripts failed to load; do a hard reload (1.6).

**What the buttons do** — Each link opens that page. Nothing here needs confirmation and nothing changes your data.

**How to benefit from it**
- Think of the four links as a daily loop: Dashboard (what is happening) → Screener (what is worth a look) → Stock page (is this one a trade, and how big) → Portfolio (what I hold and what the Guardian says about it). Backtest is the weekend page, for testing whether a rule deserves your money before you risk it.
- The sidebar is hidden on narrow windows; the mobile strip (2.7) takes over. If you cannot see the links, widen the window or use the strip.

### 2.2 Panel — `Watchlist`

**What it is** — Your personal shortlist of starred stocks, shown under the navigation on every page with a latest price beside each ticker.

**What you see**

| Element | Meaning |
|---|---|
| `Watchlist` | Section heading. |
| Ticker, e.g. `COMI` | A stock you starred. The most recently added is at the top. At most 15 are shown here (older entries beyond 15 are still saved). |
| Number to the right | The latest available price for that stock. If no price could be fetched, the space stays blank. |
| `Empty — star a stock.` | You have not starred anything yet. |
| `Watchlist unavailable.` | The app could not read its own database — almost always because the server stopped. Check the PowerShell window. |
| A small spinning circle | Loading — the list is being fetched. |

**What the buttons do**
- **Click a ticker** → opens that stock's Stock page.
- **Adding and removing** happens on the Stock page, not here: at the top of every Stock page there is a star button (hover text `Toggle watchlist` until the page knows whether the stock is starred). `☆` (hover text `Add to watchlist`) adds the stock; it turns into a filled `★` (hover text `Remove from watchlist`), the sidebar list refreshes at once, and a green message pops up: `COMI added to watchlist.` Clicking `★` removes it with `COMI removed from watchlist.` If saving fails you see a red `Watchlist: …` message with the reason.

**How to benefit from it**
- Keep the list short — 5 to 15 names you genuinely follow. It is a shortlist, not an archive. The Dashboard's "Patterns on your stocks" column and the Guardian both read from your watchlist and positions, so a bloated list buries the signals that matter.
- Star a stock when the Screener or Candidates list surfaces it and you want to watch it for a setup, not when you have already bought it (positions have their own place in the Portfolio). Un-star it once the setup has either triggered or failed.
- The price beside each name refreshes each time a page loads, so a glance at the sidebar while you work on another page tells you whether a watched name is moving toward your planned entry.
- Use it in the evening: open each starred stock, run through the Decision checklist and note which ones are `SETUP` versus `WATCH`. Tomorrow's decisions should be limited to that list.
- Common mistake: starring twenty names on a busy day and never removing them. Every Sunday, prune anything you would not buy this week.

### 2.3 Control — page title (top bar, left)

**What it is** — The first item in the top bar names the page you are on: `Dashboard`, `Screener`, `Backtest`, `Portfolio`, or on a Stock page the ticker followed by the word Stock, for example `COMI — Stock` (just `Stock` if no ticker was given).

**What you see** — Text only. On wide screens the whole top bar stays pinned at the top while you scroll; on narrow screens it scrolls away and the mobile strip (2.7) stays pinned instead.

**How to benefit from it**
- Glance here before acting on a number, especially when you have several browser tabs open on different stocks. Confusing two Stock pages is an easy way to size a trade on the wrong price or record a fill against the wrong ticker.
- Read the ticker in the title against the symbol on your broker's order screen *before* you press buy — the app never places orders, so this cross-check is your only safeguard against mixing up two names that look alike.
- If the title reads just `Stock` with no ticker, the page was opened without a symbol; nothing on it belongs to any company. Go back to the search box (2.6) or the Watchlist (2.2) and open the stock properly.
- On a narrow window the title scrolls away; use the highlighted item in the mobile strip (2.7) to confirm which page you are on before acting.

### 2.4 Control — session pill (`Market open` / `Market closed` / `API offline`)

**What it is** — A small rounded badge with a coloured dot that tells you whether the Egyptian Exchange is trading right now, and whether the app's own server is reachable.

**What you see**

| Pill text | Colour | Meaning |
|---|---|---|
| `checking…` | grey | Shown for a moment while the page asks the server. |
| `Market open` | green, glowing dot | It is a trading day in Cairo and the time is between 10:00 and 14:30. Prices update (about 15 minutes late) while you work. |
| `Market closed` | red | Outside session hours, a Friday/Saturday, or a public holiday. **Hover the mouse over the pill** to see `Next open: …` followed by the date and time of the next session in computer form, for example `Next open: 2026-09-06T10:00:00+03:00` (year-month-day, then the time in Cairo). |
| `API offline` | red | The browser could not reach the app's server at all. The page you see is stale and every card will fail. Go to section 1.1. |

The pill text is displayed in small capitals (`MARKET OPEN`, `MARKET CLOSED`). The calendar knows EGX weekends (Friday and Saturday) and the 2026 public holidays; dates of the Islamic holidays (Eid al-Fitr, Eid al-Adha, Islamic New Year, the Prophet's Birthday) are approximate because they depend on the moon sighting, so around those dates double-check with your broker.

**What the buttons do** — Not clickable; hover for the next-open tooltip when closed.

**How to benefit from it**
- `Market open` is when the intraday tools mean something: alert rules are checked and the Position Guardian runs every 10 minutes from 10:00 to 14:20 (and once more in the 15:00 post-close run), and the Candidates `Rescan` sees live moves. This is the time to act on a plan, not to build one.
- `Market closed` is the planning state. Everything you see is the last session's close (the daily snapshot is taken after 15:00 Cairo). Use it to run the Screener, read the Decision checklist on your starred names, set your stops and alert rules, and size tomorrow's trades. Do not expect any number to move, and do not mistake a stale quote for a price you can get at the open.
- The `Next open:` tooltip saves you from placing a morning order on a holiday you forgot. Check it on Thursday evenings and before Eid.
- `API offline` means nothing on the page can be trusted — not even the watchlist prices. Fix the server first, then hard-reload.
- Remember the delay: even when the pill is green, the price you see is roughly 15 minutes old. Never treat a level on screen as "just hit"; confirm with your broker's live quote before you enter or exit.

### 2.5 Control — data-age chip (`data as of HH:MM`)

**What it is** — A second small pill beside the session pill that says when this browser page last received fresh data from the app, so you know how old every number on screen is.

**What you see**

| Chip text | Colour | Meaning |
|---|---|---|
| `no data yet` | grey | The page has not yet received anything from the server (still loading, or everything failed). |
| `data as of 11:42 (~15m delayed feed)` | green | The page last received data at 11:42 on your clock. The feed behind it is itself about 15 minutes late (or end-of-day when closed). |
| `data as of 11:42 (~15m delayed feed) · 25m old — reload` | red | The page's numbers are 20 minutes old or more. Reload the page to refresh them. |

Hover over the chip for the explanation: `When this page last received data from the API. Feed itself is delayed ~15 min (or end-of-day).` Like the session pill, the text is displayed in small capitals. The chip re-checks itself shortly after the page loads and then every 30 seconds, but note that the pages themselves **only fetch new data when you load or reload them or press one of their own buttons** — they do not update on their own.

**What the buttons do** — Not clickable; press F5 (or the page's own refresh buttons) to get new data.

**How to benefit from it**
- Before you act on any price, stop or target you read on screen, add the chip's age to the 15-minute feed delay. A green chip during the session still means a price that is a quarter of an hour old; a red chip means you are looking at the past.
- During the session, make reloading a habit each time you come back to the screen — the chip turning red is your cue.
- If the chip stays at `no data yet` while cards show errors, the server or the data providers are the problem (see 2.10), not your reading of the page.

### 2.6 Control — search box (`Search symbol or company…`)

**What it is** — The box at the right of the top bar, marked with a `⌕` magnifier. It finds any EGX-listed stock by ticker **or by company name** and opens its Stock page.

**What you see**

| Element | Meaning |
|---|---|
| Placeholder `Search symbol or company…` | Type here. |
| Dropdown list (up to 10 rows) | Appears as soon as you type. Each row shows the **ticker** in bold, the **company name**, and — if the stock belongs to an index — a small badge: `EGX30`, `EGX70`, `SHARIAH33`, `EGX35LV` or `TAMAYUZ` (a stock in several indices shows only the first of those that applies, in that order). Hovering a row highlights it and shows its sector as a tooltip. |
| `No matching symbol` | Nothing in the catalogue matched what you typed. Check the spelling, or type the ticker exactly. |

The catalogue holds 305 EGX tickers, 293 of them with a company name (those are the ones you can find by name). Matches are ranked: an exact ticker first, then tickers that begin with your text, then company names that begin with it, then names that contain it, then tickers that contain it. Ties are broken by index membership (EGX30 first, then EGX70, and so on) and then by company size, so the most tradable names appear at the top. Typing `EGX:` in front of a ticker is fine — it is ignored. The catalogue is downloaded once per browser tab and remembered, so suggestions appear instantly on every later page.

**What the buttons do**
- **Typing** → filters the dropdown instantly. Clearing the box closes it.
- **Click a suggestion** → opens that stock's page.
- **↓ / ↑** → move the highlight down and up through the suggestions (↓ also opens the list if it is closed; ↑ only works while the list is open). The list wraps around at both ends.
- **Enter** → opens the highlighted suggestion; if nothing is highlighted, opens exactly the ticker you typed (so `COMI` + Enter always works even before the list has loaded). Typing a company name (not a ticker) and pressing Enter with nothing highlighted opens a Stock page for that text, and its cards will fail to load because no such ticker exists — pick from the list instead.
- **Esc** → closes the dropdown and leaves the box.
- Clicking elsewhere closes the dropdown.

**How to benefit from it**
- You do not need to memorise ticker codes. Type `bank`, `cement`, `juhayna` or `telecom` and choose from the list — the badges tell you at a glance whether it is an EGX30 blue chip or a smaller EGX70 name, which matters for liquidity and for how much of your account it can safely absorb.
- Use it as a quick liquidity filter: a name with **no** index badge is often thinly traded. Before buying such a stock, check the liquidity warning on the Stock page and keep your size small; the app's own `MIN_DAILY_VALUE_EGP` floor (1.4) exists for exactly this reason.
- When the Screener or Dashboard shows a ticker you do not recognise, type it here: the company name and sector in the dropdown tell you what the business is before you spend time on the chart.
- Fastest workflow during the session: click the search box, type the ticker, press Enter. Three actions from any page to the Stock page.
- Common mistake: typing a company's English marketing name that differs from its registered name. If the list shows `No matching symbol`, try a shorter part of the name (for example just `misr` or `egypt`) and scan the results.

### 2.7 Panel — mobile navigation strip (narrow windows only)

**What it is** — On windows narrower than about 860 pixels — a phone, or a half-width laptop window — the sidebar is hidden and a horizontal strip of the same four links appears under the top bar instead, pinned to the top of the screen while you scroll.

**What you see** — `▦ Dashboard`, `⌗ Screener`, `↻ Backtest`, `☷ Portfolio` in a row that you can swipe or scroll sideways; the current page is highlighted. The top bar may wrap onto two lines at this width and the search box becomes narrower.

**What the buttons do** — Same as the sidebar links (2.1).

**How to benefit from it**
- The watchlist lives in the hidden sidebar, so on a narrow screen use the search box to reach your stocks — or widen the window to get the sidebar and watchlist back.
- Wide tables (Screener results, backtest trade logs, positions) scroll sideways inside their own card on narrow screens; the page itself never scrolls sideways. If a column seems missing, drag the table left.

### 2.8 Panel — footer

**What it is** — The last line of every page.

**What you see** — `Analysis tooling — not financial advice. Data delayed ~15 min.` On the Dashboard and Stock page a second, dimmer label reads `EGX Decision Engine · local`, reminding you the app is running on your own machine.

**What the buttons do** — Nothing; it is text.

**How to benefit from it**
- It is there on purpose. Treat every verdict, score and plan in this app as evidence to weigh, never as an instruction. The app never sees your broker account, never knows your real fill, and shows prices a quarter of an hour late; the trade — and the responsibility — are yours.
- "Delayed ~15 min" has a concrete consequence: a `price above` alert (7.6) or an `EXIT STOP` verdict (7.2) describes where the stock *was*, not where it is. Always confirm the live quote at your broker before you send an order, and expect a stop hit at 47.50 in the app to fill lower at the broker in a fast market.
- Outside 10:00–14:30 Cairo the "delayed" price is the last session's close. A red `EXIT STOP` read at 20:00 is tomorrow's opening order, not a price you can still trade at.
- "Not financial advice" is also a sizing rule: nothing on these pages justifies risking more than the 1% per trade and 6% open heat the app defaults to. If a card ever makes you want to bet bigger, that is the moment to reread this line.
- The footer is the same on every page, so use it as a stopping point: when you scroll down to it, you have seen everything the page has — there is no hidden card below.

### 2.9 Control — pop-up messages (toasts)

**What it is** — Small messages that slide in at the bottom-right corner of the screen when you do something (star a stock, open a position, run a scanner, generate a brief) and disappear by themselves after about four seconds. You never need to dismiss them. Several can stack if you click quickly.

**What you see**

| Left-hand stripe | Meaning | Examples of exact text |
|---|---|---|
| green | Success — the action worked. | `COMI added to watchlist.` · `Morning brief generated.` · `Thesis generated.` · `Scanner "…" returned 12 rows` · `Backtest finished: COMI / …` · `Guardian ran — 1 position(s) need a decision` · `Alert rule created: …` · `Rule deleted` · `Position closed at …` |
| red | Error — the action failed, with the reason. | `Watchlist: …` · `Brief failed: …` · `Scanner failed: …` · `Enter a symbol first` · `Quantity must be a positive number` · `Stop must be a positive price` · `You only hold … shares` |
| teal (the app's accent colour) | Information — nothing failed, but something happened that you should know. | `Auto-filled from trade plan: …` · `Position not opened (open-heat cap).` |
| amber | Warning. | The style exists but no page currently uses it. |

**What the buttons do** — Toasts have no buttons; they fade out on their own.

**How to benefit from it**
- Read the red ones. They usually say precisely what to fix (a missing symbol, a quantity that is not a number, a provider that is rate-limiting). Repeating the click without reading it wastes the minute the provider asked you to wait.
- A green toast after opening a position or creating an alert rule is your confirmation that the record was saved to your data file. If you did not see one, check the Portfolio page before assuming it went through.
- A teal `Position not opened (open-heat cap).` is not a bug: the app warned that your open positions already carry too much risk, offered an override, and you (rightly) declined. Read the Portfolio page before trying again.
- Toasts are not alerts. Price and Guardian alerts appear in the Portfolio page's `Fired alerts` list and, if configured, on Telegram — not as toasts.

### 2.10 Control — loading and error messages that appear inside cards

**What it is** — Every card fetches its own data. While it waits it shows shimmering grey placeholder bars or a `Loading…` line (sometimes more specific, such as `Loading fired alerts…`); if the fetch fails, the card shows a red-bordered box with a plain-English explanation instead of a blank space. Hover over the message to read the raw technical error if you ever need to report it. The wording differs slightly between the Dashboard and Stock page on one hand and the Screener, Backtest and Portfolio pages on the other.

**What you see**

| Message | What it means | What to do |
|---|---|---|
| Grey shimmering bars or `Loading…` | Fetching. Scans that cover the whole market can take up to a minute. | Wait. |
| `No rows` (Screener, Backtest, Portfolio tables) or `No rows returned.` (Dashboard) | The request worked but returned nothing (an empty result, not a failure). | Change the filter or the universe. |
| `TradingView is pausing this app for a minute or two (rate limit). The chart, your position and patterns still work from Yahoo data. Reload in a minute for the score and trade plan.` (Dashboard, Stock page) · `TradingView is pausing this app for a minute or two (rate limit). Try again shortly — stored results and Yahoo-based tabs (Leaders, Patterns) still work.` (other pages) | The scanner provider has temporarily throttled the app after heavy use. | Wait one to two minutes and reload. The Leaders and Patterns tabs, the chart and your position card keep working meanwhile. |
| `Yahoo is rate-limiting requests for a short while. Cached data is shown where available; try again in a minute.` (Dashboard, Stock page) · `Yahoo is rate-limiting requests for a short while. Try again in a minute.` (other pages) | The price-history provider is throttling. | Wait a minute and try again. |
| `The app's server is not responding. Is it running? (see the guide, section 1)` (Dashboard, Stock page) · `The app's server is not responding. Is it running?` (other pages) | The browser cannot reach the app at all. | Check the PowerShell window; restart with 1.1. |
| Any other sentence, sometimes prefixed with the card's name (for example `Candidates: …`) | A specific problem reported by that card (for example no price history for a micro-cap, or an AI key that is not configured). | Read it; the rest of the page usually still works. |

**How to benefit from it**
- Rate-limit messages are the most common thing you will see, and they are harmless — they recover on their own. Do not hammer `Rescan` or the scanner buttons while one is showing; that prolongs the pause.
- A card in error is not a card saying "no trade". Never read a failed score or plan as a verdict; reload and get the real number before deciding.
- If every card on every page fails at once, the cause is almost always the server (2.4 will say `API offline`) or a provider outage, not the stocks.

---

## 3. Page 1 — Dashboard

**This is your "what is the market doing, and what do I have to decide today?" page.** It is the first page you see at http://127.0.0.1:8642 and the one to open first every trading day. Everything on it loads by itself — you press nothing to make it work. Only two buttons exist on the whole page: **`Rescan`** on the Candidates card and **`Generate`** on the Morning brief card.

The page is built top to bottom in the order you should read it: a breadth row (is the market healthy?), the decision card (what needs my attention?), the world (is anything outside Egypt about to spoil the day?), the movers (where is the money going?), sectors and candidates (where should I hunt?), and finally the written brief that ties it all together.

Remember the footer that appears on every page: *"Analysis tooling — not financial advice. Data delayed ~15 min."* Every number here is evidence to weigh, not an instruction. The app never places an order.

---

### 3.1 Stat tiles — `Advancers`, `Decliners`, `Unchanged`, `% Advancing`, `Session (Cairo)`

**What it is** — Five small tiles across the top of the page. The first four measure **market breadth**: how many EGX stocks went up, down, or nowhere in the current (or last) session. The fifth tells you whether the Egyptian Exchange is open right now.

**What you see**

| Tile | Colour | What the number means |
|---|---|---|
| **Advancers** | Green | How many EGX stocks are up today |
| **Decliners** | Red | How many are down today |
| **Unchanged** | Grey | How many closed exactly where they started |
| **% Advancing** | Neutral | Advancers as a share of all three groups together, to one decimal (e.g. `61.3%`) |
| **Session (Cairo)** | `OPEN` in green or `CLOSED` in red | Under it, a small line: when open, the current Cairo time (e.g. `12:40 Cairo`); when closed, `next: 2026-09-06 10:00` — the date and time of the next opening bell |

Before the data arrives every tile shows `—`. If the market overview could not be fetched, the small line under the session tile reads `overview unavailable` and the tiles stay at `—`.

**What the buttons do** — There are no buttons. The tiles refresh every time you reload the page (the market data behind them is refreshed at most once a minute, so reloading more often than that shows the same numbers).

**How to benefit from it**

- **Read `% Advancing` before you read anything else.** Most Egyptian stocks move with the index. When most of the market is advancing, your breakout candidates have the wind behind them; when most of it is declining, even a perfect-looking chart is swimming against the tide. On a broad-selling day the sensible response is to trade smaller, wait for the close, or do nothing.
- **Compare the tile with the index.** The Dashboard does not show the EGX30 level itself, so glance at it on your broker screen: if the index is up but far fewer than half the stocks are advancing, a handful of large names is carrying the rally — that is a fragile market, not a strong one. Breadth tells you what the headline number hides.
- **Use the session tile to know what kind of prices you are looking at.** EGX trades Sunday to Thursday, 10:00–14:30 Cairo time; Friday and Saturday are the weekend. When the tile says `CLOSED`, every price on the page is from the last session — fine for planning tomorrow's trades, useless for "what is happening right now". When it says `OPEN`, remember prices are still delayed roughly 15 minutes.
- **Common mistake:** treating the Advancers count on its own as bullish. 120 advancers is great out of 200 stocks and mediocre out of 380. That is why `% Advancing` is the tile that matters.

---

### 3.2 Card — `Today — what needs a decision`

**What it is** — The decision card. Four columns pull, from every other part of the app, the things that might actually require you to act today, so you do not have to open five pages to find them. On the right of the title a small grey stamp reads `guardian 12:40` — the time the Position Guardian evaluated your holdings for this view (it appears only once you have at least one open position recorded).

Each column header has a small grey link (`all →`, `portfolio →`, `all patterns →`, `leaders →`) that takes you to the full version on the Screener or Portfolio page. Every symbol in every column is a link to that stock's Stock page. Hovering a row in the first three columns shows a one-line explanation (the checklist headline, the Guardian's first reason, or the pattern scanner's note).

**How to benefit from it (the card as a whole)**

- Read the four columns in order: *positions first* (protect what you have), then *setups* (what could I buy), then *patterns on my stocks* (is anything I own or watch drawing a signal), then *leaders* (is my shopping list made of strong names or weak ones).
- Nothing in this card is a buy or sell order. It is a to-do list of things to **look at**. The stock page, the trade plan and your own judgement still come between this card and your broker.
- If all four columns say "nothing" — no setups, nothing urgent, no patterns, and your names are not in the leaders — that is a valid, useful answer: a day to stay in cash and let the app keep working.

#### 3.2.1 Column — `Best setups`

**What it is** — The stocks that currently pass the app's **six-pillar decision checklist** (trend, support/resistance, volume, price action, patterns, risk plan). After every close the checklist is run across every stock the app already has a reason to look at — the latest Candidates, the Leaders ranking, your watchlist and your open positions — and the results are stored so this column opens instantly. The link `all →` opens the Setups tab of the Screener.

**What you see**

Up to six **SETUP** rows. If fewer than three stocks qualify as setups, up to four **WATCH** rows are added underneath so the column is never a blank wall. Each row shows:

| Element | Meaning |
|---|---|
| **Symbol** | Click to open the Stock page. Hover the row to read the checklist headline (e.g. *"Setup: 5 of 6 pillars in favour, only volume unclear."*) |
| **Score badge** `5/6` | How many of the six pillars pass. Green badge = SETUP verdict, amber badge = WATCH verdict |
| **Six pillar chips** | In fixed order — Trend, S/R, Vol, PA, Pat, Risk — each a small chip: `✓` pass (green), `⚠` unclear (amber), `✗` against (red). Hover a chip for its name and status, e.g. *"Vol: warn"* |
| **Grey note** | `all six` when every pillar passes, otherwise `needs volume, patterns` — the first two pillars that are not yet a pass, i.e. what you are waiting for |

Under the list a grey summary line: `3 setups · 7 watch · 21 no setup · checklist of 2026-09-02` — the counts across the whole stored run and the date it was built.

**How the verdict is decided** (this is exactly what the app does):

| Verdict | Rule |
|---|---|
| **SETUP** (green) | 5 or 6 pillars pass and **none** is against it |
| **WATCH** (amber) | 3 or 4 pass with none against; or 3 or more pass with exactly one pillar against (as long as that one is not Trend or Risk plan) |
| **NO SETUP** (not shown here) | Trend or Risk plan is against it, or two or more pillars are against it, or fewer than 3 pass |

**What each chip is judging**

| Chip | `✓` pass when | `✗` against when |
|---|---|---|
| **Trend** | Price is above the 50-day average and the 20-day average is above the 50-day (if the recent swings are still making lower highs and lower lows, or the weekly trend is down, it drops to `⚠`) | Price and the 20-day are both below the 50-day — a downtrend |
| **S/R** | Price is sitting at a tested support, or is breaking out above resistance, or is mid-range with at least twice as much room up as down (and at least 5% up) | Price is at a tested resistance |
| **Vol** | At least 55% of the last 20 sessions' volume traded on up days and this week runs at or above the 20-day average | 40% or less of the volume on up days while activity is at least 1.1× normal — heavy selling. (Quiet weeks under 0.7× average are only `⚠`) |
| **PA** (price action) | Bullish events outnumber bearish ones on the last sessions | A bull trap, false breakout, change of character, failed retest or upthrust, or bearish events outnumber bullish |
| **Pat** (chart patterns) | A confirmed bullish chart shape | A confirmed bearish shape and no bullish one. Forming shapes are `⚠` |
| **Risk** | A stop just under the nearest support gives at least 2R to the nearest resistance, the stop is 10% away or less, and the stock is liquid | Less than 1R of room, or the stock is illiquid — its typical daily traded value is below 5,000,000 EGP by default. Under 2R, or a stop more than 10% away, is `⚠` |

The risk pillar also builds a levels-based plan (entry at the price, stop under support, first target at resistance) and works out how many shares that plan allows at your risk percent (1% of a 100,000 EGP account by default — both configurable). You see the full plan on the Stock page.

**What the buttons do** — No buttons in this column. `all →` opens the Setups tab, where **`Run now (≈1 min)`** re-scores everything live. Click a symbol to open the stock.

**Messages you may see**

- `No checklist run stored yet — built after each close (15:00), or press Run on the Setups tab.` — the app has not yet run its 15:00 post-close job since you installed it. Either wait for it or go to the Setups tab and press Run.
- `Setups unavailable: …` — the stored run could not be read; the rest of the card still works.

**How to benefit from it**

- **Shop only from green SETUP rows.** The whole purpose of the checklist is to stop you buying a stock with two crosses because one indicator looked exciting. A 5/6 or 6/6 with nothing against it is where your research time should go.
- **Use the grey `needs …` note as your watch condition.** A WATCH row that says `needs volume` is a stock whose chart is right but whose buyers have not shown up yet. Put an alert on it (Portfolio page) and let the volume come to you instead of chasing.
- **Look at *which* chip is missing, not just the count.** A missing `Vol` on a 5/6 is a very different thing from a missing `Trend`. Trend and Risk are the two pillars that veto the trade outright, so a row can never be a SETUP with either against it.
- **Cross-check with the other columns.** A SETUP that also appears in `Strongest vs EGX30` and sits in a green sector on the heatmap is a much stronger case than a SETUP in a red sector. Agreement between independent tools is the edge.
- **Common mistake:** treating six ticks as a guarantee. The checklist filters out bad trades; it does not promise good ones. Still open the Stock page, still check the R:R, still size at 1%.

#### 3.2.2 Column — `Your positions`

**What it is** — The **Position Guardian**'s live verdict on every position you have recorded on the Portfolio page. Everything else in the app helps you decide what to buy; this column is the one that answers the harder question — *what should I do with what I already hold?* It is evaluated fresh every time the dashboard loads (read-only: it does not save verdicts or send Telegram messages — that is the `Run & notify` button on the Portfolio page and the scheduler). The link `portfolio →` opens the Portfolio page.

**What you see**

Positions whose verdict is **not** a plain HOLD, most urgent first, then the advice-level ones. Each row:

| Element | Meaning |
|---|---|
| **Symbol** | Click to open the Stock page (where your entry, stop and suggested stop are drawn on the chart). Hover the row to read the first reason behind the verdict |
| **Verdict badge** | The Guardian's decision (see table below). **Red** = critical, **green** = a profit-side action, **amber** = a warning or advice |
| **R figure** | Your current result in R, e.g. `+1.35R` or `-0.40R` — profit or loss measured in multiples of the risk you took at entry (entry minus the stop you recorded at entry, not the current stop). Blank when that risk is unknown: no stop was recorded, the stop was already above cost when recorded, or no price could be found |

Under the list a grey summary: `1 need a decision · 1 advice · 4 hold`. When nothing is critical, action or warning the first part reads `nothing urgent` (e.g. `nothing urgent · 1 advice · 4 hold`, or `nothing urgent · 5 hold` when every position is a HOLD). Positions on HOLD are counted but not listed — they need nothing from you.

| Verdict badge | Severity / colour | It means | What to do |
|---|---|---|---|
| **EXIT STOP** | critical — red | The price is at or below your current stop | Sell. That was the plan, and the plan was written when you were calm |
| **TRAIL EXIT** | action — green | After reaching at least 1R, the price has fallen to or below its post-entry high minus 2.5× the 14-day average true range (ATR) — the multiplier is 2.5 by default and configurable | The move is over — take what is left |
| **TARGET2 HIT** / **TARGET1 HIT** | action — green | Price reached your target 2 / target 1 | Book profit, or take a partial and move the stop to breakeven |
| **STOP TOUCHED** | warning — amber | Today's low pierced the stop but the close recovered | Check whether your broker filled you; decide whether the level still holds |
| **THESIS BROKEN** | warning — amber | The stock's latest post-close signal turned SELL, or its composite score has fallen 15 or more points since you bought (15 by default, configurable) | Re-read your entry note — if the reason for the trade is gone, so is the trade |
| **TIGHTEN STOP** | advice — amber | The trade reached 1R and a higher stop (the trailing level, never below breakeven) sits above your current stop | Raise your stop with the `Stop` button on the Portfolio page |
| **BEARISH EVENT** | warning — amber | The pattern scanner confirmed a bearish event or shape on this stock within the last 3 sessions (bull trap, upthrust, change of character, failed retest, a confirmed double top…) | Read the level it names; tighten the stop under the nearest tested support, or leave if the pattern's target sits below your stop |
| **CHECKLIST EXIT** | warning — amber | The six-pillar sell checklist says exit (thesis and weekly both broken, or three pillars against) while the stop is still intact | Sell into strength if it comes, otherwise at market; the reason text repeats the checklist headline with its levels |
| **TIME STOP** | advice — amber | Held 15 or more sessions (15 by default, configurable), still inside ±0.5R, and nothing above applies | Dead money — consider freeing the capital for a live setup |
| **HOLD** | ok — not listed | Stop intact, no target reached, thesis unchanged | Nothing. Doing nothing is a decision too |

A position shows only its **most severe** verdict; hover the row to read the first reason behind it. The colour tells you the urgency class (red, green, amber); the words tell you what actually happened.

**What the buttons do** — None here. Acting on a verdict (closing, raising the stop, taking a partial) happens on the Portfolio page via `portfolio →`.

**Messages you may see**

- `No open positions recorded. Add them on the portfolio page and the Guardian starts watching.` — you have not logged any positions yet.
- `Guardian unavailable: …` — the evaluation failed (usually the price feed); reload in a minute.

**How to benefit from it**

- **Look at this column before you look at any buy idea.** A red `EXIT STOP` on a position you own is worth more than any new setup — losing less is how most accounts are saved. If a red badge is showing, deal with it first.
- **Green badges are good news that still needs a hand.** `TARGET1 HIT` and `TRAIL EXIT` are the app reminding you that winners have to be *sold* to become profit. The classic answer to a target-1 hit is to sell part and move the stop to breakeven, so the rest of the trade cannot become a loss.
- **Act on `TIGHTEN STOP` the same day.** The suggested stop is never below your entry, so raising it turns an open trade into a risk-free one (before fees). This is the single easiest improvement most traders never make.
- **Take `TIME STOP` seriously.** Capital sitting flat for fifteen sessions (the default) is capital not working in a real setup. Compare the dead position with the `Best setups` column right next to it.
- **Common mistake:** hovering a `THESIS BROKEN` and deciding to "give it a few more days". The reason you bought has changed; hope is not a reason. Re-read your own note and decide with the numbers in front of you.

#### 3.2.3 Column — `Patterns on your stocks`

**What it is** — Confirmed chart or price-action patterns from the daily pattern scan (EGX100 universe), filtered down to only the stocks you **hold** or have on your **watchlist**. Candlestick patterns and neutral-direction patterns are deliberately left out — they fire on many stocks every day and would bury the meaningful ones. The link `all patterns →` opens the Patterns tab of the Screener.

**What you see**

Up to eight rows:

| Element | Meaning |
|---|---|
| **Symbol** | Click to open the Stock page, where the pattern's points, neckline and target are drawn on the chart. Hover the row for the scanner's note |
| **Direction badge** | `bullish` in green or `bearish` in red |
| **Pattern name** | e.g. *Double bottom*, *Breakout*, *Head and shoulders*. Followed by ` · watchlist` when the stock is on your watchlist rather than held (held stocks have no suffix) |

**What the buttons do** — None. `all patterns →` opens the full Patterns tab where you can filter by category, status and **Universe** and press **`Scan now (≈1 min)`**.

**Messages you may see**

- `No confirmed chart or price-action pattern on a stock you hold or watch (scan of 2026-09-02).` — nothing confirmed on your names in the latest scan; the date tells you how fresh that scan is.
- `Patterns unavailable: …` — the stored scan could not be read.

**How to benefit from it**

- **A red `bearish` on a stock you hold is an early warning the Guardian may not have yet.** The Guardian works from your stop and targets; a confirmed head-and-shoulders or bull trap is the chart telling you the same thing a few days earlier. Open the stock, look at where the pattern's target sits relative to your stop, and consider tightening.
- **A green `bullish` on a watchlist name is your cue to go and check the checklist.** Confirmed means the pattern's trigger line was already broken (or the price-action event completed) recently — the signal is live, not forming. Look for it in `Best setups`; if it is not there, the Stock page tells you which pillar is missing.
- **Confirmed patterns also feed the Scorecard**, which measures what the stock did 5, 10 and 20 sessions later. Over a few months you will learn which shapes actually work on EGX and which merely look nice.
- **Common mistake:** trading the shape instead of the break. Pattern recognition is subjective; the scanner will flag shapes you would not, and miss some you would. Trust the *break with volume* on the Stock page, not the name in this column.

#### 3.2.4 Column — `Strongest vs EGX30`

**What it is** — The top five of the **relative-strength ranking**: the EGX100 stocks that have beaten the EGX30 index the most over the last one, three and six months. Strength relative to the index is the classic swing-trade pool; weakness relative to the index is the classic thing to avoid. The ranking is rebuilt after every close and stored, so this loads instantly. The link `leaders →` opens the Leaders tab of the Screener.

**What you see**

| Element | Meaning |
|---|---|
| **`#1` … `#5`** | Rank in the stored ranking |
| **Symbol** | Click to open the Stock page |
| **`RS 87.50`** | The RS score, 0–100. It is the stock's percentile rank of *excess* return over EGX30 across 1, 3 and 6 months, weighted 30 / 40 / 30. Higher = stronger than more of the universe |
| **`+12.34% 3m`** | The stock's own three-month return, green when positive, red when negative |
| **`new high` badge** | Green; shown when the price is within 2% of its 52-week high |

Under the list: `ranking of 2026-09-02` — the date the ranking was built.

Stocks whose typical daily traded value (20-day median) is below the liquidity floor — 5,000,000 EGP by default — are removed from the ranking before the top five is taken, so a name here is one you can realistically get out of. The benchmark is Yahoo's EGX30 index when it has enough history; otherwise an equal-weight proxy built from the EGX30 members is used (the Leaders tab says which).

**What the buttons do** — None. `leaders →` opens the full table with a **Universe** selector and a **`Refresh (≈1 min)`** button that recomputes the ranking.

**Messages you may see**

- `No ranking stored yet — built after each close, or press Refresh on the Leaders tab.`
- `Leaders unavailable: …`

**How to benefit from it**

- **Buy strength, not bargains.** A stock at `#2` with `RS 94.00` and a `new high` badge is doing something the other ninety-odd stocks are not. Stocks making new highs in a market that is not have real buyers behind them; that is where swing trades tend to work.
- **Use it as a filter on the Candidates card.** A candidate that is also in this top five has *both* a fresh signal and months of proven relative strength. A candidate near the bottom of the Leaders table has a fresh signal on a stock the market has been rejecting for months — be far more careful.
- **Check your own holdings against it.** If a position you hold sits at the bottom of the full Leaders table while it drifts sideways, you are holding the market's least-wanted stock and hoping. Compare with the `TIME STOP` advice in the positions column.
- **Common mistake:** buying the `new high` badge blindly at any price. New highs are where strength lives, but you still need a stop under a real support and at least 2R of room — the checklist and trade plan on the Stock page decide that, not the badge.

---

### 3.3 Card — `Global snapshot`

**What it is** — A strip of the outside prices that matter to a Cairo trading day, fetched from Yahoo: first the Egypt row (USD/EGP, Brent oil, gold, silver), then US indices, US funds, key currencies and crypto — each with a readable name, its ticker, latest value and percentage change.

**What you see** — Five labelled rows of tiles, Egypt first. Each tile shows **what it is** in bold (for example `Brent oil`), the ticker(s) and unit in small grey type underneath (`FX:UKOIL spot · BZ=F fut · USD / barrel`), the **value** on the right with its day's **% change** coloured green (up), red (down) or grey (flat), and — for Brent, gold and silver — a second, smaller `FUT` line with the futures price and change. Hover any tile to read a one-line explanation of why it matters to an EGX trader. A `—` means that value was unavailable. A footer line gives the time of the quotes. On failure the card shows an error box beginning `Global snapshot: …`.

| Row | Tiles | Why it is here |
|---|---|---|
| **Egypt & commodities** (teal border) | `USD / EGP` (TradingView FX_IDC:USDEGP, pounds per dollar — up means the pound weakened), `Dollar index` (TVC:DXY), `Brent oil`, `Gold`, `Silver` | The prices that move Egyptian earnings, foreign flows and local savers' choice between gold, dollars and stocks. **Brent, gold and silver show two figures**: the big one is the **spot** price from TradingView (the same UKOIL / XAUUSD / XAGUSD figure you see on a TradingView chart), the small `FUT` line underneath is the **front-month futures** contract from Yahoo (BZ=F, GC=F, SI=F). They differ by a little — futures carry storage and interest cost, so gold futures normally sit slightly above spot — and by timing, since the two sources refresh at different moments. If TradingView is pausing, the tile falls back to Yahoo and the hover text says so |
| **US indices** | `S&P 500`, `Dow Jones`, `Nasdaq`, `VIX fear index` | World risk appetite; a VIX above 20 usually means foreign money leaves emerging markets first |
| **US funds** | `S&P 500 ETF`, `Nasdaq-100 ETF`, `Gold ETF` | Tradable versions of the above |
| **Currencies** | `EUR / USD`, `GBP / USD`, `JPY / USD` | Dollar strength against the majors |
| **Crypto** | `Bitcoin`, `Ether`, `Solana`, `BNB` | A pure risk-appetite gauge |

All quotes are delayed Yahoo data. The US rows show the last close when the US is shut, which is the normal case during the Cairo session.

**What the buttons do** — None. Read-only information; it refreshes with the page.

**How to benefit from it**

- **Three-second sanity check before you commit money.** Egypt does not trade in a vacuum: a sharp US sell-off or a spiking dollar tends to hit EGX sentiment within a session or two, especially in the large EGX30 names that foreign funds own.
- **Deep red across the strip = size down.** You do not need to understand why the world is falling to know that today is not the day to take your largest position. Combine it with `% Advancing`: weak world *and* weak breadth is a stay-in-cash day.
- **Green world, red Egypt?** That divergence is worth a look — it usually means a local story (currency, rates, a policy headline) is driving EGX, and local stories are where the Morning brief and the News tab on the Stock page earn their keep.
- **Common mistake:** reading it as a trading signal for individual Egyptian stocks. It is context, not a trigger.

---

### 3.4 Cards — `Top gainers`, `Top losers`, `Most active`

**What it is** — Three side-by-side tables from the EGX market overview showing today's biggest risers, biggest fallers, and the stocks with the most shares traded. This is the same data that feeds the breadth tiles, refreshed at most once a minute.

**What you see** — Each table shows up to 8 stocks with the same four columns:

| Column | Meaning |
|---|---|
| **Symbol** | The ticker code (e.g. COMI). A link to the Stock page |
| **Price** | Latest price in EGP |
| **Chg %** | Today's percentage move — green if up, red if down, grey if flat |
| **Vol** | Shares traded today, shortened: `1.2K` = 1,200 · `3.45M` = 3,450,000 · `1.20B` = 1.2 billion |

While loading you see grey placeholder lines. `No rows returned.` means the overview came back without that list. If the whole overview fails, all three cards show an error box beginning `Market overview: …` (see 3.8 for the friendly versions of these errors).

**What the buttons do** — **Click anywhere on a row** (or on the symbol) to open that stock's full analysis on the Stock page. Nothing else is clickable.

**How to benefit from it**

- **`Most active` is usually the most useful of the three.** Real institutional interest shows up as volume before it shows up as price. A stock in `Most active` that is *not* in `Top gainers` — heavy trading without a big move — is either quiet accumulation or quiet distribution; the Smart Money tab on its Stock page tells you which.
- **Treat `Top gainers` as a late list.** By the time a stock is the day's biggest riser, the move you wanted has largely happened. On EGX a stock near the top of the daily price band (the app assumes ±20% by default, configurable) may also be limit-locked — you often physically cannot buy it. Use gainers to spot which *sector* is waking up, then look for the second- and third-strongest names in that sector that have not run yet.
- **Use `Top losers` two ways.** First, as a do-not-catch-the-falling-knife list — check whether the loser is in your watchlist or holdings and whether the Guardian has something to say. Second, as a place to spot a quality company being sold on a one-day headline; a name here that is still `✓` on Trend in the checklist and at a tested support deserves a look.
- **Cross-reference with the checklist.** A top gainer that also shows up in `Best setups` with `✓` on Vol is a breakout with buyers behind it. A top gainer on quiet volume is a candidate for a `⚠` and a false breakout tomorrow.
- **Common mistake:** buying the biggest gainer because "it's strong". Strength that started three hours ago is not the same as strength that has lasted three months — that is what the `Strongest vs EGX30` column measures.

---

### 3.5 Card — `Sector heatmap`

**What it is** — A grid of coloured tiles, one per EGX sector (Banks, Real Estate, Chemicals, Food, Telecom, and so on), each showing the sector's average move today. The small grey stamp on the right of the title (e.g. `2026-09-03 12:40`) is when the scan was taken.

**What you see**

- Tiles are **sorted strongest first** — top-left is the best sector of the day, bottom-right the worst.
- **Green tile** = sector average is up; **red tile** = down; a plain grey tile means no number was available for it.
- **The deeper the colour, the bigger the move.** Shading grows with the size of the move and reaches its deepest at roughly a 2% average move; beyond that all tiles look equally intense, so read the printed percentage for the big days.
- Each tile carries the **sector name** (cleaned up: `Banks`, `Real Estate`, `IT`, `Food & Beverages`) and the **average change** with sign, e.g. `+1.84%`, coloured to match. `—` when unknown.
- Hover a tile to see its full name.
- On failure the card shows an error box beginning `Sectors: …`.

**What the buttons do** — Tiles are **not clickable** and there are no buttons. To dig into a sector, use the Screener page.

**How to benefit from it**

- **Money rotates between sectors in waves — trade with the current, not against it.** Picking the best stock in a sinking sector is far harder than picking an average stock in a rising one. Before you research a candidate, find its sector on this grid: green and near the top-left is a tailwind; deep red is a headwind you need a very good reason to fight.
- **Watch for persistence, not one day.** Look at the heatmap every morning. A sector green three or four sessions in a row is leadership; a sector that flips colour daily is noise. Leadership is where the `Strongest vs EGX30` names will start appearing.
- **Combine with breadth.** Broad green with one deep-red sector is a healthy market with a sector-specific problem — avoid that sector, trade the rest. Broad red with one green sector is a defensive rotation — that green sector is where money is hiding, and hiding places tend to get crowded and then sold. Treat it with care.
- **Use it to spread risk.** If your three open positions are all in the same red tile, you do not have three trades — you have one big sector bet. Check this before adding a fourth.
- **Common mistake:** buying the deepest-green sector's biggest gainer. That is the late-and-crowded corner of the market. Prefer a leading sector's second-tier names that are still forming setups.

---

### 3.6 Card — `Candidates`

**What it is** — **The heart of the whole app.** A ranked shortlist of stocks flagged by **several independent scanners at once**. One scanner finding a stock is a coincidence; a volatility squeeze *and* a volume breakout *and* smart-money accumulation on the same name is a signal. The card opens instantly with the **stored** result of the last post-close scan and lets you re-run every scanner live with **`Rescan`**.

**What you see**

In the title bar, on the right:

- A grey stamp: `stored scan · 2026-09-02` when you are looking at the saved result of the 15:00 post-close job, or `live · 2026-09-03 12:41` after a live run.
- The **`Rescan`** button (hover it: *"Re-run every scanner now (about a minute)"*).

While the card is loading — briefly for the stored view, for about a minute during a live run — a pill reads `Running scanners… (can take a minute)`. If the stored scan is empty (for example on a fresh install, before the first 15:00 job) the app automatically falls back to a live run.

The table shows up to 10 stocks:

| Column | Meaning |
|---|---|
| **Symbol / scanners** | The ticker (a link to the Stock page) with one small badge for **each scanner that flagged it**: `squeeze`, `volume_breakout`, `smart_money`, `momentum` |
| **Price** | Latest price |
| **Chg %** | Today's move, green / red / grey |
| **Score** | The app's composite stock quality score, to one decimal (higher is better). `—` when that stock was not scored: on a live run only the top 15 merged names are scored (to keep the run to about a minute), and in the stored view the score is only present if the scanner itself recorded one, so `—` is common there — open the Stock page or press `Rescan` to see it |

**Click any row** to open the stock's full analysis.

**The four scanners behind the badges** (the settings used for this card):

| Badge | What it found | How it is set for Candidates |
|---|---|---|
| **`squeeze`** | Bollinger Band width has compressed to an unusually tight range — a coiled spring before a move | Band width no more than 0.04; up to 40 names |
| **`volume_breakout`** | Volume at least 1.8× the 20-day average **together with** a price move of at least 2% | Bearish breakouts (a big *down* day on volume) are thrown away — this is a bullish shortlist; up to 25 names |
| **`smart_money`** | EGX30 members showing institutional accumulation in the volume-flow read over the last 6 months | Only names at or above the accumulation threshold (composite 58) count; up to 15 |
| **`momentum`** | A strong bullish daily candle with at least 1% growth, then verified against real daily history: the last three closes must each be higher than the one before, with each candle closing above its open | Names that fail the history check are dropped (the first 15 hits are checked; any beyond that are kept unverified); up to 25 names |

**Four more badges — the proven rules (added 2026-09-05).** `range_breakout`, `squeeze_breakout`, `momentum_3` and `pullback_trend` are the app's **own** candle rules — the four entry rules the `Proven edge` card measured over five years — run every post-close on the **last completed daily bar of every listed EGX stock**, on Yahoo candles, so they never depend on TradingView. Their hits are journaled under the rule name, which means they enter the ranking with the **weight already measured on thousands of replayed signals** (a 20-day high breakout weighs more than a three-rising-closes badge from day one). Illiquid names are dropped before you see them. `squeeze_breakout` belongs to the **coil** family, `range_breakout` and `momentum_3` to **thrust**, `pullback_trend` is its own family. On the Screener's `Candidates` tab a grey line under the buttons reads e.g. `Proven rules for 2026-09-03: 7 hits — 20-day high breakout 3 (edge, n=4015) · Squeeze breakout 1 (edge, n=1394) · …`, and a `Scan proven rules` button re-runs them on demand (a few minutes on a cold cache, in the background).

**How the list is ranked** — read this once, it explains the order you see:

1. **Signal families, not raw badge counts.** `volume_breakout` and `momentum` measure the *same* daily bar (a big up-day on volume trips both), so they count as one family, **thrust**. `squeeze` is the **coil** family and `smart_money` is the **flow** family. A stock with `squeeze` + `smart_money` (two families) ranks above one with `volume_breakout` + `momentum` (one family, two badges) — the second is one piece of evidence counted twice.
2. **Proven evidence first.** Each family is weighted by its scanner's track record from the **Scorecard** tab (Screener page). A scanner weighs 1.0 until it has 20 graded hits, so early on the ranking is simply the family count. After that its weight is twice its 10-day beat rate against EGX30, kept between 0.5 and 1.5 — a scanner that beats the index 70% of the time weighs 1.4, one that beats it 30% of the time weighs 0.6. Where two scanners share a family, the family takes the better weight. The list slowly learns which of its own tools work on this exchange.
3. Then family count, then raw badge count to break ties, then the Score, then today's change.

**The liquidity filter** — on EGX the tightest-looking "setups" are often flat, illiquid names nobody can exit. Any candidate whose typical daily traded value (20-day median of price × volume from the app's own post-close snapshots) is **known** to be below 5,000,000 EGP (the default floor, configurable) is removed before you see it. If the app has fewer than five stored sessions for a stock it cannot judge its liquidity, so the stock is kept — unknown is never treated as illiquid. This means the filter only starts biting once the 15:00 job has run for about a week.

**What the buttons do**

- **`Rescan`** — runs all four scanners live right now against current (delayed) data. Takes about a minute; the pill shows while it runs, and the stamp switches to `live · …`. A live rescan is for looking, not for record-keeping: it does not overwrite the stored scan, and it does not create Scorecard hits — only the automatic 15:00 post-close run does that, so the track record stays one clean entry per session.
- **Click a row** or a symbol — opens the Stock page.

**Messages you may see**

- `No candidates from today's scans.` — the scanners ran and nothing qualified. This is real information: the market has no multi-scanner setups right now. A day to stay in cash.
- `Candidates: …` in an error box — the run failed; the most common cause is a short TradingView pause (see 3.8). Wait a minute or two and press `Rescan`.

**How to benefit from it**

- **Start your research here, not with a stock someone mentioned on Facebook.** The list is the app's answer to "where is the evidence stacking up today?" Pick two or three names — ideally from a green sector on the heatmap — and open their Stock pages.
- **Read the badges, not just the position in the list.** `squeeze` alone is *early* (the move has not happened — good entry, uncertain timing). `volume_breakout` + `momentum` is *now* (the move is starting — confirm it is not already extended). `smart_money` is *quiet* (institutions accumulating — best when paired with a squeeze, because the spring is coiled *and* someone is loading it). Two different families on the same stock is the combination to prize.
- **Look at the Score column second.** Two candidates with the same badges but scores of 78 and 52 are not equal; the Score tells you the overall technical quality behind the fresh signal. A `—` means "not scored yet", not "bad" — open the Stock page to see it.
- **Then hand the name to the checklist.** A candidate that is also a green SETUP in the decision card has both a fresh trigger and a full six-pillar structure behind it. A candidate that the checklist calls NO SETUP because Trend is against it is a bounce in a downtrend — the most common way to lose money on a "great signal".
- **Respect the empty list.** `No candidates from today's scans.` is not a broken app; it is the app declining to invent a trade. Forcing one on such a day is how you turn a quiet week into a losing one.
- **Common mistakes:** (1) counting badges as if four badges meant four times the evidence — the families explain why they do not; (2) buying a candidate without opening its trade plan — every name here still has to pass the R:R rule on the Stock page; (3) pressing `Rescan` every few minutes during the session and expecting new names — the scanners read daily bars, so the list changes slowly.

---

### 3.6.1 Card — `Proven edge`

**What it is** — The app's own report card. Every other card tells you what the tools *say*; this one tells you which tools have actually been *right* on EGX history, and which have not. It answers the question you should ask before trusting any signal: "has this ever worked here, on enough trades to mean something?"

Three kinds of rows share one table:

| Kind badge | What was measured | The two numbers |
|---|---|---|
| **Rule** | One of the app's four entry rules (squeeze breakout, 20-day high breakout, pullback in uptrend, three rising closes) traded on **every** EGX100 stock over the last three years, entering at the next open, exiting by the Guardian's rules, fees and slippage charged | `Samples` = trades; `Win / beat %` = winning trades; `Avg R / excess` = average R per trade (the expectancy per unit of risk) |
| **Scanner** | A live scanner (`squeeze`, `momentum`, `volume_breakout`, `smart_money`) or one of the replayed candle rules that stands in for it, graded by the Scorecard | `Samples` = graded signals; `Win / right %` = share of signals where the stock moved the signal's way relative to EGX30 over the next 10 sessions; `vs random` = that rate minus what a random entry achieves; `Avg R / excess` = average return relative to EGX30 over those 10 sessions, in %, **signed so that + always means "the signal was right"** |
| **Pattern** | A confirmed chart pattern (double bottom, breakout, bull trap, …) graded the same way, on its break day. A `bearish` chip marks patterns that are graded on the stock **falling** — a triple top with a 74% right-way rate means the stock lagged the index 74% of the time after it | same as Scanner |

**The yardstick — read this once.** On EGX a stock bought at random beats the index over the next 10 sessions only about **44%** of the time (the app measures the exact figure on every refresh and shows it in the headline). That is not a bug: single-stock returns are skewed — most sessions lag the index a little, a few fly. Judging a signal against 50% would condemn everything, so every rate here is judged against the **random-entry rate**, and every average excess against the random-entry excess. `vs random` is the number to read.

**The verdict column**, in plain words:

| Badge | Means | Rule of thumb used |
|---|---|---|
| **Proven edge on this sample** (green) | Did clearly better than buying at random, on 20+ samples | Rules: average R of +0.20 or better after costs. Scanners/patterns: average excess at least 0.5 points above the random entry **and** beyond two standard errors (so a handful of lucky trades cannot qualify), with a right-way rate not more than 3 points below random |
| **Coin flip — no reliable edge** (amber) | Not distinguishable from buying at random | Rules: average R between 0 and +0.20. Scanners/patterns: inside the bands above |
| **Worse than the index — avoid or downweight** (red) | Buying at random would have done better | Rules: average R at or below zero. Scanners/patterns: average excess at least 0.5 points (and two standard errors) **below** random, or a right-way rate more than 3 points below random |
| **Too few signals to judge** (grey) | Fewer than 20 samples — hidden from the table, counted in the footer | — |

A small `replay` badge on a row means the record comes from the historical replay (below), not from live scans. Hover a verdict to read the basis sentence behind it.

**What you see** — a one-sentence headline (`Of 31 rules and signals with enough history, 6 show an edge, 12 do worse than the index. Strongest: … Negative ones are downweighted in Candidates and should not be traded on their own.`), then up to 14 judged rows, rules first, then a footer with how many more rows exist and where the full table lives (Screener → Scorecard). The grey stamp shows when the table was computed; `never computed` on a fresh install.

**What the buttons do**

- **`Replay history`** — the important one, press it once. The app re-runs its own four entry rules and the whole pattern detector over **five years of daily candles for every EGX100 stock**, journals each historical signal, and grades it by what happened 5, 10 and 20 sessions later against EGX30. That is thousands of graded signals in about 25 minutes instead of waiting months for live hits. It runs in the background: a progress line (`Replaying history… 37 / 100 stocks (COMI) · 9 min`) replaces the buttons until it is done, and you can leave the page. Replayed rows are marked `replay` everywhere, **never** appear in Candidates or Setups, and are kept when old live hits are pruned. Pressing it again later only adds sessions that were not there before.
- **`Refresh`** — rebuilds the table from the graded history plus four universe backtests (a few minutes, background). The weekly maintenance job (Saturday) does the same automatically.
- **`include checklist`** (tick box next to `Replay history`) — also replays the six-pillar **buy checklist** on every fifth past session of every stock and journals its verdict (`checklist_setup` / `checklist_watch` / `checklist_no_setup`), graded like any signal. After `Refresh` the card shows a **Buy checklist** line: *The checklist works: over the next 10 sessions a SETUP beat EGX30 by +1.9% on average (1,240 verdicts) versus −0.3% for a NO SETUP (4,800) — a +2.2-point gap…* or, honestly, that it does not. This is the only way to know whether the card you use to decide a buy actually sorts winners from losers on this exchange. The post-close job also journals every live `Best setups` verdict, so the live record grows on its own. Adds roughly 15 minutes to the replay.

**How the verdicts change the rest of the app** — the Scorecard weights that order the `Candidates` list now rest on this record: a scanner's weight is 1 + 2 × (its right-way rate − the random-entry rate), so 46% against a 44% yardstick is 1.04 (slightly better than chance), not a red 0.92. A live scanner that has not yet collected 20 live graded hits **borrows the weight of its replayed candle rule**: `squeeze` from `squeeze_breakout`, `momentum` from `momentum_3`, `volume_breakout` from `range_breakout`. `smart_money` has no candle equivalent (it is a TradingView composite) and stays neutral until its own live record exists. The Scorecard's `Weight from` column shows which record is in use.

**How to benefit from it**

- **Read it before you read Candidates.** If `momentum_3` is a coin flip on 900 signals, a `momentum` badge is not evidence — it is a description of yesterday's candle. Give your attention to the families with a green verdict.
- **A red rule is a rule to stop trading**, not to trade the other way. "Worse than the index" usually means "buys after the move is over"; the fix is patience, not shorting.
- **Samples matter more than the percentage.** A 70% beat rate on 22 signals and a 54% beat rate on 800 signals are not comparable; the second is the more trustworthy number. That is why rows under 20 samples are hidden.
- **Expect modest numbers.** On a liquid index a beat rate of 55–58% with positive excess *is* an edge. Anything claiming 80% on hundreds of signals is a bug, not a discovery — tell the developer.
- **It is a past record, not a promise.** An edge measured over three years can fade. Refresh weekly, and if a green row turns amber, believe the new number.

---

### 3.7 Card — `Morning brief`

**What it is** — A written summary of the day, produced by an AI analyst from the app's own data and saved so you can re-read it. On page load the card shows the **most recent** saved brief. The **`Generate`** button writes a fresh one.

**What you see**

- A small grey **date** line (the day the brief was written), then the **brief text**.
- The brief is written to a fixed structure, so you always know where to look:
  1. **Market pulse** — index and breadth read, session context.
  2. **Sector and leadership notes** — where the strength and weakness is.
  3. **Top screener candidates** — for each notable candidate: why it fired, its score/signal, and a one-line **WATCH CONDITION** (what would have to happen before acting — never a buy or sell instruction; a day with no qualifying candidates is treated as a valid, useful answer).
  4. **Alerts and open positions** — what fired since yesterday and how your open positions look, flagging any near a stop or target.
  5. **Plan for today** — 3 to 5 bullet watch items.
  Every brief ends with the exact sentence *"Not financial advice."*
- The analyst is instructed to cite only numbers that appear in the app's data, to state the date and time of anything it quotes, to say plainly when a data section was unavailable, and — because news coverage of EGX is thin — never to read the *absence* of headlines as calm.
- What goes into it: your open positions and any alerts fired in the last 24 hours first (so on a busy day it is the candidate list that gets shortened, never your own risk context), then the market overview and a fresh live run of the Candidates scanners.

**What the buttons do**

- **`Generate`** — the button greys out, the card shows the pill `Generating morning brief… (LLM call, may take ~1 min)`, and about a minute later the new brief appears with a green toast `Morning brief generated.` The brief is saved, so it is still there tomorrow. If it fails you see an error box `Brief generation failed: …` and a red toast `Brief failed: …`; the button becomes available again.
- The brief is also written **automatically every trading day at 09:30 Cairo** (skipped on weekends and holidays), so when the app has been left running you simply find it here before the 10:00 open.

**Messages you may see**

- `No morning brief yet (no morning brief found). Use Generate.` — no brief has ever been saved. Press `Generate`.
- `Brief generation failed: ANTHROPIC_API_KEY not configured` — the brief needs an AI key in the app's settings (see section 1). Without it every other card on this page still works normally; only this one card is affected, and the 09:30 automatic brief is skipped.

**How to benefit from it**

- **Read it with your coffee, before the open.** It joins the dots that the cards above show separately — *"breadth is weak, banks lead, three candidates share a squeeze, your position in X is one session from its stop"* — the read-through a human analyst would give you, in two minutes.
- **Use the WATCH CONDITIONS as your alert list.** Each candidate comes with a "what has to happen first". Turn the two or three you care about into price-above or entry-hit alert rules on the Portfolio page, and let the app watch the tape while you are at work (rules are checked every 10 minutes during the session).
- **Section 4 is your risk review.** If the brief flags a position near its stop, that is the second warning (the Guardian column above was the first). Two independent parts of the app pointing at the same position is not a coincidence.
- **Re-generate after big changes**, not every hour: after the 15:00 post-close job has stored the day's candidates, or after you have opened or closed a position. The brief uses a *live* candidates run, so each generation costs about a minute.
- **Common mistake:** treating the brief as a recommendation. It is deliberately written to end in *"Not financial advice."* and to give watch conditions instead of orders. Use it to organise your attention, then let the checklist, the trade plan and your position size make the actual decision.

---

### 3.8 The footer and messages shared by every card

**What it is** — Two lines close the page, and a small set of plain-English error messages can appear in any card when a data source hiccups.

**What you see**

- Footer left: *"Analysis tooling — not financial advice. Data delayed ~15 min."*
- Footer right: *"EGX Decision Engine · local"* — a reminder that the app runs on your own machine; nothing about your positions or watchlist leaves it except the requests that fetch market data.

When a card fails to load, the raw technical reason is translated into one of these friendly messages (hover the red box to see the original):

| Message | What it means | What to do |
|---|---|---|
| *"TradingView is pausing this app for a minute or two (rate limit). The chart, your position and patterns still work from Yahoo data. Reload in a minute for the score and trade plan."* | The scanner data source is briefly refusing requests after heavy use | Wait one to two minutes and reload. Cards built from stored data (setups, leaders, patterns, stored candidates) keep working meanwhile |
| *"Yahoo is rate-limiting requests for a short while. Cached data is shown where available; try again in a minute."* | The price-history source is briefly throttling | Same — wait a minute |
| *"The app's server is not responding. Is it running? (see the guide, section 1)"* | The app itself is not running, or the browser cannot reach http://127.0.0.1:8642 | Start the app again (section 1) and reload |

**What the buttons do** — There are none; the error boxes are informational.

**How to benefit from it**

- **Know which cards are live and which are stored.** Breadth, movers, the global strip, the sector heatmap and a live `Rescan` all need the data sources to be awake. The `Best setups`, `Strongest vs EGX30` and `Patterns on your stocks` columns of the decision card, the stored Candidates and the Morning brief read from what the 15:00 post-close job saved, so they survive a TradingView rate-limit pause. The `Your positions` column is the exception: the Guardian is re-run **live** on every load using Yahoo marks, so it survives a TradingView pause but goes red if Yahoo is unreachable (see 3.2.2). If the live cards are red but the stored cards are fine, nothing is wrong with your data — wait a minute.
- **Leave the app running through the trading week.** The automatic jobs (alerts and Guardian every 10 minutes from 10:00 to 14:20 during the session, the full post-close pipeline at 15:00, the brief at 09:30, all Sunday–Thursday and skipped on holidays) are what keep this page instant and its history growing. If the machine was asleep at 15:00, an hourly catch-up runs the missed post-close work once it wakes; a Saturday 12:00 job tidies old records and backs up the database. Everything still works if you do not leave it running — you just have to press `Rescan`, `Run now`, `Scan now`, `Refresh` and `Generate` yourself.
- **Never mistake a delayed price for a live one.** Every figure on this page is at least ~15 minutes old, and outside 10:00–14:30 Cairo it is the last session's close. Place your orders with your real broker at the price you actually see there.

---

## 4. Page 2 — Stock page

**This is the deep-dive page for one company — the place where you decide.** You reach it by clicking any symbol anywhere in the app (Dashboard tables, Screener results, Portfolio rows, the sidebar watchlist) or by typing a ticker in the top-bar search. The address ends in `?symbol=COMI` (or whatever ticker you chose). If you arrive with no symbol the page shows only one message: `No symbol given. … use the search box above.`

The page is two columns. **Left column, top to bottom:** the one-year chart, `Multi-timeframe alignment`, and a card with five tabs (`Smart Money`, `Fibonacci`, `News`, `Debate`, `Thesis`). **Right column, top to bottom:** `Decision checklist`, `Your position` (only if you hold the stock), `Score`, `Trade plan`, `Support & resistance`, `Chart patterns`, `Position size`. On a phone the left column stacks above the right one.

Most sections load independently, so a slow or failed section never blanks the others — you see a grey placeholder or a short loading message (`Loading chart…`, `Checking six pillars…`, `Finding levels…`, `Scanning…`) in that one card only, and a specific error message if it fails. Two exceptions: the `Chart patterns` card and the `Your position` card only start loading *after* the live analysis has answered, so if the analysis fails they stay at `Scanning…` / hidden.

**Suggested reading order for a buy decision:** `Decision checklist` first (is there anything to do here at all?), then `Support & resistance` and the chart (where are the walls?), then `Trade plan` (is the reward worth the risk?), then `Position size` (how many shares?). The left-column tabs are for confirmation and for finding reasons *not* to trade.

Remember throughout: prices are delayed about 15 minutes, the app never places orders, and everything on this page is analysis tooling, not advice.

---

### 4.1 The header strip

**What it is** — the one-line summary at the very top: ticker, price, today's change, the app's one-word signal, and the watchlist star.

**What you see**

| Element | What it shows |
|---|---|
| **Symbol** | The ticker you are viewing (e.g. `COMI`). The browser tab title changes to `COMI — EGX Decision Engine`. |
| **Price** | The latest price from the live analysis. Shows `—` while loading. |
| **Change** | Today's percentage move: green when positive, red when negative. |
| **Signal badge** | The app's overall buy/sell reading. Any word containing *buy*, *bull* or *strong* turns the badge **green**; any word containing *sell*, *bear* or *weak* turns it **red**; anything else (e.g. `NEUTRAL`, `HOLD`) is **amber**. If the live analysis has no signal, the first words of the trade plan's recommendation are used instead. |
| **☆ / ★ star** | ☆ = not on your watchlist, ★ (amber) = on it. Hover to see `Add to watchlist` or `Remove from watchlist`. |

**Fallback when the live feed is slow:** the chart loads from a different (faster) source than the analysis. If the analysis has not answered yet, the header borrows the chart's **last daily close** and the change versus the previous close. Hover the price and you will see the tooltip `last daily close 2026-09-02 (Yahoo) — live analysis still loading`. The moment the live analysis arrives it overwrites the borrowed number. If the analysis fails completely, the price stays `—`, the change disappears, and the `Score` and `Trade plan` cards show `Analysis: …` / `Trade plan: …` errors.

**What the buttons do**

- **☆ / ★** — click once to add the stock to your watchlist (toast: `COMI added to watchlist.`), click again to remove it (toast: `COMI removed from watchlist.`). The sidebar list refreshes immediately. If the save fails you get a red toast `Watchlist: …`. The button is disabled while the save is in progress so you cannot double-click it.

**How to benefit from it**

- Treat the signal badge as a *headline*, not a verdict. It comes from the same engine as the `Score` card; the `Decision checklist` below is stricter and built on Egyptian daily data — when they disagree, trust the checklist.
- Star the 10–15 names you actually know. A focused watchlist is how you stop chasing 260 tickers; the sidebar keeps those names live for you every session, and the Dashboard's `Patterns on your stocks` column only reports confirmed patterns on stocks you hold or have starred.
- If the price shows a borrowed close (hover to check), do not read the `Change` figure as today's live move — it is yesterday's close versus the day before. Wait for the live number before judging a gap.
- A red `Analysis:` error in the right column with a working chart usually means the upstream feed is rate-limited. The `Decision checklist` and `Support & resistance` cards still work (they use the chart's daily data), so you can still make a decision; the `Score`, `Trade plan`, `Chart patterns` and `Your position` cards need the analysis — reload in a few minutes.

---

### 4.2 Card — `Price · 1Y daily`

**What it is** — a one-year daily candlestick chart with volume bars underneath, and dashed horizontal lines for every price level the rest of the page talks about. The small note in the card title says how many candles loaded (e.g. `250 candles`).

**What you see**

- **Candles**: one per trading day. Green body = closed above the open, red body = closed below. Wicks show the day's high and low. Volume bars at the bottom are tinted green or red the same way.
- **Crosshair**: move the mouse over the chart to read the exact date and price on the axes. Scroll to zoom, drag to pan.
- **Dashed price lines** (each labelled on the right axis):

| Line label | Colour | Comes from | Meaning |
|---|---|---|---|
| `entry` | Teal | `Trade plan` | Where the app suggests buying. |
| `stop` | Red | `Trade plan` | Where you get out if the plan is wrong. |
| `T1`, `T2` | Green | `Trade plan` | First and second profit targets. |
| `YOU @ 42.10` | Off-white | `Your position` | Your actual average entry price — only if you hold the stock. |
| `your stop` | Red | `Your position` | The stop you recorded on the Portfolio page. |
| `suggested stop` | Amber | `Your position` | Drawn only when the Guardian says to raise your stop (see 4.10). |
| `support x3` / `resistance x2` | Dark green / dark red | `Support & resistance` | Tested zones with two or more touches; the number is the touch count. Up to four strongest zones. Below the current price = support, above = resistance. |
| `Double bottom neckline`, `Double bottom target` … | Blue | `Chart patterns` | Neckline (trigger) and measured-move target of up to two chart *shapes* (reversals, triangles, wedges, channels, continuations). Candlesticks and price-action events are not drawn. |
| `fib …` | Amber | `Fibonacci` tab | The first three levels listed in the `Fibonacci` tab, labelled with that tab's level name (extensions carry `ext`). |

- **De-cluttering rule**: if two lines would sit within 0.3% of each other, only one label is kept, in this priority order — your own levels (`YOU @`, `your stop`, `suggested stop`) win over the plan's `entry`/`stop`, which win over `T1`/`T2`, which win over decorations (support/resistance, pattern lines, fibs). So if a fib level and the plan's stop coincide, you see `stop`. Nothing is lost — the underlying numbers are still in their cards.

**Messages you might see instead of a chart**

| Message | Meaning |
|---|---|
| `Loading chart…` | Still fetching. |
| `No price history available for this symbol.` | The price source has no daily candles for this ticker — common for very small or newly listed companies. The checklist, levels and patterns use the same daily candles, so they are usually unavailable too. |
| `Chart library failed to load (CDN unreachable).` | Your PC is offline or the charting library is blocked; the rest of the page still works. |
| `Price history came back in an unreadable format.` | The feed answered with something the chart cannot draw; reload later. |
| `Series data came back in an unreadable format.` | The same problem for a single-line chart (an equity or indicator line rather than candles). The chart engine can draw such lines, but no page in this version of the app uses one, so you should not see this message today. |
| `History: …` | The history request itself failed (network or feed error). |

**What the buttons do** — there are no buttons; the chart is read-only. Zoom with the mouse wheel, drag to move, hover for the crosshair.

**How to benefit from it**

- Numbers in a table are abstract; lines on a chart are obvious. Before reading anything else, look at where `entry`, `stop` and the dark-green `support xN` lines sit relative to each other. **A stop that sits above a tested support line is a stop that will be hit before the level holds** — the `Trade plan` card will warn you in words, but you can see it here in one glance.
- Look at how far the nearest `resistance xN` line is above `entry`. If `T1` sits just under a resistance with many touches, expect sellers there and plan to take profit slightly early.
- When you hold the stock, the gap between `YOU @` and `your stop` is the money you have at risk; the gap between `YOU @` and the amber `suggested stop` is profit the Guardian thinks you should lock in. Act on it on the Portfolio page.
- A blue pattern `neckline` sitting just above price with a `target` well above it is a breakout waiting to happen — but the volume bars on the day of the break are what matter (see 4.14). Quiet-volume breaks on EGX fail often.
- Do not trade off the chart alone: it draws only the tested zones (round numbers and moving averages are *not* drawn, but fibs are). Use it to sanity-check the cards, not to replace them.

---

### 4.3 Card — `Multi-timeframe alignment`

**What it is** — a grid of small tiles, one per timeframe (weekly → daily → 4-hour → 1-hour → 15-minute), each showing that timeframe's trend and momentum, followed by a one-line summary of whether they agree.

**What you see**

- **One tile per timeframe** (normally five; the grid shows at most six), each with three lines: the **timeframe** (e.g. `1W`, `1D`, `4h`, `1h`, `15m`), the **trend** word (green for anything containing *up/bull/buy/strong*, red for *down/bear/sell/weak*, grey otherwise), and a **momentum** line such as `RSI 58.3 ↑` (↑ rising, ↓ falling) or a short signal word.
- **Hover a tile** for a tooltip with the timeframe's label, `Trend strength: …`, `Structure: …`, the bullet-point reasons behind the bias, the advice for that timeframe, and `Error: …` if that interval failed.
- **Amber note** under the grid when a timeframe returned nothing: `No data for 15m, 1h — the upstream feed returned nothing for those intervals. Usually a rate limit; retry in a few minutes.` (or `…for that interval.` for a single one).
- **Alignment badges** under the grid: the overall status (green if it contains *bull/up/buy*, red for *bear/down/sell*, teal otherwise — e.g. `LEAN BULLISH`), `Confidence: …`, `Net +3` (a net vote count across timeframes, positive = bullish), and — the most useful one — an amber `Diverging: 15m, 1h` naming every timeframe that disagrees with the rest.
- If the feed's shape is unrecognised, the raw data is printed as a folded list; if the whole request fails you see an `MTF: …` error.

**What the buttons do** — none. Hover for tooltips; reload the page to retry a failed interval.

**How to benefit from it**

- **Never take a trade that fights the weekly trend.** A buy signal on the 15-minute chart while `1W` is red is a bounce inside a downtrend — the most common trap on EGX. When `1W` and `1D` are both green and agree with your direction, your odds improve dramatically.
- Use `Diverging:` as a warning label. If only the short intraday frames diverge (bearish `15m`/`1h` under a green `1D`/`1W`), that is often just a pullback — potentially a *better* entry price, not a reason to skip. If the *weekly* is the one diverging, walk away.
- Combine with the `Decision checklist`: a `SETUP` verdict with green weekly and daily tiles is the strongest situation this page can show. A `SETUP` with a red weekly tile deserves a smaller position or a pass.
- A daily RSI that is already high and still marked ↑ means you are late to the move; look for the pullback the `Fibonacci` tab and `Support & resistance` card suggest rather than chasing.
- Intraday tiles (`15m`, `1h`) are the ones most often blank because of rate limits. Do not wait for them — the weekly and daily carry most of the weight in a swing trade.

---

### 4.4 Tab — `Smart Money`

**What it is** — the first tab in the left-column tab card (it loads automatically when the page opens). It estimates from price and volume behaviour whether large, informed players seem to be **accumulating** (quietly buying) or **distributing** (quietly selling). Each tab loads once when first clicked and then remembers its content.

**What you see**

- A **verdict badge**: green for anything like `SMART MONEY IN` / `ACCUMULATION` / bullish / inflow, red for `SMART MONEY OUT` / `DISTRIBUTION` / bearish / outflow, amber otherwise. Next to it, `votes: 3 bullish · 1 bearish` — how many of the underlying indicators lean each way.
- A **plain-English sentence** under the badge, one of: `Institutions appear to be buying — volume behaves like accumulation.`, `Institutions appear to be selling — volume behaves like distribution.`, `Volume behaves like quiet accumulation.`, `Volume behaves like distribution into strength.`
- A short table of readings:

| Row | Meaning |
|---|---|
| `Volume-flow score` | `62 / 100 · accumulation` — a composite of volume-flow indicators with its verdict. |
| `Banker-fund oscillator` | `18.4 (was 12.1) · rising` — an oscillator that rises when big-money buying dominates; the previous value shows the direction. |
| `Who is active` | `banker 45 · hot money 30 · retail 25 · …` — an estimate of which type of participant is driving volume. |
| `Priced as of` | The close and date the reading is based on. |

- A grey methodology note (if the engine does not supply its own): `Price/volume-derived proxy for institutional activity — not actual fund-flow data.`
- A folded `Full smart-money payload` you can expand for every raw number.
- On failure: `Smart money: …`.

**What the buttons do** — click the `Smart Money` tab header to show it. Click `Full smart-money payload` to unfold the raw readings.

**How to benefit from it**

- Price tells you *what* happened; volume flow hints at *who* did it. Institutions cannot buy size on EGX without leaving footprints in the volume. **Accumulation under a flat or slightly falling price is one of the most bullish situations you can find** — it often precedes the breakout the `Chart patterns` card is waiting for.
- A red `DISTRIBUTION` reading while the price is still making highs is the classic warning that the move is being sold into. If you hold the stock, tighten your stop; if you do not, do not buy the breakout.
- Use the `votes:` count as a confidence check: `4 bullish · 0 bearish` is a strong read; `2 bullish · 2 bearish` means the indicators disagree and you should give this tab no weight today.
- Remember the note: this is a *proxy*. It is not EGX foreign/local flow data. Never buy on this tab alone — use it to confirm a `SETUP` from the checklist or to veto one.
- Watch `Banker-fund oscillator` turn from falling to `rising` while `Volume-flow score` carries an accumulation verdict; that combination, on a stock sitting `AT SUPPORT`, is worth putting on your watchlist.

---

### 4.5 Tab — `Fibonacci`

**What it is** — a small table of Fibonacci retracement and extension prices calculated from the stock's recent swing. The first three are also drawn on the chart as amber `fib …` lines.

**What you see**

- A two-column table, `Level` and `Price`. Retracement levels are labelled by their ratio as the engine names them; extension levels carry an `ext` prefix (e.g. `ext 1.618`).
- A folded `Full fibonacci payload` with every raw value (it opens automatically if no table could be built).
- Messages: `Waiting for analysis…` (the main analysis has not arrived yet — the tab retries when you click it again), `No fibonacci data in the analysis payload.`, or `Fibonacci: …` when the calculation failed upstream.

**What the buttons do** — click the tab header to view; click `Full fibonacci payload` to unfold.

**How to benefit from it**

- After a stock runs up it usually pulls back before continuing. The middle retracement levels in the table are where pullbacks most often stop and buyers return. **Buying at a fib level that coincides with a tested `support xN` zone from the `Support & resistance` card is a far better price than chasing the breakout.**
- Compare the fib prices with the `Trade plan` `Entry`. If the plan's `Pullback plan` entry sits near one of the retracement levels, the two methods agree and the entry is well-founded.
- Extension levels (`ext …`) are natural places to take profit when the plan's `T2` is far away or when you are already in the trade and the Guardian says `TARGET1 HIT`.
- Do not treat a fib level as a wall on its own; it is a *zone of interest*. Wait for a green candle to close above it (see the chart) before treating it as support.
- If the tab says the data is missing, the swing was too small or the feed was rate-limited — the levels card and checklist still give you real, tested prices.

---

### 4.6 Tab — `News`

**What it is** — recent headlines about the company with a sentiment reading.

**What you see**

- A teal badge `Sentiment: …` when the news service returns a single overall sentiment word or number (a detailed sentiment breakdown is shown as folded raw data instead).
- Up to 12 headlines, each a clickable link that opens the article in a new tab, with a grey line of `source · date` under it. Headlines without a safe web address show as plain text.
- If the news service returns a summary instead of a list, the summary text is shown; otherwise the raw reply is printed as a folded list.
- **Without a news key** this tab shows the error `News: MARKETAUX_API_TOKEN not configured` — the app needs a Marketaux news key in its settings file for this tab to work. Everything else on the page works without it.

**What the buttons do** — click a headline to open the article in a new browser tab. Click the tab header to load or return to it.

**How to benefit from it**

- Charts do not know that the chairman resigned this morning or that a rights issue was announced. **Use this tab as a veto, not as a buy signal:** if the technicals look perfect but there is fresh, material bad news, stand aside for a day and let the market digest it.
- Positive news on a stock that is *already* `AT RESISTANCE` is often the moment insiders sell into retail enthusiasm — check the `Smart Money` tab for `DISTRIBUTION` before buying good news.
- The best combination is *no* news: a quiet stock building a base (`Chart patterns` forming, `Smart Money` accumulating). Headlines usually arrive after the move.
- Check the dates. English-language coverage of EGX names is sparse and items can be weeks old; an old headline is not a reason to act today, and an empty tab is not proof that nothing happened.

---

### 4.7 Tab — `Debate`

**What it is** — two things stacked: first a **rule-based bull/bear signal summary** built from fixed indicator checklists (not AI), then an optional **AI bull/bear debate** you can generate with a button. The two are deliberately labelled so you never mistake a mechanical checklist for a written argument.

**What you see**

*Top part — the rule-based summary*

- Heading `Rule-based signal summary (deterministic checklist — not AI)` and a grey method note from the engine.
- A verdict badge (green for buy/bull, red for sell/bear, amber otherwise) with a confidence badge next to it when available.
- One block per rule set — each named perspective the engine reports (falling back to the name `rule set`) with its written argument.
- While loading: `Computing rule-based signal summary…`; on failure: `Signal summary: …`.

*Bottom part — the AI debate*

- The button `Run AI bull/bear debate` with the hint `LLM call — adversarial bear case, grounded in this page's data`.
- If a debate was generated earlier for this stock, the most recent saved one loads automatically under the heading `AI bull/bear debate · <date>`.
- While generating: `Running AI debate… (LLM call, may take ~1 min)`.

**What the buttons do**

- **`Run AI bull/bear debate`** — sends the stock's full analysis and trade plan, the multi-timeframe read, the smart-money read and the news to the AI and asks it to argue *against* the trade as hard as for it. Takes up to about a minute; the button is disabled while it runs. Success shows a green toast `Debate generated.` and the text; failure shows `Debate failed: …` in the tab and a red toast. Needs the AI key in the app's settings file. The result is saved, so it is still there next time you open the stock.

**How to benefit from it**

- The single most expensive habit in trading is looking only for evidence that confirms what you already want to do. **Read the bear case before you buy, every time.** If you cannot answer its strongest point in one sentence, you do not understand the trade well enough to size it.
- The rule-based summary is the same every time for the same data — use it as a quick "what do the indicators say" check. The AI debate is where the nuance lives (e.g. "the breakout came on below-average volume and into a resistance tested three times").
- Generate the debate *after* the checklist says `SETUP` or `WATCH`, not before — it is slow and costs an AI call, so spend it on candidates that already passed the mechanical filters.
- Save the bear case in your head as your **exit thesis**: if the bear's main argument starts coming true (e.g. "volume dries up after the break"), that is your signal to tighten the stop even if the price has not hit it yet.
- A disagreement between the rule-based verdict (say `BUY`) and the AI debate's lean (say cautious) is not a bug — it is exactly the tension you are paid to resolve. When in doubt, take the smaller position or wait for the pullback.

---

### 4.8 Tab — `Thesis`

**What it is** — the last AI-written investment thesis for this stock, with a button to write a fresh one.

**What you see**

- The `Generate thesis` button at the top.
- Below it, the saved thesis: a small grey date line, then the text. If none exists yet: `No thesis yet (…). Use Generate.`
- While generating: `Generating thesis… (LLM call, may take ~1 min)`. On failure: `Thesis failed: …`.

**What the buttons do**

- **`Generate thesis`** — asks the AI to write a structured thesis using the stock's full analysis and trade plan, the multi-timeframe read, the smart-money read and the news. Takes up to about a minute; the button is disabled meanwhile. Success: green toast `Thesis generated.`; failure: red toast `Thesis failed: …`. Needs the AI key in the app's settings file. The thesis is saved, so it is still there next week.

**How to benefit from it**

- A thesis converts six panels of numbers into an argument you can actually judge — and disagree with. If you read it and think "that is not why I want to buy", you have learned something important about your own reasoning.
- **Write your own one-line thesis before you generate the AI's**, then compare. If yours is "it went up a lot" and the AI's is about volume, structure and levels, you are gambling, not trading.
- Because it is saved, re-read it when the Guardian says `THESIS BROKEN` or `TIME STOP` on your position. The question "is the reason I bought still true?" is much easier to answer honestly when the reason is written down.
- Generate a fresh thesis after a big event (earnings, a breakout, a broken support) rather than every day. Same data → similar text; new data → new information.
- The thesis knows nothing you have not shown the app. It does not know your account size, your other positions, or tomorrow's news. Keep it in the "opinion" column, not the "fact" column.

---

### 4.9 Card — `Decision checklist`

**What it is** — the first card in the right column and **the one to read first**. It scores the stock on the six things a trade needs — Trend, Support / resistance, Volume, Price action, Patterns, Risk plan — gives each a tick, a warning or a cross, and turns them into one verdict with a headline that names what is missing. It runs on the daily chart data, so it answers quickly and keeps working when the live analysis feed is slow. The card title shows `daily · 2026-09-02` — the date of the last daily candle it used.

**What you see**

- While loading: `Checking six pillars…`.
- A **verdict badge**: `SETUP` (green), `WATCH` (amber) or `NO SETUP` (red), next to a big **`N/6`** — how many pillars passed.
- A one-line **headline**, for example `Setup: 5 of 6 pillars in favour, only volume unclear.`, `Watch, don't chase: 4 of 6 in favour; unclear on volume, patterns.`, `Caution: price action is against it; 4 of 6 in favour.`, `Not a setup: 2 pillars against it — trend, risk plan.`, `Not a setup: volume is against it and only 2 of 6 in favour.`, or `Nothing to act on: only 2 of 6 pillars in favour.`
- **Six rows**, each with an icon badge — **✓** green = pass, **⚠** amber = warn, **✗** red = fail — the pillar's name and one sentence of evidence with the actual numbers.

| Pillar | ✓ Pass when | ⚠ Warn when | ✗ Fail when |
|---|---|---|---|
| **Trend** | Price is above the 50-day average and the 20-day average is above the 50-day (the text adds `50-day rising` or `50-day still flat`, and whether swings make `higher highs and higher lows`). The text then adds a **`Weekly:`** sentence — the swing structure and the position versus the 10- and 40-week averages on the daily candles resampled to weeks — ending `The larger trend is up.` | The averages line up but the recent swings are lower highs and lower lows (`the trend is tiring`), or the picture is `Mixed: … No clear trend yet.` — **or the daily uptrend sits inside a weekly downtrend** (`The larger trend is down — daily buy signals are counter-trend. Treat the daily uptrend as a counter-trend bounce.`). | Price and the 20-day average are both below the 50-day — `a downtrend. Buying against it needs a reason.` If the weekly trend is still up the text adds `A pullback inside a larger uptrend — watch for the daily trend to turn back up.` |
| **Support / resistance** | Price is `at support` (sitting on a zone tested 2+ times, within one daily range) or `breaking out` (no tested resistance overhead — `Breakouts need volume (see below).`), or mid-range but with **at least twice as much room up as down and at least 5% up**. | Mid-range without that edge (`Room up 3.1%, room down 2.8% — not an edge.`), or `Levels unavailable.` | Price is `at resistance` — within one daily range of a zone tested 2+ times. |
| **Volume** | At least 55% of the last 20 sessions' volume traded on up days **and** this week (the last 5 sessions) runs at or above the 20-day average — `buyers are doing the work.` | This week is below 0.7× the average (`quiet. Breakouts on quiet volume tend to fail.`), or the mix gives `no clear message from volume.`, or `No volume data.` | 40% or less of volume on up days while activity is 1.1× normal or more — `heavy selling.` |
| **Price action** | Confirmed bullish *events* on the recent sessions outnumber bearish ones (`Bullish — 1 event: Break of Structure (BOS) (also seen as Higher High / Higher Low)`). Rows that describe the same candles count once — see the `Chart patterns` card. | `No decisive price-action event on the last sessions.` | Any bearish reversal on the tape — bull trap, false breakout, change of character, failed retest or upthrust (`Bearish reversal on the tape — 1 event: Bull Trap (also seen as Upthrust, False Breakout)`) — or bearish events simply outnumber bullish. |
| **Patterns** | A confirmed bullish chart shape, with its target, % to target and `N% of the move done.` | A shape is still forming (bullish or bearish) with its trigger price, or `No chart pattern on the daily chart right now (neutral).` | A confirmed bearish shape (with its target) and no confirmed bullish one. |
| **Risk plan** | The levels-based plan (below) gives **2R or more** to the first resistance with a stop at a real level and the stock is liquid — `Reward covers the risk twice or more with a stop at a real level.` | Less than 2R (`Under 2R: acceptable only with a strong trend.`) or the stop is **more than 10% away** (`one limit-down session could gap through it`). | Less than 1R of room (`the reward does not pay for the risk here`), or the stock is illiquid — its median daily traded value is below the floor (by default 5,000,000 EGP). |

- **The levels-based plan line** under the six rows, in grey: `Levels-based plan: entry 42.10 · stop 40.35 (4.16%) · target 46.80 · 2.69R · 237 shares at your risk %`. How it is built: entry = current price; stop = half a daily range **below the nearest support** (or two daily ranges below price if there is none), never closer than three-quarters of a daily range; target = the nearest resistance if it is at least half a daily range away, otherwise 3R; the share count uses your account size and risk % from the app's settings file (by default 100,000 EGP and 1%).
- **How the verdict is decided**: `NO SETUP` if Trend or Risk plan fails, or two or more pillars fail. `SETUP` if five or six pass and nothing fails. `WATCH` if three or four pass and nothing fails, or if exactly one pillar fails but at least three pass. Anything else is `NO SETUP`.
- Messages: `Checklist unavailable: not enough daily history (95 bars)` (the card needs at least 120 daily candles) or `Checklist unavailable: …` for other failures.

**What the buttons do** — none on the card itself. **It quietly pre-fills the `Position size` card**: if the sizer's Entry box is still empty when the checklist arrives, it fills Entry and Stop with the levels-based entry and stop. (The `Trade plan` card does the same with its own levels — whichever finishes first wins, and you can always overwrite the boxes by hand.)

**How to benefit from it**

- **The point of this card is to stop a bad buy, not to bless a good one.** Six ticks do not guarantee a winner; two crosses almost guarantee you should not be there. Read the crosses first.
- `NO SETUP` = walk away today, no matter how good the story is. `WATCH` = put it on the watchlist (star it) and read the headline — it tells you exactly what to wait for (`unclear on volume, patterns` means: wait for a high-volume day or a pattern confirmation). `SETUP` = proceed to `Trade plan` and `Position size`; it is *permission to do the work*, not an order.
- The **Risk plan** pillar is the most Egyptian one: it fails on liquidity and warns when the stop is more than 10% away because EGX halts a stock at its daily limit and a gap can jump straight over a distant stop. A ✗ here means the trade is unsafe even if the chart is beautiful.
- The **Volume** pillar decides breakouts. A `breaking out` support/resistance ✓ with a `quiet` volume ⚠ is the single most common failed trade on EGX — wait for the volume, or buy the retest instead.
- Compare the levels-based plan with the `Trade plan` card below. The checklist's plan is built from *tested* zones on the daily chart; the trade plan uses indicators and volatility. When both put the stop in the same area, the level is real. When they differ by a lot, prefer the one whose stop sits *below* a dark-green support line on the chart.
- A common mistake: reading `4/6` as "67%, good enough". It is not a percentage. Look at *which* two are missing — Trend and Risk plan missing is a `NO SETUP`; Volume and Patterns missing is a `WATCH` that may become a `SETUP` next week.

---

### 4.10 Card — `Your position` (only when you hold the stock)

> **Sell check block (added 2026-09-05).** Under the Guardian's reasons the card now shows a bordered block: a badge `Sell check: HOLD / REDUCE / EXIT` with a one-sentence headline that names prices (e.g. *Reduce: take 50% here (target 1 13.05 reached); stop to 12.60 (just under weekly support 12.75 tested 3x).*), then chips for the levels it cites — red `Exit below 12.50 · your stop`, amber `Bear trigger 12.90 · Double Top`, green `Reduce at 13.55 · target 2`, amber `Trail stop to 12.60 · just under weekly support…` — and six small pillar chips (✓ / ⚠ / ✗ for Thesis, Weekly, Rel. strength, Distribution, Bear events, Exit plan; hover for the status). The full checklist with one sentence per pillar is one click away (`full sell checklist (raw)`), and the same six pillars are described in 7.2. Read it as: **exit below** is the line that ends the trade, **reduce at** is where you take money off, **trail stop to** is where the stop belongs now.

**What it is** — appears under the checklist **only if you have an open position in this stock** on the Portfolio page (and only once the live analysis has loaded). It shows the Position Guardian's live exit verdict for that position so that buy analysis and sell analysis sit on the same screen. The card title shows `guardian 14:32` — the time of the reading. If you hold the stock in more than one position, each gets its own block.

**What you see**

- A **verdict badge** whose colour follows severity: **red** for `EXIT STOP` (critical); **green** for `TRAIL EXIT`, `TARGET2 HIT`, `TARGET1 HIT` (action — something good happened, act on it) and for `HOLD` (ok); **amber** for `STOP TOUCHED`, `THESIS BROKEN` (warning) and `TIGHTEN STOP`, `TIME STOP` (advice).
- Next to it: `#12 · 500 sh @ 42.10` — the position number, shares held and your average entry.
- A small table:

| Row | Meaning |
|---|---|
| `Mark` | The price the position is valued at, with its source in brackets — e.g. `43.20 (yahoo quote)` or `43.20 (snapshot)` when the app fell back to the last nightly snapshot price. Marks are often a daily close, not a live quote. `—` if no price could be found. |
| `Stop` | Your current stop, as recorded on the Portfolio page. |
| `R now` | Your open profit in **R** — multiples of the risk you took at entry (entry minus your *initial* stop). `+1.50R` means you are up one and a half times your planned risk. Raising the stop later does not inflate this number. `n/a` if no stop was recorded. |
| `Peak R` | The best R the position has reached on a closing basis since entry. |
| `Unrealized` | Open profit or loss in percent. |
| `Suggested stop` | Only shown when the Guardian recommends a higher stop (`TIGHTEN STOP`). Also drawn on the chart in amber. |
| `Held` | `12 sessions` — trading days since entry. |

- **Reasons**: one grey sentence per finding with the exact numbers, e.g. `Reached +1.40R. Raise the stop from 40.35 to about 42.10 (high 45.10 minus 2.5xATR 1.20, floored at breakeven) — a winner must not be allowed to become a loser.`
- `Your note: …` — the entry note you typed when opening the position, in italics.
- A link `Manage on the portfolio page →`.

**The nine verdicts, most severe first** (the position gets the most severe one that applies; all reasons are listed):

| Verdict | When | What it tells you |
|---|---|---|
| `EXIT STOP` | Mark is at or below your stop. | `The plan you wrote at entry says exit — hoping is not a plan.` |
| `TRAIL EXIT` | After reaching at least 1R, price has given back more than 2.5 daily ranges (by default) from its post-entry high. | `The trailing exit says the move is over; take what is left.` |
| `TARGET2 HIT` | Mark at or above your target 2. | `Book the profit or trail a tight stop — do not let a completed trade turn into a new one.` |
| `TARGET1 HIT` | Mark at or above your target 1. | `Consider taking a partial and moving the stop to breakeven so the rest is a free trade.` |
| `STOP TOUCHED` | Today's low pierced the stop but the close recovered. | Check whether your broker filled a resting stop order; if not, decide now whether the level still holds. |
| `THESIS BROKEN` | The nightly signal turned to SELL, or the composite score fell 15 points or more (by default) since you bought. | `Re-read your entry note — if the setup is gone, so is the trade.` |
| `TIGHTEN STOP` | At least 1R reached and the trailing level (post-entry high minus 2.5 daily ranges by default, never below breakeven) is above your current stop and below the price. | Raise the stop to the `Suggested stop`. |
| `TIME STOP` | Held 15 sessions or more (by default), still within ±0.5R, and nothing else applies. | `Dead money has a cost: the capital could be in a setup that is actually moving.` |
| `HOLD` | Nothing above applies (or no price could be found — the reason says so). | `Stop intact, no target reached, thesis unchanged — nothing to do. Doing nothing is a decision too.` |

If the daily history could not be loaded, an extra reason says `Daily history unavailable (…) — trailing-stop and time-stop checks skipped.`

**What the buttons do** — `Manage on the portfolio page →` opens the Portfolio page, where you can raise the stop, record a partial sale or close the position. Nothing on this card changes your position; it only reports.

**How to benefit from it**

- **Look at this card before the `Trade plan`.** If you already hold the stock, the question is not "should I buy" but "should I still be holding" — and the Guardian answers it with your actual numbers, not the plan's theoretical ones.
- Act on `TIGHTEN STOP` the same day: go to the Portfolio page and set the stop to the suggested level. The chart shows the amber `suggested stop` line above your red `your stop` line — that gap is profit you are leaving exposed for no reason.
- `TARGET1 HIT` with `Peak R` well above `R now` means the stock already went further and came back — do not wait for `T2` on the full size; sell part and protect the rest.
- `THESIS BROKEN` plus a red `Chart patterns` or a `DISTRIBUTION` reading in `Smart Money` is a strong exit even if the stop is intact. The stop is the *last* line of defence, not the first.
- `STOP TOUCHED` on EGX often means the level was probed by a single trade. Confirm with your broker whether you were filled before deciding anything.
- Watch the `Mark` source: `(snapshot)` is the last nightly price, not today's. Before acting, check the live price with your broker — the app's data is delayed about 15 minutes at best.

---

### 4.11 Card — `Score`

**What it is** — the app's composite technical score for the stock out of 100, with a letter grade and a bar for each component that makes it up.

**What you see**

- While loading: a grey placeholder.
- A **big number** coloured **green at 70 or above**, **amber from 45 to 69**, **red below 45**, followed by `/ 100`, and often a teal **grade badge** (e.g. `A`, `B`).
- **Component bars**, one per sub-score (trend, momentum, volume, volatility and so on, named as the engine reports them). Each bar's fill is green when the component is at 66% or more of its scale, amber from 40%, red below, with the value printed on the right.
- Messages: `No score available.` when the engine returned nothing; `Analysis: …` when the whole analysis failed (the header price will also be `—`).

**What the buttons do** — a **`1D | 1W` toggle** in the card title. `1D` (the default) is the daily analysis — the decision timeframe. `1W` re-runs the *same* engine on weekly candles and re-renders **this card and the `Trade plan` card only**; both titles gain a `· weekly` tag, and the plan card adds a note that its levels are in weekly terms. The header price, the chart, the checklist, the levels, the patterns and your position stay daily — the weekly view is context, the daily view is the decision. Switch back to `1D` before you act.

**How to benefit from it**

- **Use `1W` to answer one question: is the larger trend intact?** A daily score of 67 with a weekly score of 55 and `Weak Setup` (a real CCAP reading) says the daily strength is a move inside a larger picture that has not confirmed yet. A daily score that *rises* when you switch to weekly is a stock where the big trend is doing the work — the kind you can hold through daily noise.
- **The bars matter more than the total.** A 72 built from strong trend and strong volume is a different animal from a 72 built on one extreme momentum reading. Read the bars to know what the score is made of, so you can disagree with it intelligently.
- A high score with a red *volume* bar is a rally without participation — the same warning the checklist's Volume pillar gives. A modest score with a green volume bar and a green trend bar on a stock sitting `AT SUPPORT` is often the better trade.
- The composite score is what the Guardian compares against later: if you buy at a score of 75 and the nightly snapshot score falls to 60 or below, `THESIS BROKEN` fires (a drop of 15 points by default). So the number you see today is your baseline — note it in the entry note when you open the position.
- Do not use the score as a ranking across stocks in isolation; that is what the Screener page's `Candidates` and `Setups` tabs do with more context. Here it is a health check for *this* name.
- Red total (below 45) plus `NO SETUP` in the checklist: close the page. There is nothing to wait for; move on.

---

### 4.12 Card — `Trade plan`

**What it is** — where analysis becomes an executable plan: entry, stop, two targets, the risk-to-reward ratio, a quality grade, the alternative scenario, and EGX-specific warnings about whether the plan is realistic. The levels are drawn on the chart as `entry`, `stop`, `T1`, `T2`. The card follows the `1D | 1W` toggle on the `Score` card: on `1W` the title reads `Trade plan · weekly`, the plan is computed on weekly candles (wider stop, further targets, slower) and a grey note below it reminds you that the stop belongs under a *weekly* level and the position must be sized on that stop. The `Position size` card and the checklist's levels-based plan are not affected by the toggle.

**What you see**

*Banners and warnings at the top (only when they apply):*

| Message | Colour | Meaning |
|---|---|---|
| `Plan inconsistent: entry 42.10 is at/below stop 43.00. Upstream data issue — do not trade these levels.` | Red error box | The feed produced a long plan whose stop is above its entry. Ignore the levels entirely. |
| `Reject: R:R to T2 1.63 < 2` | **Red banner** | The reward-to-risk ratio to the second target is below 2. The plan does not pay for its risk. (The test uses T2 because the engine's own quality grade is computed on T2 — T1 is deliberately the *nearest* level. If the plan has no T2 ratio, the T1 ratio is used, but the banner still reads `to T2`.) |
| `⚠ Stop is 23.4% below the current price — beyond one ±20% limit session; a limit-down open can gap through it with no fill. Size for gap risk, not just stop distance.` | Amber | EGX halts a stock at its daily band (by default ±20%). A stop farther than that can be jumped over in a single session. |
| `⚠ Target 1 is 24.1% above the current price — more than one ±20% limit session away; treat it as a multi-day swing target.` | Amber | Same idea for the targets (`Target 2` gets its own line). |
| `⚠ Your stop 40.50 sits just ABOVE a support tested 3x at 40.20 — the level will likely be probed before it holds. Put the stop below it (about 39.60).` | Amber | Built from the `Support & resistance` zones. The most common plan mistake. |
| `⚠ Target 1 (46.90) sits right at a resistance tested 2x at 47.00. Expect sellers there — consider taking profit a little before it (46.64).` | Amber | The second most common mistake. |
| `⚠ Illiquid: 20-day median traded value ~2,100,000 EGP (floor 5,000,000). Exit liquidity is the real risk — spreads and slippage will eat the plan's R:R.` | Amber | Median daily traded value is below the liquidity floor (by default 5,000,000 EGP). |

*The four levels*, as tiles: `Entry` (teal), `Stop` (red), `Target 1` and `Target 2` (green). `—` when a level is missing.

*Badges under the levels:*

| Badge | Meaning |
|---|---|
| `Pullback plan` / `Breakout plan` | Which scenario the four tiles belong to (the scenario name comes from the engine; pullback = buy the dip, breakout = buy strength through resistance). All four levels and the ratio belong to that one scenario. |
| `R:R T1 2.35 · T2 3.80` | Reward-to-risk to each target, measured from the Entry. **Green** when the grading ratio (T2, or T1 if no T2) is 2 or more, **red** below 2. |
| `Grade: …` | The engine's quality grade for the setup (for example `Grade: Good`). |
| A setup/strategy word (e.g. `long`, `swing`) | The plan's direction or style, when the engine names one. |

- **`Alt — breakout: entry 47.20 · stop 44.10 · T1 51.00 · R:R 1.23`** — a grey one-liner showing the *other* scenario's levels so you can compare both ways to trade the same stock.
- **Notes** — the engine's reasons for the plan, as a paragraph or up to eight bullets.
- **`Full plan payload`** — a fold with every underlying number.
- Messages: `No trade plan returned.`, `Trade plan: …` (error).

**What the buttons do** — click `Full plan payload` to unfold the raw plan. The card also **pre-fills the `Position size` card** with its Entry and Stop when those boxes are empty (the checklist may have got there first — see 4.9).

**How to benefit from it**

- **When you see the red `Reject` banner, skip the trade.** If every winner makes you twice what every loser costs, you can be wrong more often than right and still make money. Below 2R you need a high win rate just to break even — and nobody has a reliably high win rate. This one discipline separates profitable traders from the rest.
- Read the amber ⚠ lines as *edits to the plan*, not as reasons to abandon it: move the stop below the tested support it names (the message gives you the price), take profit slightly before the tested resistance, and if the stop is beyond one limit session, size smaller than the calculator says.
- The `Pullback plan` almost always has the better ratio because its entry is lower; the `Breakout plan` has the better *timing* because you only buy once the move has started. On EGX, where breakouts fail on quiet volume, prefer the pullback entry unless the checklist's Volume pillar is a ✓.
- The `Alt —` line is your patience check: if the breakout entry is well above today's price, you have time. Star the stock and wait for the pullback instead of chasing.
- Never take the plan's Entry as an order to buy *now*. Entry is a *level*; if the stock is far above it, the plan is telling you to wait. Compare with the current price in the header.
- Cross-check the Stop with the chart: it should sit *below* a dark-green `support xN` line, not on top of it. If the checklist's levels-based stop and this stop agree, you have a real level.

---

### 4.13 Card — `Support & resistance`

**What it is** — where the walls are. It finds price zones from four sources on the last year of daily candles, ranks them, says where the current price sits relative to them, and feeds the chart and the trade-plan warnings. The card title shows `daily · 2026-09-02`.

**What you see**

- While loading: `Finding levels…`.
- A **position badge**: `AT SUPPORT` (green), `BREAKING OUT` (green), `AT RESISTANCE` (red), `MID-RANGE` (amber). "At" a level means within one daily range (ATR) of a zone that was tested **two or more times**; round numbers, 52-week extremes and averages never count as the level you are "at".
- `room up 6.4% · room down 2.1%` — distance to the nearest meaningful resistance above and support below (round numbers excluded).
- A **note** sentence, one of: `Price is within +0.6 ATR of a resistance tested 3x at 47.00. Buying here means buying into sellers; wait for the break or the pullback.` / `Price sits on a support tested 2x at 40.20 (-0.4 ATR). The classic low-risk spot: a stop just below it keeps the risk small.` / `No tested resistance overhead within the last year — price is in open air.` / `Price is between support 40.20 (swings) and resistance 47.00 (52w high).`
- Two columns, up to four rows each, or `none within a year`:

| Column | Price colour | Row format |
|---|---|---|
| `Resistance above` | Red | `47.00   +11.6% · swings · tested 3x · 2026-07-14` |
| `Support below` | Green | `40.20   -4.5% · swings + round number · tested 2x · 2026-08-21` |

  The **source** is one of `swings` (a cluster of past swing highs/lows), `52w high`, `52w low`, `round number` (a psychological price near the current one), `SMA50` or `SMA200` (the 50- and 200-day averages, which move every day), or a combination like `swings + round number` when two sources coincide. `tested Nx` is the touch count — shown for swing zones and for the 52-week extremes (which count as one touch); round numbers and averages have none. The date is the last touch.
  A small grey **`W` badge** after the price marks a daily level that is *also* a weekly zone (hover it: `Also a weekly zone (tested 3x on the weekly chart)`). Those are the levels the larger trend respects — a stop under a `W` support is a stop under something real.
- Below the two daily columns, when the stock has them, two more: **`Weekly resistance`** and **`Weekly support`** — up to three rows each, `5.71   -4.8% · tested 3 weeks · 2026-08-21`. These come from the same daily candles resampled into Sunday–Thursday weeks (swing window 2 weeks, clustered within 0.75 weekly ATR), and only zones touched in two or more different weeks qualify. They are also drawn on the chart as `weekly support xN` / `weekly resistance xN` when no daily level already sits there.
- A grey footer: `Tested zones (2+ touches) are drawn on the chart; W marks a daily level that is also a weekly zone. Zones = clusters of swing highs/lows (window 3) within 0.75 ATR over the last year, strength = touches + recency + volume at the touches; plus 52-week extremes, round numbers near price, SMA50/SMA200. Weekly zones = the same on daily candles resampled to weeks (window 2); a daily level marked W sits on one.`
- Messages: `Levels unavailable: not enough daily history (need 60+ bars)`, `Levels unavailable: …`.

**What the buttons do** — none. The card silently redraws the chart's `support xN` / `resistance xN` lines when it loads.

**How to benefit from it**

- **`AT SUPPORT` is the low-risk spot**: a stop half a daily range below a zone tested 2+ times gives a small, well-defined loss if you are wrong. This is exactly how the checklist's levels-based plan is built. `AT RESISTANCE` is the opposite — buying here is buying into the people who sold there twice before. Wait for the break (with volume) or the pullback.
- `BREAKING OUT` (open air, no tested resistance within a year) is where the biggest moves happen — and also where you have no reference for a target. Use the `Trade plan` T1/T2 or a fib extension, and trail your stop instead of picking a number.
- **Touch count is strength.** A `tested 4x` zone with a recent last touch is a real wall; a `tested 2x` zone from ten months ago is a suggestion. The chart shows only the strongest few.
- **A `W` beats a plain daily zone.** When you have a choice of where to put a stop, put it under the support that also shows on the weekly chart: it was defended across several weeks, not several days, and the checklist's S/R pillar will say so (`The nearest support 5.74 is also a weekly zone (tested 3x on the weekly chart) — the larger trend respects it.`).
- Compare `room up` with `room down`: the checklist passes the S/R pillar when room up is at least twice room down and at least 5%. If you are `MID-RANGE` with roughly equal room both ways, there is no edge — do nothing.
- Round numbers (`45.00`, `50.00`) are anchors where Egyptian retail orders cluster; expect hesitation there but do not put a stop *exactly* on one — put it a little below.
- The 50- and 200-day averages are *dynamic* — the level printed today moves tomorrow. Use them as trend context (price above a rising SMA50 = healthy), not as precise entry prices.

---

### 4.14 Card — `Chart patterns`

**What it is** — every chart shape, price-action event and candlestick pattern the scanner currently sees on this stock's daily chart, with its trigger, target, stop hint, quality and whether it is still forming or already confirmed. The card title shows `daily · 2026-09-02`. The two strongest chart *shapes* are also drawn on the chart (blue `neckline` and `target` lines). This card loads only after the live analysis has answered.

**What you see**

- While loading: `Scanning…`. If nothing is found: `No chart shape, candlestick or price-action pattern on the daily chart right now.` On failure: `Patterns unavailable: …`.
- A grey **count line** that counts *events*, not rows — e.g. `2 bullish facts · 1 bearish event (seen 3 ways) · 7 rows`. One market event often arrives under several names: a failed upside break is reported as `False Breakout` *and* `Bull Trap` (and, if the poke was intrabar the day before, `Upthrust`); a rising swing structure as `Higher High / Higher Low` *and* `Break of Structure`; a held retest as `Throwback` *and* `Retest`. The scanner groups rows that describe the same candles (same direction, same target within a third of a daily range, broken within a session of each other, or a known synonym pair) into one **event**. `(seen 3 ways)` tells you three rows share one event — that is one piece of evidence, not three. **Never count rows.**
- A grey **decisive level** line, e.g. `Decisive level 5.91 (+0.2% away) — Break of Structure (BOS), Bull Trap, False Breakout. A close through it flips this line.` — the trigger nearest to the last close and every pattern that hangs on it. When bullish and bearish names share one level, the market has not decided yet; that level is what you watch.
- **Weekly rows.** Four patterns are computed on the daily candles resampled to weeks and appear with a `Weekly` prefix: `Weekly Higher High / Higher Low`, `Weekly Lower High / Lower Low`, `Weekly Break of Structure`, `Weekly Change of Character`. They describe the *larger* trend, always carry a `weeks`/`months` horizon, never cluster with their daily namesakes (a weekly and a daily structure are different facts even on the same day), and feed the checklist's **Trend** pillar rather than its Price-action pillar. No weekly row means the weekly swings are mixed — neither a clean uptrend nor a clean downtrend.
- A **compact list, one item per event, newest first** (then by quality), so a two-day trap is never buried under a three-month base. Each item begins with a **horizon** chip — `today`, `3 days`, `6 wk`, `3 mo` — how long the pattern has been building (since its first pivot). A `months` bullish base and a `days` bearish trap on the same stock are not contradicting each other; they answer different questions (*is the trend intact?* versus *is today an entry?*). **Only the first six events are shown**; a `Show all 8 events` button reveals the rest.
- Each item is a collapsed row you can click to expand. The **collapsed row** shows:

| Part | Example | Meaning |
|---|---|---|
| Horizon | `today`, `3 days`, `6 wk`, `3 mo` | How long the pattern has been building — since its first pivot. |
| Name | `Double bottom`, `Ascending Triangle ↑ broke up`, `Bullish Engulfing` | The pattern (the best-quality name for the event); trendline shapes add `↑ broke up` / `↓ broke down` once broken. |
| Direction badge | `bullish` (green) / `bearish` (red) / `neutral` (amber) | Which way the pattern points. |
| Status badge | `confirmed` (green) / `forming` (amber) | **Confirmed** = a daily close beyond the neckline/trigger within the last 15 sessions (for trendline shapes — triangles, wedges, channels — within the last 5). **Forming** = the shape is complete but the trigger has not been broken. A break older than that is stale and not shown; a classic reversal shape that fell back 2% through its neckline after confirming is dropped; a pattern whose target has already been reached is dropped. |
| `also: …` | `also: Upthrust, False Breakout` | The other names the scanner gave this same event. Their full rows are folded inside the item under *Same event, other names — same candles, same target; not extra evidence.* |
| Gist | `target 46.80 (+11.2%) · q 71` or `trigger 44.50 · q 58` | Target and distance to it when there is one, otherwise the trigger price; `q` is the **quality score 0–100**. |

- The **expanded body** shows:
  - A grey line: `reversal · reversal · reliability high · common · since 2026-05-24` — the category, kind, the date of the first pivot, and two qualitative tiers from the classic pattern references: **reliability** (`high` / `medium` / `low`) and **frequency** (`common` / `uncommon` / `rare`).
  - Rows (only those that apply): `Trigger / neckline` with `(+2.3% away)`; `Target` with `(+11.2%)`; `Stop hint` (the price beyond which the pattern is invalid — for the classic reversal shapes, half a daily range beyond the pattern's extreme; for trendline shapes, the opposite trendline); `Move done` `35.0%` (confirmed patterns only — how much of the measured move from neckline to target has already happened; 0 = at the neckline, 100 = at target); `Break` `2026-08-28 · volume 1.8× avg` (the break date and that day's volume versus the 20-day average); `Triggers` `above 43.10 / below 41.90` (candlesticks — the high and low that would confirm the candle either way); `Points` — the pivot dates and prices that make the shape (`low 1 40.10 (2026-06-12) · neck 44.50 (2026-07-03) · low 2 40.30 (2026-07-29)`).
  - A one-line description of the pattern.
- A grey footer: `Chart shapes are drawn on the chart (neckline + target). A finder, not a judge — the break with volume is the signal.`

**Quality score** — for the classic reversal shapes (double/triple bottoms and tops, head & shoulders, cup with handle): how clean the shape is (symmetry of the equal highs/lows), how big the move (depth in daily ranges), whether it is confirmed and on what volume (no credit below 0.8× average volume, full marks at 2× or more), and how recent the last pivot is. For confirmed shapes the score is *reduced* as `Move done` rises — a pattern that has travelled most of the way to its target is a finished trade, not a fresh signal. Trendline shapes, candlesticks and price-action events use their own simpler scoring (line fit, number of touches, size of the move).

**What the buttons do**

- **Click a row** to expand or collapse its details.
- **`Show all N`** — reveals the items beyond the first six and then disappears.

**How to benefit from it**
- **When bulls and bears are both `confirmed`, ask four questions — in this order.** `Confirmed` means *this pattern's own trigger has already been broken* (a past fact, dated under `Break`), not a forecast; a bullish target and a bearish target are the two edges of the map, never two votes. (1) **Where is price on the map?** Stack every trigger, neckline and level with price in the middle — those are the walls. (2) **Which patterns are still alive?** A bullish one is alive while price is *above* its neckline; a bearish one while price is *below* its trigger. Dead ones do not count whatever the badge says. (3) **Which horizon says whether, which says when?** The longest horizon (`months`, `weeks`, the checklist's `Weekly:`) gives the direction you would even consider; the shortest (`days`, `today`) gives the timing. A two-day bear inside a three-month bull means *wait*, not *sell*; a two-day bull inside a months-long downtrend means *a bounce, don't chase*. (4) **What are my two "if" sentences?** *If it closes above the nearest bear trigger → that bear dies, the bull targets are what's left, that is the entry and the bear trigger area is the stop. If it closes below the nearest bull neckline → that bull dies, stand aside. Between them → do nothing.* Bull targets are where you get paid; bear targets are where you bleed if you ignore the stop; the nearest wall between them is the only decision today. Example (CCAP, 2026-09-03, price 6.00): Upthrust alive below 6.12, BOS alive above 5.91, Double bottom alive above 5.78 — direction up (months + weeks), timing not yet (a 2-day bear at the ceiling); *above 6.16 → long, target 6.63, stop under 5.91; below 5.91 → out; 6.00 → wait* — which is exactly the checklist's `WATCHLIST`.

- **The shape is the setup; the break with volume is the signal.** A `forming` double bottom is a stock to star and watch, with the `Trigger / neckline` as your alert price. A `confirmed` one with `Break … volume 1.8× avg` and a low `Move done` is the actionable moment — you are early in the measured move with a clear `Stop hint`.
- **Volume on the break is the deciding number.** The quality score gives no credit for break volume below 0.8× the 20-day average and full credit only at 2× — so treat a `confirmed` break on below-average volume as unconfirmed. That is the classic EGX false breakout, and the checklist's Price action pillar will flag a false breakout or bull trap if it plays out.
- Use `Move done`: when most of the measured move is already done, the easy money is gone — do not buy; if you hold, tighten the stop toward the target. The quality score already penalises this, so a late pattern sinks down the list.
- Reliability tiers are Western textbook priors, not EGX statistics. The Screener page's `Scorecard` tab grades every confirmed pattern against what the stock actually did next — after a few months, trust those Egyptian numbers over the tier word.
- Bearish shapes on a stock you hold (`Head & shoulders` forming, `Double top` confirmed) are an exit warning even before the Guardian says anything. Check the `Stop hint` — it is where the pattern is invalidated.
- Candlesticks are the noisiest group; that is why they are listed last and a single candle rarely moves the checklist. Use them only at a level: a hammer *at* a tested support is meaningful; a hammer in the middle of nowhere is not.
- Compare the pattern `Target` with the `Trade plan` T1/T2 and the nearest `resistance xN`. When a measured-move target lands just under a tested resistance, take profit *before* the resistance, not at the target.

---

### 4.15 Card — `Position size`

**What it is** — the calculator that turns a stop distance into a share count. Four boxes and a button. In practical terms this is the most valuable feature on the page.

**What you see**

| Field | What goes in it |
|---|---|
| `Account (EGP)` | Your total trading capital. **Pre-filled from the app's settings file** — by default 100,000 — so a wrong account size never silently mis-sizes every trade. You can overtype it for a one-off, but set it properly in the settings file so every page uses the right number. |
| `Risk %` | The percentage of the account you are willing to lose on *this one trade* if the stop is hit. Pre-filled from the settings file — by default 1. |
| `Entry` | Your buy price. **Auto-filled** from the `Decision checklist` levels-based plan or the `Trade plan` (whichever loads first) when the box is empty. Overwrite it with your real intended price. |
| `Stop` | Your stop-loss price. Auto-filled the same way. Must be below Entry. |

After pressing the button:

| Result | Meaning |
|---|---|
| `Shares` | Exactly how many shares to buy so that a stop-out loses the risk amount. Rounded down to whole shares. If the shares would cost more than the account, the count is capped at what you can afford. |
| `Risk amount` | What you lose in EGP if the stop is hit (account × risk %). |
| `Position cost` | Total EGP the position ties up (shares × entry). |

Under the results an **amber note** strings together every relevant sentence:

| Sentence | When |
|---|---|
| `Risking 1,000 EGP (1.00% of 100,000) at 1.75 EGP/share risk.` | Always. |
| `A 2R target sits at 45.60.` | Always — the price where the reward is twice the risk. |
| `Estimated round-trip fees ~106 EGP (0.25%/side) — a stop-out costs risk + fees.` | Always. Fees are per side and configurable in the settings file (by default 0.25% each way). |
| `Size capped by available capital, so realized risk is below target.` | Your account cannot afford the full risk-based share count (very tight stop or expensive stock). |
| `WARNING: risk_pct 3.00% exceeds the 2% cap guideline.` | You typed a risk above 2%. |
| `Risk budget too small for even 1 share at this stop distance.` | The stop is so far away that one share already risks more than your budget. |
| `LIQUIDITY WARNING: this position is ~22% of COMI's 20-day median daily value (4,500,000 EGP) — entering and exiting will move the price; cap at ~15%.` | Your position would be more than 15% of a normal day's traded value in this stock. |
| `Position is ~3.2% of COMI's 20-day median daily value (31,000,000 EGP).` | Otherwise — a comfortable size relative to daily turnover. |
| `Liquidity unknown for COMI (snapshots history too thin to compute 20-day traded value).` | The app has fewer than five nightly snapshots for this stock yet, so it cannot judge liquidity — "unknown" is not "illiquid". |

**What the buttons do**

- **`Size position`** — validates the four boxes and computes. Errors you may see: `Fill account, risk %, entry and stop first.` (a box is empty or not a number), `Sizing failed: stop must be below entry for a long position`, `Sizing failed: account must be > 0`, `Sizing failed: entry must be > 0`, `Sizing failed: risk_pct must be > 0`, `Sizing failed: stop cannot be negative`. While computing you see `Sizing…` and the button is disabled.

**How to benefit from it**

- **Most traders do not blow up by picking bad stocks; they blow up by betting too much on one.** At 1% risk, ten losses in a row cost about 10% of the account — survivable. At 10% risk the same streak ends you. This calculator makes correct sizing take three seconds, so there is no excuse to guess.
- **Always size from the stop you will actually use**, after applying the `Trade plan` ⚠ corrections (stop below the tested support, not above it). A stop 1% lower means fewer shares — that is the point, not a problem.
- The `2R target` sentence is your minimum acceptable target. If the `Trade plan` T1 or the nearest `resistance xN` is *below* that price, the trade is a `Reject` no matter what the banner says.
- Fees are real on EGX: a stop-out costs the risk amount *plus* the round-trip fees (two sides at 0.25% each by default). On small accounts with tight stops, fees are a meaningful share of the risk — the note shows you the number so you can decide whether the trade is worth it at all.
- Take the `LIQUIDITY WARNING` seriously. On EGX, exit liquidity is the real risk: a position that is 20% of a day's turnover cannot be stopped out anywhere near the planned level. Cap yourself at the ~15% the note suggests, even if that means risking less than 1%.
- Before you open the position on the Portfolio page, remember the portfolio's own limit: total open risk across all positions is capped at 6% of the account (a fixed "open heat" rule on the Portfolio page, which can only be exceeded with an explicit override). Sizing one trade correctly at 1% does not help if you already have six others open.
- Common mistake: increasing `Risk %` to "make the position worth it" when the share count looks small. A small share count is the calculator telling you the stop is too far away for this stock at your account size — pick a closer, real level or skip the trade.

---

## 5. Page 3 — Screener

**This is your stock-hunting page** — how you *find* opportunities instead of waiting to hear about them. Open it from the sidebar link **⌗ Screener**.

Everything on this page is analysis on delayed data (about 15 minutes for live quotes; the Leaders, Setups and Patterns tabs work from daily closing candles). The app never places an order. It gives you a shortlist and a reason; the decision is yours. The footer on every page says the same thing: *Analysis tooling — not financial advice. Data delayed ~15 min.*

The page is organised as six tabs along the top. Each tab is described below in the order it appears on screen.

### 5.1 Tab strip — `Scanner` · `Candidates` · `Setups` · `Leaders` · `Patterns` · `Scorecard`

**What it is** — A row of six buttons that switches the whole page between six different tools. The active tab is highlighted; only one is shown at a time.

**What you see**

| Tab | The question it answers |
|---|---|
| `Scanner` | "Show me every stock that meets *this one* condition right now." |
| `Candidates` | "Which stocks are flagged by *several* scanners at once?" |
| `Setups` | "Which stocks pass the six-pillar decision checklist *today*?" |
| `Leaders` | "Which stocks are actually stronger than EGX30?" |
| `Patterns` | "Which stocks are drawing a classic chart pattern right now?" |
| `Scorecard` | "Which of these scanners actually work on EGX?" |

**What the buttons do** — Click a tab to show it. The `Scanner` tab is open when the page loads. The tabs behave differently the first time you open them:
- `Candidates` runs the four scanners **live** the first time you open it (it takes up to a minute) and then keeps that list until you press `Refresh` or reload the page.
- `Setups`, `Leaders` and `Patterns` load their **stored** result from the last post-close run the first time you open them and then keep it — switching away and back is instant.
- `Scorecard` re-reads its table every time you open it.

The Dashboard can also open this page straight onto the `Setups`, `Patterns` or `Leaders` tab when you click the `all →`, `all patterns →` or `leaders →` links on its cards. The page also accepts a direct address for each of those tabs and for `Scorecard`: adding `?tab=setups`, `?tab=patterns`, `?tab=leaders` or `?tab=scorecard` to the end of the Screener's address (for example `http://127.0.0.1:8642/screener.html?tab=scorecard`) opens it on that tab. No button on any page links to the Scorecard address — it exists so you can bookmark the tab you use most and land on it without a click.

**How to benefit from it**
- Use the tabs as a funnel, left to right in *reverse*: start with `Leaders` (which stocks have the wind behind them), check `Candidates` (which of those have fresh evidence today), then let `Setups` tell you whether the trade actually has a plan, and finally open the Stock page for the chart and levels.
- `Scorecard` is your monthly read, not your daily one — it tells you which of the scanners deserve your attention and which are producing noise.
- Do not treat any single tab as a buy list. A stock on one tab is a lead; a stock on three tabs is a lead worth an hour of your time.
- Because `Setups`, `Leaders` and `Patterns` open the stored post-close run, what you see before the open is yesterday's picture. That is exactly what you want for planning orders; press the tab's refresh button only if you need today's session included.

### 5.2 Panel — `Run a scanner`

**What it is** — Pick one of six hunting tools, adjust its settings if you want, and run it against the whole Egyptian market. This is the manual, one-condition-at-a-time screen.

**What you see**

- A line under the heading shows the selected scanner's description (it reads `Loading scanners…` for a second when the page opens). If the list cannot be fetched you see a red box: `Could not load scanner list: …`. If the app returns an empty list you see a red box beginning `No scanners returned by` (followed by a technical address) — restart the app if you ever see it.
- The **`Scanner`** dropdown. Each entry shows the scanner name followed by its short key in brackets, for example `Bollinger Squeeze (squeeze)`.
- One input box per parameter, labelled with the parameter's name in plain words (`bbw max`, `volume multiplier`, and so on). Numbers get a number box, text gets a text box, and each box is pre-filled with the default.
- The **`Run scanner`** button.

The six scanners, their parameters and their defaults:

| Scanner (key) | What it hunts for | Parameters (default) | When to use it |
|---|---|---|---|
| **Bollinger Squeeze** (`squeeze`) | Stocks whose Bollinger Band width has compressed below `bbw max` — low-volatility coils that often precede a big expansion move | `timeframe` (1D), `limit` (50), `bbw max` (0.04) | **Before** a move. Volatility contracts, then expands — this is the most "early" of the scans. It tells you *where* energy is stored, not *which way* it will go |
| **Volume Breakout** (`volume_breakout`) | A volume surge (`volume multiplier` × the 20-bar average) happening on the same bar as a price move of at least `price change min` percent | `timeframe` (1D), `volume multiplier` (2.0), `price change min` (3.0), `limit` (25) | **As** a move begins. Volume is what separates a real breakout from a fake one. Each row carries a breakout type — bullish or bearish — so read it before assuming it is a buy |
| **Smart Volume** (`smart_volume`) | Volume breakouts filtered by RSI regime — `rsi range` can be `oversold`, `overbought`, `neutral` or `any` — with a trading recommendation attached to each hit | `min volume ratio` (2.0), `min price change` (2.0), `rsi range` (any), `limit` (20) | When you want breakouts that are not already exhausted. Set `rsi range` to `neutral` or `oversold` to avoid buying the top of a spike |
| **Momentum Candles** (`momentum`) | A strong directional candle today (dominant body, trend alignment, healthy RSI), then **verified against real daily history**: only stocks with `candle count` consecutive closes in the pattern direction survive | `timeframe` (1D), `pattern type` (bullish), `candle count` (3), `min growth` (1.0), `limit` (25) | To ride an established push rather than anticipate one. Rows that passed the history check are tagged as verified; rows that failed it are dropped. History is checked for up to 15 rows per run — beyond that, rows are kept but marked unverified. The check only runs on the 1D timeframe with a `candle count` of 2 or more |
| **Smart Money Flow** (`smart_money`) | Members of an index (`index`, e.g. EGX30) ranked by evidence of institutional accumulation — a volume-flow composite, a banker-style read and an oscillator — over `period` | `index` (EGX30), `limit` (10), `period` (6mo), `min score` (0.0) | To find quiet accumulation before the crowd notices. Its score runs on a 0–100 scale; the Candidates tab uses 58 as its "accumulation" cut-off, so consider typing 58 into `min score` here too |
| **EGX Stock Screen** (`custom`) | The full EGX ranking engine: stock score, grade, trade setups and quality. Rows are tagged with a `bucket` of `qualified` (passed the setup rules) or `watchlist` (close but not yet) | `timeframe` (1D), `min score` (55), `index filter` (empty = whole market), `limit` (20) | Your general-purpose "show me the best-rated stocks" tool. Put `EGX30` in `index filter` to stay in the big, liquid names |

**What the buttons do**
- **`Scanner` dropdown** — choosing a scanner rewrites the description line and rebuilds the parameter boxes with that scanner's defaults.
- **Parameter boxes** — type over a default to change it for this run only. Clear a box to use the default. If you type something the scanner cannot read, the app falls back to the default silently.
- **`Run scanner`** — runs the scan and fills the `Results` panel below. The button greys out while running and the Results panel shows `Running "Bollinger Squeeze"…` (with the scanner's name). When it finishes a green toast says `Scanner "…" returned N rows`. If nothing is selected you get a red toast `No scanner selected`. If the run fails you see `Scanner failed: …` both in the panel and as a toast. In the panel the technical reason is translated into one of three friendly sentences worth knowing: `TradingView is pausing this app for a minute or two (rate limit). Try again shortly — stored results and Yahoo-based tabs (Leaders, Patterns) still work.`, `Yahoo is rate-limiting requests for a short while. Try again in a minute.` and `The app's server is not responding. Is it running?` (hover the red box to read the raw reason; the toast shows the raw reason directly).

**How to benefit from it**
- **Match the scanner to where you are in the move.** Squeeze finds stocks *before* they move (a watchlist builder). Volume Breakout and Momentum find stocks *as* they move (entry candidates). Smart Money finds stocks that *may* move because somebody big is quietly buying (research leads). Do not buy off a squeeze alone — a coil can release downward.
- **Tighten, do not loosen.** The defaults are already generous. If a scan returns 40 rows, raise `volume multiplier` or `min score`, or lower `limit`, until you have five to ten names you could actually study. A screener that returns half the market has told you nothing.
- **Run Volume Breakout later in the session, not in the first minutes after 10:00.** Early on, a single block trade can trip the volume condition on a stock that then does nothing all day. By midday the volume ratio means something.
- **Cross-check a scanner hit before acting**: click the row to open the Stock page and look at the Decision checklist and the levels. A breakout into overhead resistance with a 1R target is a scanner hit, not a trade.
- Common mistake: running Momentum with `pattern type` = bullish after three up days and buying the fourth. Three consecutive up closes is often where the *first* pullback starts. Use Momentum to build the list, then wait for the pullback the `Patterns` tab flags.
- If a scan returns nothing, that is information. On a quiet or falling day the market simply has no setups — staying in cash is a decision too.

### 5.3 Panel — `Results`

**What it is** — A sortable table of everything the last scan found, with a one-line summary above it.

**What you see**
- Before the first run: `Pick a scanner and press Run. Click a column header to sort; click a row to open the stock page.`
- After a run, a summary line: `Scanner: <name> · rows: <N> · as of <time>`.
- A table whose columns depend on the scanner, because each scanner reports different things. Column headers are the scanner's own field names written with spaces and capital initials (for example `Breakout Type`, `Change Percent`); the app pins a fixed set of well-known columns to the front in this order — symbol, ticker, name, strategy, price, close, last, entry, stop, target 1, target 2, exit price, qty, change percent, change, signal, score, rating, hit count, family count, volume, RSI, band width (BBW), PnL, PnL percent, R multiple — whichever of them the scanner reports, and only the remaining scanner-specific columns are sorted alphabetically after them. So on the Squeeze scanner the volume, RSI and band-width columns come before, not among, the alphabetical tail. The most useful columns are always there in some form: the symbol, the last price, the day's change, and the scanner's own measurements (band width for Squeeze, volume ratio and breakout type for Volume Breakout, RSI and recommendation for Smart Volume, the verified flag for Momentum, the composite score for Smart Money, score / grade / bucket for the EGX Stock Screen). The table shows at most 12 columns.
- A cell that holds a whole group of values (for example the indicator block on the Squeeze and Volume scanners) shows a shortened text; hover it to read everything.
- Numbers are right-aligned. Columns whose name marks them as a percentage change are shown green when positive and red when negative; yes/no flags read `yes` / `no`; empty cells show `—`.
- If the scan returns no rows the table reads `No rows`, and an expandable `Raw response` block appears below it so you can see the scanner's own notes (for example a note that a batched scan aborted early but salvaged some rows — the summary line still counts the salvaged rows).

**What the buttons do**
- **Click a column header** to sort by that column; click again to reverse. A small teal ▲ or ▼ after the header marks the active sort. Empty cells always sort to the bottom.
- **Click any row** to open that stock's Stock page in the same window.
- **`Raw response`** (only when there are no rows) expands the complete unfiltered answer.

**How to benefit from it**
- **Sort is your second filter.** Run Squeeze, then sort by volume or by day change: now you are seeing coiled stocks that people are *already* starting to trade. Combining two conditions this way is where a screener earns its keep.
- **Sort Volume Breakout by breakout type** so the bearish rows sit together — those are stocks to avoid or to protect a position in, not to buy.
- **Sort the EGX Stock Screen by bucket** and study the `qualified` rows first; the `watchlist` rows are tomorrow's candidates if they hold up.
- **Look at the `as of` time.** During the session (Sunday–Thursday, 10:00–14:30 Cairo) a scan from 10:20 is stale by 13:00. Re-run before you act.
- Do not act from this table alone. It has no stop, no target and no liquidity check. Those live on the Stock page and the `Setups` tab.

### 5.4 Tab — `Candidates — merged multi-scanner ranking`

**What it is** — The app's flagship screen: four scanners are run together with fixed settings (Bollinger Squeeze, Volume Breakout, Smart Money Flow and Momentum Candles), their hits are merged by stock, and the merged list is ranked so that stocks flagged by *several independent* methods rise to the top. The Dashboard shows the stored copy of this list from the last post-close run; this tab computes a fresh one live every time it loads.

**What you see**
- While loading: `Merging scanners — this can take a minute…`.
- A header line: `N candidates · as of <time>` and a `Refresh` button.
- A table with one row per stock. Columns, in screen order:

| Column | Meaning |
|---|---|
| `Symbol` | The ticker. Click the row to open it |
| `Price` / `Change Pct` | Last price and the day's move (from the scanner that found it, or from the deeper analysis for the top 15). The change is green when positive, red when negative |
| `Signal` · `Score` · `Rating` | The buy/sell reading, the overall technical score and the overall rating from the per-stock analysis — filled for the top 15 merged names only, `—` for the rest |
| `Hit Count` | How many scanners flagged it (raw count) |
| `Family Count` | How many *independent kinds* of evidence flagged it. The scanners belong to three families: **coil** (Squeeze), **thrust** (Volume Breakout and Momentum — they measure the *same* big up-day, so together they count once) and **flow** (Smart Money). Maximum 3 |
| `Evidence Weight` | The family count, but with each family weighted by the best track record its scanner has earned on the `Scorecard`. Until a scanner has 20 graded hits its weight is 1.0, so at first this equals the family count |
| `Grade` | The letter grade from the per-stock analysis (top 15 only) |
| `Liquidity Egp` | The typical (median) money traded per day, in EGP, from the app's own stored end-of-day snapshots of the last 20 sessions. `—` until the app has stored at least 5 sessions for that stock — "unknown" is never treated as "illiquid" |
| `Scanners` | A small badge for **each scanner that flagged it** (for example `squeeze`, `smart_money`). Shows `—` if empty |

- If the whole run fails: `Candidates failed: …` in the panel and as a red toast. If only *one* of the four scanners fails (typically a TradingView pause), the list is still built from the other three — a suspiciously short list during a pause is usually that, not a quiet market.

**What the buttons do**
- **`Refresh`** — re-runs all four scanners live and rebuilds the list (up to a minute).
- **Click a row** to open the Stock page.
- **Click a column header** to sort.

The settings the four scanners run with here are fixed and differ from the manual defaults in 5.2: Squeeze uses `bbw max` 0.04 with up to 40 rows; Volume Breakout is looser (1.8× volume and a 2.0% move, up to 25 rows); Smart Money is stricter (EGX30 members with a score of 58 or more, up to 15 rows); Momentum looks for 3 consecutive bullish candles with 1.0 minimum growth, up to 25 rows.

How the ranking works (so you can read the order): stocks are sorted first by `Evidence Weight`, then by `Family Count`, then by `Hit Count`, then by `Score`, then by the day's change. Two rules clean the list: Volume Breakout hits marked *bearish* are dropped before merging (this is a **bullish** shortlist — a −4% distribution day should not count as confirmation), and stocks whose known 20-day median traded value is below the liquidity floor (by default 5,000,000 EGP per day, configurable) are filtered out. Stocks whose liquidity is not yet known are kept and shown with `—` in the liquidity column. Only the top 15 names after a first pass (by family count, then day change) receive the deeper per-stock analysis that fills `Score`, `Grade`, `Signal` and `Rating`.

**How to benefit from it**
- **One scanner finding a stock is a coincidence. Three families finding the same stock is a pattern.** A stock that is coiled (Squeeze), has smart-money accumulation (Flow) *and* just thrust up on volume (Thrust) is showing you the entire life-cycle of a move in one row. Spend your research time on `Family Count` = 3 and 2, and largely ignore 1.
- **Read `Family Count`, not `Hit Count`.** A stock with Volume Breakout *and* Momentum has a hit count of 2 but a family count of 1 — it is one big green candle described twice. The app already knows this; make sure you do too.
- **Watch the `Evidence Weight` drift away from `Family Count` over the months.** When a family's weight rises above 1.0 the Scorecard has proven that scanner beats the index; when it falls below, the scanner has been losing. A stock ranked top on evidence weight but only second on family count is being promoted by a scanner that has *earned* it.
- **Use the `—` cells in `Score` as a boundary.** Only the top 15 merged names are given a full score and grade. If the stock you like is below that line, it did not have enough independent evidence to be worth the deeper pass — treat it as a watchlist name.
- **Hand every candidate to the `Setups` tab before buying.** Candidates says *why the stock is interesting*; Setups says *whether there is a trade in it* (trend, level, volume, plan). Many candidates are interesting and un-tradeable at the same time.
- Common mistake: refreshing this tab every ten minutes during the session and chasing whatever moved to the top. The list is built from daily conditions; intraday churn is noise. Check it once before the open (the Dashboard's stored copy from yesterday's close) and once around midday.
- If the list is short or empty (`0 candidates`), the market has no multi-scanner agreement today. That is a legitimate "stay in cash" reading, not a bug.

### 5.5 Tab — `Best setups — the six-pillar checklist across today's candidates`

**What it is** — The Stock page's Decision checklist answers "is *this* stock a setup?". This tab answers the question you actually start the day with: **which stocks are?** After every close the checklist runs over every stock the app already has a reason to look at — the latest stored Candidates (top 40), the stored EGX100 Leaders ranking (top 25), your watchlist and your open positions — up to 80 stocks in the post-close run, and the results are stored so the tab opens instantly.

**What you see**
- The description under the heading: *Every stock the app already has a reason to look at (Candidates, Leaders, your watchlist, your holdings) is scored on Trend, Support/Resistance, Volume, Price action, Patterns and Risk plan. **SETUP** = 5-6 ticks and nothing against it. **WATCH** = worth following, something unclear. **NO SETUP** = the trend or the risk plan is against it. Runs after each close.*
- While loading: `Loading stored checklist run…`.
- A header line: `N stocks scored · X setups · Y watch · Z no setup · checklist of <date> · stored by the post-close job` (or `· run just now` after you press Run now), and the `Run now (≈1 min)` button.
- If nothing is stored yet: `No checklist run stored yet. The post-close job builds it every trading day at 15:00, or press Run now.`
- A table (up to 120 rows), sorted SETUP first, then WATCH, then NO SETUP, and by score within each group:

| Column | Meaning |
|---|---|
| `Symbol` | The ticker, in bold |
| `Verdict` | A badge: **SETUP** (green), **WATCH** (amber), **NO SETUP** (red) |
| `Score` | Pillars passed, shown as `n/6` |
| `Trend` · `S/R` · `Volume` · `Price action` · `Patterns` · `Risk plan` | One badge per pillar: ✓ (green, pass), ⚠ (amber, warning), ✗ (red, fail). **Hover** to read the one-sentence evidence behind it, e.g. "Trend — Price 45.20 above the 50-day average (42.10) and the 20-day is above the 50-day, 50-day rising." |
| `Last` | Last daily close |
| `Plan R` | The reward-to-risk of the levels-based plan, e.g. `2.4R`; `—` if no valid stop could be built |
| `Verdict in words` | The headline sentence, e.g. "Setup: 5 of 6 pillars in favour, only volume unclear." or "Not a setup: 2 pillars against it — trend, risk plan." |
| `Why on the list` | The sources that put the stock here: `candidates`, `leaders`, `watchlist`, `held` (and `manual` for stocks added by hand) |

- Under the table, after a live `Run now`, a basis line: *Six-pillar checklist (trend, support/resistance, volume, price action, patterns, risk plan) on Yahoo daily closes, run over the latest Candidates, the Leaders ranking, your watchlist and your open positions. SETUP = 5-6 pillars and nothing against it.* (the stored view omits it). The expandable `Full setups payload` is always there.
- Errors show as `Setups failed: …` or `Run failed: …`.

What each pillar checks (all from daily closing candles, so a stock needs at least 120 days of history — stocks with less are skipped):

| Pillar | Pass | Warning | Fail |
|---|---|---|---|
| **Trend** | Price above the 50-day average and the 20-day above the 50-day (ideally with higher highs and higher lows in the swings) and the weekly trend agrees | Mixed averages, an uptrend whose recent swings are already making lower highs and lower lows ("the trend is tiring"), or a daily uptrend inside a weekly downtrend (a counter-trend bounce) | Price below the 50-day and the 20-day below the 50-day — a downtrend |
| **S/R** | Price sitting at a tested support, or breaking out over resistance, or mid-range with at least twice as much room up as down and at least 5% up | Mid-range with no edge, or levels unavailable | Price sitting at resistance |
| **Volume** | At least 55% of the last 20 sessions' volume traded on up days and this week (last 5 sessions) runs at or above the 20-day average | Quiet (this week under 0.7× the average — "breakouts on quiet volume tend to fail"), or no clear message | 40% or less of volume on up days while activity is 1.1× normal or more — heavy selling |
| **Price action** | Recent confirmed bullish events (price-action events and candlestick patterns) outnumber bearish ones — one event counted once, however many names it carries | No decisive event | A red-flag reversal on the tape (bull trap, false breakout, change of character, failed retest, upthrust), or bearish events outnumber bullish |
| **Patterns** | A confirmed bullish chart shape (with its target and how much of the move is already done) | A bullish or bearish shape still forming, or no pattern at all | A confirmed bearish shape and no bullish one |
| **Risk plan** | Stop under the nearest support, first target at the nearest resistance, and the reward covers the risk at least twice with the stop 10% away or less | Under 2R ("acceptable only with a strong trend"), or the stop is more than 10% away ("one limit-down session could gap through it") | Less than 1R of room to the first resistance, or the stock is illiquid (median daily value under the floor, by default 5,000,000 EGP) |

How the plan is built: the stop goes half an average daily range (14-day) under the nearest support (or two ranges under the price when there is no support), and is never tighter than three-quarters of a range; the first target is the nearest resistance, or — when the nearest resistance is too close to matter — three times the risk above the entry. The Risk plan pillar also tells you the position size: the number of shares you could buy risking your configured percentage of your account (by default 1% of 100,000 EGP) between entry and stop, and roughly how many EGP that is.

How the verdict is decided: **NO SETUP** if Trend or Risk plan fails, or if two or more pillars fail. **SETUP** if at least 5 pillars pass and nothing fails. **WATCH** if 3–4 pass and nothing fails, or if exactly one non-critical pillar fails but at least 3 pass. Anything else is NO SETUP.

**What the buttons do**
- **`Run now (≈1 min)`** — re-scores every candidate, leader, watchlist and held stock live (up to 100 stocks, against 80 in the scheduled run). The panel shows `Scoring every candidate, leader, watchlist and held stock on six pillars — about a minute…` and finishes with a toast `Checklist run: N setups found`. The result is stored and replaces today's post-close run.
- **Hover a pillar badge** to read its evidence sentence.
- **Click a row** to open the Stock page, where the full Decision checklist and the chart with levels live.
- **Click a column header** to sort (for example by `Plan R` to see the best reward-to-risk first).

**How to benefit from it**
- **Shop only from the SETUP rows, and from WATCH rows whose one missing pillar you can see resolving.** A WATCH with only `Volume` unclear becomes a SETUP the day volume arrives — that is a stock to have an alert on, not to buy today. Ignore NO SETUP entirely; the point of the checklist is to stop you buying stocks with two crosses, not to bless the ones with six ticks.
- **Read `Plan R` before the verdict.** A SETUP can carry a ⚠ on `Risk plan` — that means its R is under 2 (or its stop is more than 10% away) and the other five pillars carried it; a SETUP with `Risk plan` ✓ is where the checklist says the reward pays for the risk twice over. Two SETUPs with the same score — take the one with the higher R and the tighter stop percentage (hover `Risk plan` to see it).
- **Your held stocks are scored too** (`Why on the list` = `held`). A position that drops to NO SETUP with `Trend` failing is telling you the reason you bought is gone. That is the moment to tighten the stop or exit — do not wait for the stop to do it for you.
- **Run now after the 14:30 close** if you want to prepare tomorrow's orders in the afternoon before the 15:00 job has finished. Otherwise the stored run is ready when you open the app the next morning.
- **Combine with `Leaders`**: a SETUP whose source is `leaders` *and* `candidates` is a strong stock with fresh evidence and a valid plan — the best combination this page produces.
- Common mistake: sorting by `Score` and buying every high score. The ticks describe the past; the `Plan R` column describes your trade. A stock with five ticks and a `Plan R` of 1.5R is a SETUP with a warning, not a clean one — and under 1R the Risk pillar fails outright and the verdict becomes NO SETUP, however good the other five look.

### 5.6 Tab — `Leaders — relative strength vs EGX30`

**What it is** — The stocks that are actually stronger than the market: beating EGX30 over one, three and six months, still near their 52-week high, above their 50-day average and liquid enough to exit. This is the classic swing-trade pool. It is computed after each close from daily candles and stored, so it opens instantly.

**What you see**
- The description under the heading: *Stocks beating the index over 1, 3 and 6 months, still near their 52-week high, above the 50-day average and liquid enough to exit. Computed after each close from Yahoo daily candles; **Refresh** recomputes now (about a minute).*
- While loading: `Loading stored ranking…`.
- A header row with a **`Universe`** dropdown (`EGX30`, `EGX70`, `EGX100` — default EGX100), an info line `N leaders · ranking of <date> · M ranked · stored by the post-close job`, and a `Refresh (≈1 min)` button. After a live Refresh the info line instead ends `· benchmark: <source> · recomputed just now`.
- If nothing is stored: `No ranking stored yet. The post-close job builds it every trading day at 15:00, or press Refresh to compute it now.`
- A table of the top 40, ranked:

| Column | Meaning |
|---|---|
| `#` | Rank, 1 = strongest |
| `Symbol` | The ticker |
| `Price` | Last daily close |
| `RS score` | 0–100. The percentile rank of the stock's *excess* return over EGX30 across 1m / 3m / 6m, weighted 30 / 40 / 30 (the 3-month window counts most, as in classic relative-strength ranks). 100 = stronger than every other stock in the universe; 90 = stronger than 90% of it |
| `1m %` / `3m %` / `6m %` | The stock's own return over 21 / 63 / 126 sessions, green when positive, red when negative |
| `vs EGX30 3m` | The stock's 3-month return minus the index's 3-month return |
| `From 52w high` | How far below the 52-week high (0% = at the high; −12% = twelve percent below it) |
| `New high` | `yes` (green) when within 2% of the 52-week high, otherwise `no` (amber) |
| `> SMA50` | `yes` (green) when trading above its 50-day average, otherwise `no` (amber); `—` when there is not enough history |
| `Median value 20d (EGP)` | Typical money traded per day over the last 20 sessions. Stocks known to be below the liquidity floor (by default 5,000,000 EGP) are removed from the ranking |

- After a live Refresh, a basis line appears under the table: *Returns from Yahoo daily closes (delayed, not dividend-adjusted). RS score = percentile rank of excess return vs EGX30 over 1m/3m/6m, weighted 30/40/30. New high = within 2% of the 52-week high.* The expandable `Full leaders payload` is always there.
- Errors show as `Leaders failed: …` or `Refresh failed: …`.

**How the EGX30 benchmark is built.** The app first tries the index's own daily history. That history often carries only a handful of bars, so when it has fewer than 200 bars the app builds an **equal-weight proxy**: it chains the daily returns of the EGX30 members, and a day only counts when enough members reported (so one thin name cannot drive the "index" that day). After a Refresh the header tells you which was used — `benchmark: ^CASE30 (Yahoo)` or `benchmark: equal-weight EGX30 proxy (Yahoo constituents)`. The Scorecard uses the same benchmark.

**What the buttons do**
- **`Universe` dropdown** — switch between EGX30, EGX70 and EGX100. Each universe has its own stored ranking; changing it reloads. (The post-close job only stores EGX100; EGX30 and EGX70 have a stored ranking once you have pressed Refresh on them.)
- **`Refresh (≈1 min)`** — recomputes the ranking now from daily history for the selected universe. The panel shows `Recomputing relative strength for EGX100 from Yahoo history — about a minute…` (with the chosen universe) and finishes with a toast `Leaders recomputed: N ranked, M illiquid filtered`. The result is stored.
- **Click a row** to open the Stock page. **Click a column header** to sort — for example by `From 52w high` to find leaders that have pulled back.

**How to benefit from it**
- **Buy strength, not weakness.** The single most reliable habit in swing trading is to shop from the top of a relative-strength list. A stock that has beaten the index for six months is being accumulated by someone with more information than you. Weakness relative to the index — the bottom of this list, or names that fall off it — is the classic thing to avoid and the classic thing to sell.
- **A high `RS score` with `New high` = yes and `> SMA50` = yes** is the textbook leader. The best entries in these stocks are usually *not* at the high — they are on the first orderly dip toward the 20-day average, which is exactly what the `Pullback` event on the `Patterns` tab flags (2–5 down sessions into the 20-day average in an uptrend). Put the top ten here on your watchlist and wait for that.
- **Read `From 52w high` together with `RS score`.** A high RS score with the price well below its high means the stock led *earlier* and is now correcting — a WATCH, not a buy. A high RS score within 2% of its high (`New high` = yes) is a stock in motion.
- **Compare the three windows.** `1m %` far above `6m %` means the strength is *new* (a fresh leader — good early, risky late). `6m %` strong but `1m %` negative means the leader is resting or rolling over — check `Trend` on the `Setups` tab.
- **Check the benchmark line once after a Refresh.** If it reads *equal-weight proxy*, the "vs EGX30" numbers compare against an average EGX30 member, not the capitalisation-weighted index you see on TV. The ranking is still valid; just do not quote the excess to the decimal.
- **The liquidity filter protects you.** A stock that has doubled on tiny daily turnover is not a leader you can trade — you would move the price on your own exit. That is why such names are removed, and why you should not override it mentally.
- Common mistake: buying rank #1 because it is #1. Rank is a filter, not a signal. Take the top ten to the `Setups` tab and buy the one with a plan.

### 5.7 Tab — `Patterns — reversal, triangles, continuation, wedges, channels, candlesticks, price action`

**What it is** — A scanner that finds classic chart, candlestick and price-action patterns on the daily chart of every stock in a universe, tells you whether each one is still **forming** or already **confirmed**, and gives you the trigger line, the measured-move target, a stop hint and a 0–100 quality score. It runs after every close and is stored. It is **a finder, not a judge**: the shape is the setup; the break with volume is the signal.

**What you see**
- The description under the heading: *Every pattern carries its **category**, **direction**, **kind** (reversal / continuation / indecision / structure), a **reliability** and **frequency** tier from the classic references, and — as it accumulates — the app's own EGX hit rate from the Scorecard. **Confirmed** = the trigger line was broken (or the candle/event completed) recently; **Forming** = shape complete, not yet broken. A finder, not a judge: the break with volume is what matters.*
- While loading: `Loading stored pattern scan…`.
- A control row, left to right: **`Universe`** (EGX30 / EGX70 / EGX100, default EGX100), **`Status`** (`All`, `Confirmed only`, `Forming only`), **`Category`** (`All categories`, `Reversal`, `Triangles`, `Continuation`, `Wedges`, `Channels`, `Candlesticks`, `Price action`), a **`Hide candlesticks`** checkbox (on by default; hover it to read *Candlestick patterns fire on many stocks every session; hide them to see the chart shapes and price-action events*), a **`Catalog`** button, an info line, and a **`Scan now (≈1 min)`** button.
- The info line reads like `37 patterns · 14 confirmed · reversal 6, triangle 4, price action 27 · scan of <date> · stored by the post-close job` (or `· scanned just now`). The first number counts the rows actually shown; the `confirmed` count and the per-category counts respect your `Status` and `Category` choices but **not** the `Hide candlesticks` box, so they still include candlesticks you have hidden.
- If nothing matches: `No patterns stored yet for this filter. The post-close job scans every trading day at 15:00, or press Scan now.`
- A table, confirmed patterns first, then by quality:

| Column | Meaning |
|---|---|
| `Symbol` | The ticker |
| `Pattern` | The pattern name. For trendline shapes (triangles, wedges, channels, rectangles) a confirmed row adds **` ↑ broke up`** or **` ↓ broke down`** to say *which* line was broken. Hover the name for the one-line description of the pattern |
| `Category` | reversal / triangle / continuation / wedge / channel / candlestick / price action |
| `Direction` | Badge: **bullish** (green), **bearish** (red), **neutral** (amber). For shapes that are neutral in the textbook, a confirmed row reports the direction of the actual break |
| `Kind` | reversal / continuation / indecision / structure |
| `Reliability` | Badge: **high** (green), **medium** (teal), **low** (amber) — the textbook tier, not an EGX statistic |
| `Frequency` | common / uncommon / rare — how often the textbook says the shape appears |
| `Status` | **confirmed** (green) or **forming** (amber) |
| `Quality` | 0–100, see below |
| `Last` | Last daily close |
| `Neckline` | The trigger line — the level that has to break (or was broken) |
| `To neckline %` | Distance from the last close to the trigger line. Positive = the line is above price |
| `Target` / `Target %` | The measured move projected from the trigger line, and the distance to it from the last close |
| `Move done %` | Confirmed patterns only: how much of the measured move price has already travelled (0 = at the neckline, 100 = at target). Patterns that have reached their target are not shown at all — they are finished trades, not signals |
| `Stop hint` | Where the pattern is wrong: just beyond the pattern's extreme for the big reversal shapes (below the lows for a bullish shape, above the head for a bearish one), the opposite line for triangles, wedges and channels, just beyond the flag for flags, and just beyond the signal bar for candlesticks and price-action events |
| `Break date` | The session on which the trigger was broken |
| `Break vol ×` | Volume on the break day divided by the 20-day average |
| `Since` | The date of the pattern's first point |
| `Median value 20d` | Typical money traded per day (liquidity) |

- After a live Scan now, a basis line appears under the table: *Swing points must dominate 5 bars each side; equal levels within ~1.2-1.5 ATR14; pattern depth >= 2 ATR; last pivot within 60 sessions. CONFIRMED = a close beyond the neckline within the last 15 sessions (volume ratio vs 20-day average shown); FORMING = shape complete, neckline not yet broken. Target = measured move from the neckline. Finder, not judge: the break with volume is the signal.* The expandable `Full patterns payload` is always there.
- Errors show as `Patterns failed: …` or `Scan failed: …`.

**How the scanner works, in plain words.** It finds swing highs and lows on the daily chart (for the big reversal shapes a point must be the highest or lowest for five bars either side; the shorter trendline and structure checks use three) and tests the geometric rules of each shape with a tolerance scaled to the stock's own volatility (its 14-day average range), so a jumpy stock gets more slack than a quiet one. "About the same price" means within roughly 1.2–1.5 average ranges; equal lows or highs must be at least 8 sessions apart; a pattern must be at least two average ranges deep to count; the last swing point must be within the last 60 sessions; a stock needs at least 60 days of history to be scanned at all. The seven families are found in different ways:

| Category | How it is found | Confirmed means |
|---|---|---|
| **Reversal** (double/triple tops and bottoms, head & shoulders, cup & handle) | Equal swing points with a neckline across the bounces or dips between them (the cup needs rims 30–130 sessions apart, a bowl 12–50% deep and a handle of 5–25 sessions no deeper than 35% of the cup) | A daily close beyond the neckline within the last 15 sessions. A confirmed pattern that then closes 2% back through its neckline is dropped — the break failed |
| **Reversal** (rounding top/bottom, inverse cup & handle) | A smooth bowl or dome fitted over 40–120 sessions | A close beyond the rim within the last 5 sessions |
| **Reversal** (diamond top/bottom) | Daily ranges that widen through the first half and narrow through the second, after a move of at least 5% | A close beyond the recent edge within the last 5 sessions |
| **Triangles, Wedges, Channels, rectangles** | Straight lines fitted through the swing highs and the swing lows over 30, 45 or 60 sessions; classified by whether each line is flat, rising or falling and whether the gap shrinks, grows or stays. A box wider than 40% of the price is a trend, not a shape, and is ignored; the measured move is capped at 25% of the price | A close beyond either line within the last 5 sessions (the `↑ broke up` / `↓ broke down` suffix). A rectangle after a 5%+ rise is labelled Bullish Rectangle, after a 5%+ fall Bearish Rectangle; a flat box with no such trend into it is a Rectangle when found over 30 sessions and a Horizontal Channel when found over 45 or 60; a channel with price hugging the trend-side half is labelled Bullish/Bearish Channel |
| **Continuation** (flags, pennants) | A pole of at least 4 average ranges in 12 bars or fewer, then 5–20 bars of tight drift no wider than half the pole | A close beyond the flag line within the last 5 sessions |
| **Candlesticks** | The last one, two or three completed daily bars, measured against the average body of the prior ten bars. Reversal candles only count after a move of at least 3% over the prior 8 sessions — otherwise they are noise | Always **confirmed** — a candle is complete when the session closes |
| **Price action** | Breakouts of the prior 20-session range and what happened next (a close back inside within 3 sessions makes it a false breakout / trap); Wyckoff springs/upthrusts; pullbacks to the 20-day average in an uptrend; swing structure over the last 80 sessions | Always **confirmed** — an event either happened in the last 3 sessions (a false breakout or trap: within the last 5) or it is not listed; the two structure rows (Higher High / Higher Low, Lower High / Lower Low) describe the current swing structure and have no target |

**The seven categories, their patterns and their bias** (reliability and frequency are the textbook tiers shown in the `Catalog`):

| Category | Patterns (direction · reliability) |
|---|---|
| **Reversal** (12) | Head & Shoulders (bearish · high), Inverse Head & Shoulders (bullish · high), Double Top (bearish · medium), Double Bottom (bullish · medium), Triple Top (bearish · medium), Triple Bottom (bullish · high), Rounding Top (bearish · medium), Rounding Bottom (bullish · high), Cup & Handle (bullish · medium), Inverse Cup & Handle (bearish · medium), Diamond Top (bearish · medium), Diamond Bottom (bullish · medium) |
| **Triangles** (6) | Ascending Triangle (bullish · medium), Descending Triangle (bearish · medium), Symmetrical Triangle (neutral — direction decided by the break · medium), Expanding Triangle (neutral · low), Ascending Broadening Triangle (bearish · low), Descending Broadening Triangle (bullish · low) |
| **Continuation** (7) | Bull Flag (bullish · high), Bear Flag (bearish · high), Bull Pennant (bullish · medium), Bear Pennant (bearish · medium), Rectangle (neutral · medium), Bullish Rectangle (bullish · medium), Bearish Rectangle (bearish · medium) |
| **Wedges** (3) | Rising Wedge (bearish · medium), Falling Wedge (bullish · medium), Broadening Wedge (neutral · low) |
| **Channels** (5) | Ascending Channel (bullish · medium), Descending Channel (bearish · medium), Horizontal Channel (neutral · medium), Bullish Channel (bullish · medium), Bearish Channel (bearish · medium) |
| **Candlesticks** (28) | *High reliability:* Bullish Engulfing, Bearish Engulfing, Morning Star, Evening Star, Three White Soldiers, Three Black Crows. *Medium:* Dragonfly Doji (bullish), Gravestone Doji (bearish), Hammer (bullish), Shooting Star (bearish), Piercing Pattern (bullish), Dark Cloud Cover (bearish), Three Inside Up/Down, Three Outside Up/Down, Marubozu, Outside Bar, Shark-32 (two consecutive inside bars — a coil that continues the prior trend about 60% of the time according to Bulkowski; enter on a close outside the first bar's range, target = the pattern's height). *Low:* Doji, Inverted Hammer (bullish), Hanging Man (bearish), Harami, Inverted Harami, Tweezer Top (bearish), Tweezer Bottom (bullish), Spinning Top, Inside Bar |
| **Price action** (14) | Breakout (neutral in the book — bullish or bearish by the side broken), False Breakout, Retest, Failed Retest, Pullback (bullish), Throwback (bullish), Spring (bullish, Wyckoff), Upthrust (bearish, Wyckoff), Bull Trap (bearish), Bear Trap (bullish), Higher High / Higher Low (bullish structure), Lower High / Lower Low (bearish structure), Change of Character — CHoCH (the first close through the last swing *against* the trend), Break of Structure — BOS (a close through the last swing *with* the trend). All medium reliability |

**Quality, 0–100.** For the equal-swing reversal shapes: up to 35 points for how equal the levels are, 25 for how deep the pattern is relative to the stock's volatility, 15 for being confirmed plus up to 15 for volume on the break (credit starts above 0.8× the 20-day average and 2.0× earns all of it; a forming pattern gets a flat 10 instead), and 10 for recency. A confirmed pattern then loses one point for every 5% of `Move done %`, so a break you are hearing about late scores lower than a fresh one. Trendline shapes score on how well the lines fit, how many touches they have, confirmation and height; flags on the size of the pole, confirmation and the tightness of the flag; candlesticks start from a base per pattern (e.g. Morning Star 70, Hammer 60, Doji 40) and add 10 for volume above 1.3× and 10 for the right trend context. Confirmed, directional patterns with quality 50 or more are also journaled as signals for the `Scorecard`, so the app learns which shapes work on EGX.

**What the buttons do**
- **`Universe`** — EGX30 / EGX70 / EGX100. Each has its own stored scan (the post-close job scans EGX100; the others are stored once you press Scan now on them).
- **`Status`** — `All`, `Confirmed only`, `Forming only`. Reloads the stored scan with the filter applied.
- **`Category`** — one family at a time or `All categories`.
- **`Hide candlesticks`** — on by default. Removes candlestick rows from the view so the chart shapes and price-action events are readable. It is ignored when `Category` is set to `Candlesticks`.
- **`Catalog`** — replaces the table with the full pattern reference (see 5.8). `Back to scan` returns.
- **`Scan now (≈1 min)`** — scans the selected universe live: `Scanning EGX100 for chart patterns — about a minute…` (with the chosen universe), then a toast `Scan done: N patterns, M confirmed` (counts for the whole scan, before your filters). Your current Status and Category filters are applied to the fresh result, which is also stored — and its confirmed, directional, quality-50-or-better patterns are journaled for the Scorecard.
- **Hover a pattern name** for its one-line textbook description.
- **Click a row** to open the Stock page — its `Chart patterns` card lists the patterns on that stock and the chart draws the neckline and target of the leading shapes.
- **Click a column header** to sort (for example by `Quality` or by `To neckline %`).

**How to benefit from it — trading a confirmed pattern versus a forming one**

*A forming pattern is a watchlist entry, not a trade.* The shape is complete, but the market has not voted yet. What you do with it:
- Note the `Neckline` and `To neckline %`. A bullish shape with the neckline a couple of percent above price is one good day from a signal; one far above price is weeks away and may never get there.
- Put a price alert at the neckline (or a little above it, to avoid an intraday poke). On the Stock page the same level is drawn on the chart.
- Pre-compute the trade: entry a touch above the neckline, stop at the `Stop hint`, target at `Target`. If that gives you less than 2R, cross it off *now* — a break that arrives will not change the arithmetic. This is the same 2R bar the `Risk plan` pillar on the `Setups` tab applies.
- Do **not** buy inside the pattern hoping for the break. A forming double bottom can still resolve into a lower low — that is why the app calls this state "forming", and why the stop hint sits below the lows, not below the neckline. The app drops a forming shape as soon as price moves past its lows (or highs) by the tolerance.

*A confirmed pattern is a signal — but a signal with a clock on it.* The neckline was broken by a daily close within the last 15 sessions (5 for trendline shapes, rounding shapes, diamonds and flags; 3 for price-action events). What you check, in order:
1. **`Break vol ×`.** The quality score itself starts rewarding volume above 0.8× the 20-day average and gives full marks at 2.0× — use the same scale. A break below 1.0× is a break the market did not notice; treat it as forming until volume shows up. This single column separates the good confirmed rows from the rest.
2. **`Move done %`.** The lower the better — the app docks a quality point for every 5% already travelled. A row near 0 has the whole measured move ahead of you; a row past the halfway mark is one where the reward left may not pay for the stop, so reduce size or wait for a throwback to the neckline (the `Throwback` and `Retest` events on this same tab tell you when price has come back and held). Rows at 100% are removed for exactly this reason.
3. **`To neckline %`.** For a bullish confirmation you want it small and negative (price a little *above* the line). If price has run far above the neckline, the throwback you would like to buy may never come; if price has slipped back *below* the neckline the break is failing (for the big reversal shapes the app drops the row once a close is 2% back through the neckline).
4. **Direction versus the trend.** A bullish reversal shape in a stock whose `Setups` row shows `Trend` ✗ is a counter-trend trade — allowed, but size it smaller and demand more than the 2R minimum. A bull flag in a `Leaders` stock is a with-trend trade — the easiest money this page finds.
5. **Quality** is a tiebreaker, not a gate. Between two confirmed inverse head & shoulders take the higher score; but a mid-quality break on strong volume beats a high-quality break on weak volume.

*Reading the categories differently:*
- **Reversal shapes** are the big ones (weeks to months). Trade the neckline break; the stop hint is below the lows/above the head — that is a wide stop, so the position will be small. That is correct.
- **Triangles, wedges, channels, flags** are shorter (a few weeks). The `↑ broke up` / `↓ broke down` suffix tells you what actually happened — a symmetrical triangle is "neutral" in the textbook but the confirmed row is not. A *rising wedge that broke down* in a stock you hold is an exit signal.
- **Candlesticks** are one-to-three-day signals. Alone they are weak; the app hides them by default for that reason. Their value is as *timing* on a stock you already want: a Hammer or Bullish Engulfing at the neckline of a forming double bottom, or at the `Pullback` level in a leader, is the entry day. Never buy a candlestick pattern on a stock with no other reason.
- **Price action** events are the tape telling you the truth about a level. `Breakout` + high `Break vol ×` = act. `False Breakout`, `Bull Trap`, `Failed Retest`, `Upthrust`, `Change of Character` on a stock you hold = the market has rejected the move; the `Setups` tab treats these as automatic fails on `Price action`. `Pullback` (2–5 down sessions into the 20-day average in an uptrend) is the classic buy-the-dip spot in a leader. `Spring` (a dip under range support that closes back inside) is Wyckoff's shakeout — one of the better low-risk entries because the stop hint is just under the spring low.

*Common mistakes:*
- Buying a "confirmed" pattern with `Break vol ×` below 1.0 because the badge is green. Volume is the signal; the badge only says the line was crossed.
- Confusing the target with a promise. The measured move is where the pattern *projects*; a resistance level just above the neckline (see the Stock page levels) will often stop the move first. Use the nearer of the two as your first target.
- Trading a pattern without checking `Median value 20d`. The pattern scan does not remove illiquid names the way Leaders and Candidates do — sort by that column and stay above the floor (by default 5,000,000 EGP).
- Trusting the textbook tiers as EGX numbers. They are Western priors. Open the `Catalog` after a few months of scans and read the `EGX beat index 10d %` column — that is the truth for this exchange.

### 5.8 View — `Catalog` (inside the Patterns tab)

**What it is** — The full reference of every pattern the app knows — 75 patterns in 7 categories — with its textbook reliability and frequency tiers side by side with the app's own EGX track record so far. Press `Catalog` on the `Patterns` tab to open it.

**What you see**
- While loading: `Loading pattern catalog…`.
- A header line: `75 patterns in 7 categories · 75 detected by the scanner`, and a `Back to scan` button.
- A table, one row per pattern:

| Column | Meaning |
|---|---|
| `Category` | Reversal patterns / Triangle patterns / Continuation patterns / Wedge patterns / Channel patterns / Candlestick patterns / Price-action patterns |
| `Pattern` | The name |
| `Direction` | bullish (green) / bearish (red) / neutral (amber) badge |
| `Kind` | reversal / continuation / indecision / structure |
| `Reliability (classic refs)` | high (green) / medium (teal) / low (amber) — from Bulkowski's chart-pattern statistics, Nison's candlestick work and Wyckoff practice |
| `Frequency` | common / uncommon / rare |
| `EGX graded` | How many confirmed detections of this pattern the Scorecard has graded so far on EGX (`—` until there are any) |
| `EGX win 10d %` | Of those, the share where the stock was higher 10 sessions later |
| `EGX beat index 10d %` | The share where the stock beat EGX30 over the same 10 sessions |
| `EGX avg excess 10d %` | The average return above the index, green or red |
| `What it is` | The one-line description, e.g. "Three peaks, the middle highest; neckline under the two dips. Break below the neckline confirms." |

- Under the table, the basis: *Reliability/frequency tiers are qualitative priors from the classic Western references (Bulkowski, Nison, Wyckoff practice). egx_stats are the app's own Scorecard grades of CONFIRMED detections on EGX — the numbers that matter here.* — "egx_stats" is the app's name for the three `EGX …` columns in this table; they are the Egyptian evidence, while the Reliability and Frequency tiers are only textbook opinion.
- Errors show as `Catalog failed: …`.

**What the buttons do**
- **`Back to scan`** — returns to the pattern table with your Universe, Status, Category and Hide-candlesticks settings intact.
- **Click a column header** to sort — for example by `EGX beat index 10d %` once numbers exist.

**How to benefit from it**
- **Use it as a dictionary first.** When the scan shows a `Shark-32` or an `Upthrust` you do not recognise, the `What it is` column tells you the shape and the trigger in one sentence. Learn the twenty or so you see most often; ignore the rare ones until they appear.
- **Use it as a report card later.** Only confirmed, directional detections with quality 50 or more are journaled, and the 10-day columns fill in only once 10 sessions have passed since the pattern fired, so the EGX columns start empty and grow one day at a time. After two or three months of daily scans, sort by `EGX beat index 10d %` and look at rows with `EGX graded` of 20 or more (the same sample the Scorecard demands before it trusts a scanner): the patterns at the top *work on this exchange*, whatever the textbook says; the ones at the bottom are decoration. Adjust which rows of the `Patterns` tab you act on accordingly.
- **Treat the textbook tiers as the starting bias, nothing more.** High-reliability shapes (Head & Shoulders both ways, Triple Bottom, Rounding Bottom, Bull/Bear Flag, the engulfing and star candles, Three Soldiers/Crows) deserve the benefit of the doubt until the EGX columns say otherwise. Low-reliability ones (Doji, Harami, Inside Bar, the broadening formations) should never be traded alone.
- The `Direction` column settles arguments: a Rising Wedge is *bearish*, a Falling Wedge is *bullish*, a Hanging Man is *bearish* even though it looks like a Hammer. When a row on the scan surprises you, check here before acting.

### 5.9 Tab — `Signal Scorecard — which scanners actually work`

**What it is** — The `Candidates` tab counts how many scanners flagged a stock. That is evidence by *volume*, not by *track record*. The Scorecard builds the track record: every stored scanner hit (and every journaled confirmed pattern) is graded by what the stock did **5, 10 and 20 sessions later**, and by how that compared with EGX30 over the same window. A scanner's 10-day beat rate then becomes its weight in the `Candidates` ranking — but only once it has 20 graded hits, because a 60% hit rate on 5 trades is noise.

**What you see**
- The description under the heading: *Every scanner hit is graded by what the stock did 5, 10 and 20 sessions later, against EGX30 over the same window. A scanner's beat rate becomes its weight in the Candidates ranking — only after 20 graded hits, because a 60% hit rate on 5 trades is noise. Hits accumulate one day at a time from the post-close job.*
- While loading: `Loading scorecard…`.
- A header line: `N hits stored · M graded (R from replayed history) · K waiting for price history · weights change after 20 graded hits`, and a `Grade now` button. The bracket appears once the historical replay has run.
- If nothing is graded yet: `Nothing graded yet. A hit can only be graded once 5 sessions have passed since it fired, so the first rows appear about a week after the scanners start running. Come back then.`
- A table, one row per signal source (the four Candidates scanners plus one row per confirmed pattern type that has been journaled). Columns, in screen order:

| Column | Meaning |
|---|---|
| `Scanner` | The scanner's key (`squeeze`, `volume_breakout`, `smart_money`, `momentum`) or a pattern's key prefixed with `pattern_` (for example `pattern_double_bottom`, `pattern_bull_flag`) |
| `Graded` | Hits that have an outcome row |
| `Source` | Where the graded hits came from: `N live` (journaled by real post-close scans) and/or `N replay` (found by the historical replay on the Dashboard's `Proven edge` card). Hover for the definition |
| `Weight from` | `own record` when the weight rests on this scanner's own graded hits, or a badge `proxy: momentum_3` when a live scanner with fewer than 20 live graded hits borrows the weight of its replayed candle rule (`squeeze` → `squeeze_breakout`, `momentum` → `momentum_3`, `volume_breakout` → `range_breakout`). Hover for the full basis, e.g. "proxy: replayed 'momentum_3' beat rate 48% over 912 signals at 10d — until 'momentum' has 20 live graded hits (3 so far)" |
| `Weight` | The scanner's multiplier in the `Candidates` ranking, as a badge. **Amber** = neutral 1.0 because fewer than 20 hits are graded at 10 days (hover to read e.g. "neutral 1.0 — 12/20 graded hits at 10d"). **Green** = above 1.0 (right more often than a random entry). **Red** = below 1.0. **Teal** = exactly 1.0 with a full sample. Hover for the basis, e.g. "right-way rate 46% over 777 hits at 10d (random entry 44%)". The formula is 1 + 2 × (the 10-day right-way rate − the random-entry rate), clamped between 0.5 and 1.5 |
| `n 5d` · `Right-way 5d %` · `Avg excess 5d %` | How many hits have reached 5 sessions, the share of those where the stock moved the signal's way relative to EGX30, and their average excess over the index (green or red). **Bearish** signals (a `bearish` chip next to the name) are graded on the stock *falling*, so every number reads "in the signal's favour" |
| `n 10d` · `Win 10d %` · `Right-way 10d %` · `vs random 10d` · `Avg excess 10d %` | The same at 10 sessions, plus `Win 10d %` — the share of hits where the stock simply moved the signal's way in absolute terms — and `vs random 10d`, the right-way rate minus the random-entry rate in percentage points (the number that decides the weight) |
| `n 20d` · `Right-way 20d %` · `Avg excess 20d %` | The same at 20 sessions |

- Under the table, the basis sentence (grading, the bearish flip, the random-entry yardstick and the weight formula, all in one paragraph) and an expandable `Full scorecard payload`. The header line ends with `random entry beats EGX30 44% of the time (the yardstick)` once the `Proven edge` card has measured it.
- Errors show as `Scorecard failed: …` or `Grading failed: …`.

Where the hits come from: the post-close job (every trading day at 15:00) runs the Candidates scan and stores one hit per scanner per stock, and the pattern scan stores confirmed, directional patterns of quality 50 or more. A live `Refresh` on the `Candidates` tab does **not** add hits — only the scheduled post-close run does, so the track record is not polluted by you pressing buttons. (The `Scan now` button on the `Patterns` tab, by contrast, does store its confirmed patterns as hits.) Each grading run takes the oldest ungraded hits first, up to 120 at a time; a hit whose 20-day outcome is still open is re-graded on later days (at most once a day) until it completes. The weekly maintenance job (Saturday 12:00) removes **live** hits older than 180 days, so the live record is a rolling six months; **replayed** hits (source `replay`) are the long-run track record and are never pruned — use `Replay history` on the Dashboard to build them and its neighbour `Refresh` to rebuild the `Proven edge` table.

**What the buttons do**
- **`Grade now`** — grades whatever is ready right now: `Grading pending hits against Yahoo history…`, then a toast `Graded N hit(s), M still waiting for more sessions` (the second part only appears when something is still open), and the table reloads. Grading also happens automatically in the post-close job, so this is only for impatience.
- **Hover a `Weight` badge** to read exactly why it has that value.
- **Click a column header** to sort.

**How to benefit from it**
- **Read `Beat EGX30 10d %`, not `Win 10d %`.** In a bull month every scanner "wins". A scanner is only useful if the stocks it picks do better than the stocks it did not pick — that is what the beat rate measures. 50% is a coin flip (and gives exactly the neutral weight of 1.0); anything above it on a full sample earns a weight above 1.0, anything below it a weight under 1.0 — the app's own line between "helps" and "hurts".
- **Let the 20-hit gate protect you from yourself.** After two weeks you will see a scanner at 70% on 7 hits and want to lean on it. The app deliberately keeps its weight at 1.0 until 20 graded hits exist. Copy that discipline in your own trading: do not change how you size a strategy until you have 20 trades in it.
- **Compare the three horizons for the same scanner.** A strong 5-day beat rate that fades by 20 days means the scanner finds *pops*, not *trends* — take profits faster on its hits. A weak 5-day but strong 20-day rate means its hits start slowly — do not stop out on day three.
- **Watch the `pattern_…` rows fill in.** After a few months this table is the only place that tells you whether a head & shoulders or a bull flag has predicted anything on EGX. Weight your attention on the `Patterns` tab toward the shapes with green excess here (the `Catalog` shows the same 10-day numbers next to each pattern's name).
- **Use it to explain the `Candidates` order.** When a stock ranks above another with the same family count, look here: it is being lifted by a scanner with a green weight. When a scanner turns red, its hits are demoted automatically — you do not need to do anything, but you should stop treating that scanner's badge on the `Candidates` tab as confirmation.
- Common mistake: reading the average excess without the count. A large average on a handful of hits is one lucky stock; a small positive average on many hits is an edge you can size around. Sort by the `n` columns first.

---

## 6. Page 4 — Backtest

**This page answers one question: "if I had traded this rule on this stock, what would actually have happened?"** It replays a rule over real past prices, charges fees and slippage, and reports the result in numbers and — for the app's own rules — in a plain-English verdict.

Open it from the sidebar (**Backtest**). If you add a stock to the end of the page's address — `?symbol=COMI`, for example — that stock is already typed into the top **Symbol** box when the page opens. No other page sends you here with a stock pre-filled, so this is an address you type yourself. (The `App rules` Symbol box is filled separately, with the first stock you hold.)

There are two separate engines on this page, and it matters which one you are looking at:

| Engine | Where | What it tests | How it fills trades |
|---|---|---|---|
| **App rules** (the tab that matters) | The `App rules` tab | The Squeeze / Volume-Breakout / Momentum / pullback entries the scanners actually give you, closed by the Position Guardian's exits | Buys at the **next session's open** after the signal, sizes the position so **1% of equity** is at risk (by default), checks the **stop before the target**, fills **gaps** at the open, charges fees on both sides plus slippage. Yahoo daily closes, one position at a time |
| **Indicator strategies** | The `Backtest setup` panel and the `Indicator strategies`, `Compare all`, `Walk-forward` tabs | Nine textbook indicator rules (RSI, Bollinger, MACD, moving-average crosses, Supertrend, Donchian, Keltner…) | Buys at the **close of the signal session**, puts **all capital** into every trade, has **no stop-loss** (it exits only on the opposite signal), subtracts commission and slippage twice per round trip |

Both engines use Yahoo daily history (the indicator engine can also use hourly bars), so both keep working when TradingView is rate-limiting the rest of the app. Neither places orders. Nothing here is advice; it is a way of checking your own ideas against history before you risk money on them.

**The one rule that applies everywhere on this page: under about 20 trades the numbers are noise.** The page says so every time it happens — in the verdict box, in the metric cards, and in red warning text. Believe the warning, not the win rate.

---

### 6.1 Panel — `Backtest setup`

**What it is** — The form at the very top of the page. It drives the *indicator-strategy* engine only (the three buttons `Run backtest`, `Compare all`, `Walk-forward`). It does **not** drive the `App rules` tab, which has its own smaller form underneath.

**What you see**

| Field | Default | What it means |
|---|---|---|
| **Symbol** | *(empty, or the stock you came from)* | The stock to test. Start typing and pick from the suggestion list (every EGX ticker with its company name). "EGX:" in front is ignored. |
| **Strategy** | *(first in the list)* | One of the nine indicator rules below. |
| **Period** | `1y` | How much history: `1mo`, `3mo`, `6mo`, `1y`, `2y`. Only these five work — the engine rejects anything else, so nothing else is offered. |
| **Interval** | `1d` | Candle size: `1d` (one candle per session) or `1h` (hourly candles, which also need at least 100 bars). |
| **Commission %** | `0.3` | Broker fee **per side**, in percent. |
| **Slippage %** | `0.1` | Allowance **per side** for not getting the exact price you wanted. |
| **Initial capital (EGP)** | `100000` | Starting money for the simulation. Must be at least 1. |

**The nine strategies** (the names are what you see in the dropdown; the rule is what the engine actually does):

| Name | Buys when | Sells when | Notes |
|---|---|---|---|
| `rsi` | 14-day RSI drops below 40 | RSI rises above 60 | Mean-reversion; buys weakness |
| `bollinger` | Close falls below the lower Bollinger band (20, 2) | Close rises above the middle band | Mean-reversion |
| `macd` | MACD (12, 26, 9) crosses above its signal line | MACD crosses below the signal | Trend-following |
| `ema_cross` | 20-day EMA crosses above the 50-day EMA | 20 crosses back below 50 | Trend-following |
| `supertrend` | Supertrend (ATR 10, multiplier 3) flips up | Flips down | Trend-following |
| `donchian` | Today's high beats the prior 20-session channel top | Today's low breaks the prior 20-session channel bottom | Breakout |
| `rsi_pullback` | 50-day average above 200-day average **and** RSI below 40 | RSI above 70 **or** close below the 50-day average | Needs at least 220 sessions — use `1y` or `2y`. Not allowed in Walk-forward |
| `keltner_breakout` | Close above 20-day EMA + 2 × ATR14 | Close below the 20-day EMA | Volatility breakout |
| `triple_ema` | 20-day EMA crosses above 50-day **and** close above the 200-day average | 20 crosses below 50 | Needs 220 sessions. Not allowed in Walk-forward |

**How the indicator engine fills and charges** (this is the honest part, read it once):
- Entry and exit both happen at the **close of the signal candle**. There is no waiting for the next open.
- **Every trade uses 100% of the current capital.** There is no stop-loss and no position sizing — a trade ends only when the opposite signal fires. This is very different from how you trade with the app.
- Costs: `(commission + slippage) × 2` is subtracted from every trade's percentage return (once to get in, once to get out). With the defaults that is 0.8% per round trip.
- A trade still open at the end of the window is closed at the last close and counted (so a strategy that is currently underwater cannot hide it).
- Prices are dividend- and split-adjusted where Yahoo provides adjusted closes — important on EGX, where cash dividends of 5–15% would otherwise look like losses on the ex-dividend day.
- The **Buy & hold** benchmark is charged one round trip of the same commission and slippage, so the comparison is fair.
- Sharpe is calculated in **EGP terms**: the risk-free rate is 25% a year by default (the risk-free-rate setting in your configuration) and a year is 245 EGX sessions of 4.5 hours, not the 252 × 6.5 hours a US tool assumes. That is why an EGX strategy's Sharpe here is lower than the same numbers would show on a foreign site — roughly speaking, a strategy has to out-earn a 25% deposit rate before its Sharpe turns positive.
- Every run is stored by the app, so a result can be looked up later even though Yahoo quietly revises EGX history.
- When your starting capital is more than 10% of the stock's typical daily turnover (its 20-day median traded value, from the app's own stored snapshots), the result carries a **liquidity warning** — see 6.9. It sits inside the `All returned fields` expander, not in the cards, so open that expander on any thin stock.

**What the buttons do**

| Button | What happens |
|---|---|
| **`Run backtest`** | Tests the one selected strategy on the one selected stock. Switches you to the `Indicator strategies` tab, shows "Backtesting COMI with "rsi"…" while it works, then a green notice "Backtest finished: COMI / rsi". Failure shows a red box "Backtest failed: …" and the same text as a notice. |
| **`Compare all`** | Runs all nine strategies on the stock and ranks them. Switches to the `Compare all` tab; shows "Comparing all strategies on COMI — this can take a while…"; ends with "Strategy comparison finished for COMI" or "Comparison failed: …". |
| **`Walk-forward`** | Splits history into learn/prove windows and scores the strategy on the parts it did not see. Switches to the `Walk-forward` tab; shows "Walk-forward testing COMI / rsi…" while it works. A `1y` period is quietly upgraded to `2y` so the folds have enough data. Ends with "Walk-forward finished for COMI" or "Walk-forward failed: …". |

If the Symbol box is empty every button stops with the notice **"Enter a symbol first"**; `Run backtest` and `Walk-forward` also stop with **"Pick a strategy"** if the strategy list is empty. If the strategy list itself could not be loaded you get a red notice beginning "Could not load strategies:" — the server is probably not running.

**How to benefit from it**
- **Leave commission and slippage switched on, and be honest about them.** A rule that only makes money when trading is free is not a rule. If your broker charges more than 0.3% per side, type your real number. On a thin stock raise slippage to 0.5% or more — the liquidity warning inside `All returned fields` tells you when your capital is more than a tenth of the stock's typical daily turnover, and its own advice is "Consider slippage ≥0.5%/side".
- Treat this panel as **a personality test for a stock, not a trading system.** Because every trade uses all capital with no stop, the returns are not something you would ever replicate. What *is* useful is the ranking: trending names reward moving-average and Supertrend rules; choppy names reward RSI and Bollinger. That tells you which scanner's signals to take more seriously on that stock.
- Use `1y` or `2y`. Shorter periods produce a handful of trades and the red "INSUFFICIENT SAMPLE" warning; `rsi_pullback` and `triple_ema` will not run at all on short periods.
- When you want to know whether **your** setup and **your** stop distance work, do not use this panel — go to the `App rules` tab (6.3–6.8). This panel tests textbook indicators; that tab tests what the Screener and Guardian actually tell you to do.

---

### 6.2 Tabs — `App rules` · `Indicator strategies` · `Compare all` · `Walk-forward`

**What it is** — A row of four tabs directly under the setup panel. Only one is visible at a time. `App rules` is selected when the page opens.

**What you see** — The active tab is highlighted. Each tab shows one results panel: `Test the app's own rules`, `Backtest result`, `Strategy comparison` and `Walk-forward analysis`.

**What the buttons do** — Click a tab to switch panels; results already on a hidden tab are kept, not cleared. The three buttons in `Backtest setup` switch tabs for you automatically when they run.

**How to benefit from it**
- Start on `App rules`. It is the only tab that tests the trades you actually take.
- Use the other three when you want a second opinion about a stock's character (does it trend, does it mean-revert) before deciding which scanner to trust on it.
- Because results persist per tab, run a single strategy, then `Compare all`, then `Walk-forward` on the same stock and flip between the tabs to cross-check — a winner in `Compare all` that turns WEAK in `Walk-forward` is telling you something.

---

### 6.3 Tab — `App rules` (panel `Test the app's own rules`)

**What it is** — The form and results area that backtests **the app's own signals and exits**. The panel explains itself: "The scanners tell you what to buy and the Guardian tells you when to sell. This tests exactly those rules on real daily history: enter at the next open after the signal, stop 2×ATR, fees and slippage charged, one position at a time. Every result ends with a verdict in plain words and a warning when there are too few trades to mean anything."

**What you see**

| Control | Default | What it means |
|---|---|---|
| **Symbol** | The first stock in your open positions (if you have any), else empty | The stock to test. "EGX:" in front is ignored. |
| **Entry rule** | `Bollinger squeeze breakout` | Which of the four scanner-style entries to trade (below). |
| **Exit rule** | `Guardian rules` | Which of the four ways of getting out to use (below). |
| **Period** | `2 years` | `1 year`, `2 years`, `3 years` or `5 years` of daily history (about 250 sessions a year). The engine also loads 60 extra sessions before the window to warm up the indicators. |
| **Capital (EGP)** | Your account size from the app's settings (100,000 by default) | Starting equity. Minimum 1000. |
| **Universe** | `EGX30` | `EGX30`, `EGX70` or `EGX100` — used only by `Run on universe`. |

Under the form a grey help line describes the currently selected pair, e.g. "Entry — Band width in the tightest 20% of the last 120 sessions, then a close above the upper band with volume >= 1.5x its 20-day average. (The Squeeze scanner's trade.) Exit — Stop 2 x ATR; at +1R the stop moves to breakeven and then trails 2.5 x ATR below the highest close; take profit at +3R; time stop after 15 sessions inside +/-0.5R." It changes as you change the dropdowns. If the rule list could not be fetched the line reads "Could not load the rule list: …".

Before anything has run the results area says **"Pick a stock you hold or watch, choose a rule pair, press Run."**

**The four entry rules** (a signal fires at a session's close; the trade is bought at the *next* session's open):

| Dropdown label | Rule, as the engine checks it | Which scanner it mirrors |
|---|---|---|
| **Bollinger squeeze breakout** | Yesterday's Bollinger band width was in the tightest 20% of the last 120 sessions, today closes above the upper band, today's volume is at least 1.5× its 20-day average | Squeeze scanner |
| **20-day high breakout** | Close above the highest high of the prior 20 sessions, close above the 50-day average, volume at least 1.5× average | Volume-Breakout scanner |
| **Pullback in uptrend** | 20-day average above 50-day, close above the 50-day, two to five consecutive down closes that brought price to within 1 ATR of the 20-day average, then the first up close | The Guardian's "pullback" event, traded |
| **Three rising closes** | Three consecutive higher closes, price above the 20-day average, 14-day RSI between 50 and 75 | Momentum scanner |

**The four exit rules** (in every case the initial stop is 2 × ATR14 below the entry price, and the number of shares is chosen so that a fall to that stop loses 1% of equity by default — the same risk-per-trade setting the Portfolio page uses; if that many shares cost more than the cash available, the share count is cut to what the cash can buy):

| Dropdown label | What it does | What it is for |
|---|---|---|
| **Fixed stop & target** | Stop 2 × ATR below entry; sell at +3R or at the stop. Nothing moves. | The simplest plan — a clean baseline |
| **ATR trailing stop** | Initial stop 2 × ATR; from the first day the stop is raised to 2.5 × ATR below the highest close so far. No profit target. | Lets a trend run; gives back some of the top |
| **Guardian rules** | Stop 2 × ATR and a +3R target. Once the trade has been up at least +1R, the stop moves to breakeven and then trails 2.5 × ATR below the highest close. If after 15 sessions the trade is still inside ±0.5R, it is sold at that close ("time stop"). | Exactly what the Position Guardian on the Portfolio page tells you to do |
| **Hold N sessions** | Stop 2 × ATR for safety; otherwise sell at the close of the 20th session. | A control — if the smart exits cannot beat "just hold 20 days", they are not adding anything |

**How every trade is filled (the conservative assumptions):**
1. Signal at today's close → buy at **tomorrow's open**, plus 0.1% slippage.
2. Each session, the **stop is checked first**: if the session *opens* at or below the stop, the fill is the open (a gap — reason "stop gap"); if the session's *low* touches the stop, the fill is the stop price (reason "stop"). Only if the stop survives is the *high* checked against the target (reason "target"). When both would have been hit in one session, the stop wins.
3. Trailing stops, breakeven moves and time stops are evaluated on the **close**.
4. 0.1% slippage is taken off every exit and a fee (0.25% per side by default — the per-side fee setting in your configuration) is charged on both the buy and the sell.
5. One position at a time. Equity is marked to the close every session, so the equity curve shows the dips inside a trade, not only the finished trades.
6. If the window ends with a position still open, it is **not** counted in the statistics; it is reported separately.

**What the buttons do**

| Button | What happens |
|---|---|
| **`Run`** | One entry rule + one exit rule on one stock → verdict, metric cards, equity curve, trade list (6.4). |
| **`Compare exits`** (hover text "Same entries, all four exit styles") | Same entries, all four exit styles, ranked by average R (6.5). |
| **`Stop sweep`** (hover text "Try stops from 1× to 4× ATR") | Same rule pair with the initial stop at 1, 1.5, 2, 2.5, 3 and 4 × ATR (6.6). |
| **`Run on universe`** (hover text "The same rule on every stock in the universe (~1 min)") | The selected rule pair on every stock in the chosen universe — about a minute (6.7). Does not need a Symbol. |
| **`Replay my positions`** (hover text "Your open positions under the Guardian's rules vs what actually happened") | Each of your open positions since its entry date, under the Guardian's rules, next to what holding has actually done and what EGX30 did (6.8). Uses no form fields. |

`Run`, `Compare exits` and `Stop sweep` stop with the notice **"Enter a symbol"** when the Symbol box is empty. Any run on a stock with fewer than 120 sessions of daily history fails with a red box — "Backtest failed: not enough daily history for XYZ (n bars)" (or "Compare failed: …" / "Stop sweep failed: …" for the other two buttons).

**How to benefit from it**
- **This is where you find out whether your plan has an edge on the stock you are about to buy.** Before taking a Squeeze or Volume-Breakout signal from the Screener, put the stock here with the matching entry rule and `Guardian rules`, press `Run`, and read the verdict. If the rule lost money on this stock over two years, you are not "seeing a setup" — you are seeing the same pattern that failed before.
- Use `2 years` or longer. One year of a rule that fires a few times a year is a coin-toss of a sample; the page will say "(few)" and paint the verdict amber.
- Test with **your** capital. The default is your account size for a reason: position sizes, fees and the "not enough cash" cap all depend on it, and a 1%-risk position on a 50,000 EGP account looks very different from one on 1,000,000.
- Compare the four entry rules on the same stock. Some names only break out cleanly from squeezes; others trend so smoothly that "Three rising closes" is the only rule that ever fires. That tells you which scanner to trust for *this* name.
- Remember what the engine cannot see: EGX price-limit bands, illiquid opens, and the extra TradingView fields the live scanners use. The rules here are faithful approximations of the scanners, not copies. A good result is a green light to *look*, not a guarantee.

---

### 6.4 Result — `Run` (single rule pair)

**What it is** — The result of one entry rule + one exit rule on one stock. While it runs the box says "Testing squeeze_breakout + guardian on COMI…".

**What you see**

*Verdict box* — a bordered paragraph at the top. **Green border** when the run has at least 20 trades; **amber border** when it has fewer. It always follows the same shape, for example:

> "On COMI from 2024-09-01 to 2026-08-31, 'Bollinger squeeze breakout' with 'Guardian rules' exits made 14 trades, won 43%, averaged +0.31R per trade, and turned 100,000 into 108,420 EGP after fees (+8.4%). Over the same window just holding COMI returned +21.5% and EGX30 returned +18.2%. The worst peak-to-trough drop in account value was 6.3%. Only 14 trades: the true win rate could be anywhere between 17% and 69%. Treat this as a sketch, not evidence. Winners paid for losers 1.6 times over."

The possible closing sentences (only when there are at least 5 trades): "There were no losing trades at all." · "Losses dwarfed the gains — this rule lost money on this stock." (profit factor below 0.5) · "Winners covered only 0.7 of every 1.0 lost." (below 1.0) · "Winners paid for losers 1.6 times over." (1.0 or more).

If the rule never fired: "On COMI from … to …, the 'Bollinger squeeze breakout' rule never triggered a trade. Either the setup did not occur or the volume/trend filters were never met. Nothing to judge."

*Metric cards*

| Card | Meaning |
|---|---|
| **Trades** | Number of closed trades. Shows "(few)" after the number when under 20. |
| **Win rate** | Percent of trades that ended with a net profit, followed in brackets by the 95% range the true win rate could fall in given this many trades, e.g. "43% (17.4–68.9)". |
| **Avg R** | Average result per trade in R (1R = the money you risked to the initial stop). Green when positive, red when negative. |
| **Net result** | Final equity minus starting capital, in EGP, after fees and slippage. |
| **Total return** | The same as a percentage of starting capital. |
| **Buy & hold** | What simply holding the stock from the window's first session to its last returned. |
| **EGX30** | What the EGX30 index did over the same dates (from Yahoo's ^CASE30, or an equal-weight proxy of the EGX30 stocks when that is unavailable). |
| **Max drawdown** | The worst peak-to-trough fall in account value, marked to the close every session. |
| **Profit factor** | Total money won divided by total money lost. Shows "no losers" when there were no losing trades. |
| **Exits** | How the trades ended, e.g. "stop 6 · target 4 · time stop 3 · stop gap 1". |

*Open position note* — if the window ends inside a trade: "One position is still open at the end of the window: entered 2026-08-12 @ 71.3, marked 74.1 (0.85R, not counted in the stats above)." (The R figure here carries no plus sign; a loss shows as a negative number.)

*Equity curve* — a teal-green line of account value, one point per session.

*`Trades` table* — newest first, sortable by clicking any header:

| Column | Meaning |
|---|---|
| **Entered / Entry** | Date and fill price of the buy (next open after the signal, plus slippage). |
| **Exited / Exit** | Date and fill price of the sell. |
| **Why out** | Badge: **green** "target"; **red** "stop", "stop gap" and "time stop" (any reason containing the word stop is painted red); **amber** "time" (the `Hold N sessions` exit). |
| **Sessions** | Sessions held. |
| **Peak R** | The best the trade ever looked, at a close, in R. |
| **R** | The final result in R after fees. |
| **Net PnL** | The result in EGP after fees. |

*Footnote* — the exact assumptions used, e.g. "Fees 0.25%/side · slippage 0.1% · 1% of equity risked per trade · stop 2×ATR · trail 2.5×ATR · target 3R · time stop 15 sessions. Yahoo daily closes, not dividend-adjusted."

*`Full payload`* — an expandable block with everything else: median, best and worst R, expectancy per trade in EGP, average sessions per trade, final equity, **CAGR** (the yearly growth rate the total return works out to, shown only for windows longer than about 2½ months), win/loss counts, and the date range actually tested.

**What the buttons do** — Click a table header to sort; click again to reverse. Open `Full payload` to see the extra numbers. Press `Run` again after changing any dropdown to overwrite the result.

**How to benefit from it**
- **Read in this order: Trades → verdict → Avg R → Max drawdown.** If Trades is under 20 you are looking at a sketch; take the direction (does the rule broadly work on this name?) and ignore the decimals. The bracket after Win rate shows why: "43% (17–69)" means the true win rate could be anything from terrible to excellent.
- **Avg R is the number that decides.** A positive Avg R with a win rate under 50% is normal and healthy for a breakout rule — the winners are bigger than the losers. A negative Avg R with a high win rate means the stops are too loose relative to the targets: walk away from that pair.
- **Compare Total return against Buy & hold and EGX30.** In a strong bull run, holding often wins on return — that is fine *if* the rule's Max drawdown is far smaller. What you are buying with a rule is a shallower worst-case, not always a higher return. If the rule loses on return *and* has a similar drawdown, holding was simply better.
- Look at **Exits** and **Peak R** together. Many "stop" exits with Peak R above +1R mean trades were working and then given back — try `ATR trailing stop` or check the `Stop sweep`. Many "time stop" exits mean the setup on this name drifts rather than moves — probably not a stock for breakout entries.
- Check the trade list for **one trade carrying the whole result.** If a single +6R trade is the difference between profit and loss, the rule did not work — one lucky day did.
- Do **not** conclude that a rule that made +30% here will make +30% next year, or that a rule that lost on one stock is broken everywhere. One stock over two years is one draw from a noisy distribution; use `Run on universe` (6.7) to see the distribution.

---

### 6.5 Result — `Compare exits`

**What it is** — The same entry rule, the same stock, all four exit styles side by side, so you can see which way of getting *out* pays on this name. The box says "Comparing exit styles on COMI…" while it works.

**What you see**

*Summary box* — e.g. "On COMI, 'Bollinger squeeze breakout' entries paid best with 'Guardian rules' exits: +0.45R average over 12 trades (+9.3% total)." When the best row has fewer than 20 trades it adds "Few trades — the ranking could flip with one more winner or loser." and the border is amber. If the entry never fired: "'Bollinger squeeze breakout' never triggered on COMI in this window."

*Table* — one row per exit style, **ranked by Avg R**; the winner is shown in bold with a ★:

| Column | Meaning |
|---|---|
| **Exit style** | Fixed stop & target / ATR trailing stop / Guardian rules / Hold N sessions |
| **Trades** | Closed trades (the same entries can produce different counts because exits free up the single slot at different times) |
| **Win %** | Net winners as a percent |
| **Avg R** | Average result per trade in R |
| **Per trade (EGP)** | Average net profit per trade in EGP (expectancy) |
| **Profit factor** | Money won ÷ money lost |
| **Total %** | Total return on capital |
| **Max DD %** | Worst peak-to-trough fall |
| **Avg sessions** | Average holding time |
| **How trades ended** | e.g. "stop 5 · target 4 · time stop 2" |

Then a `Full payload` expander. Failure shows "Compare failed: …".

**What the buttons do** — Sort by any column. Press `Compare exits` again after changing the entry rule or period. (The Exit rule dropdown is ignored here — all four are run.)

**How to benefit from it**
- **This is how you decide whether to follow the Guardian's exits blindly or adapt them for a stock.** If `Guardian rules` is on top or close to it, keep doing what the Portfolio page tells you. If `ATR trailing stop` wins by a wide margin with far more "target"-less big winners, the stock trends longer than a +3R target allows — consider trailing instead of taking profit at 3R on that name.
- **If `Hold N sessions` wins, the exits are not adding value on this stock** — the entry is doing all the work and any stop is just getting hit by noise. Treat that as a reason to look at the `Stop sweep` next, not to abandon stops.
- Look at **Per trade (EGP)** alongside **Avg R**: a style can have the best R but so few trades that it earned less money overall. The one with the most EGP per trade *and* a sensible drawdown is the one you can actually live with.
- Watch **Avg sessions**: a style that holds for 40 sessions ties up your single position slot for two months. On a small account, a slightly worse R that recycles capital faster can be the better choice.
- Do **not** switch exit styles because of a ranking built on 8 trades. The summary warns you exactly when that is the case.

---

### 6.6 Result — `Stop sweep`

**What it is** — The selected entry and exit rules run six times with the *initial* stop at 1, 1.5, 2, 2.5, 3 and 4 × ATR, to show how tight a stop can be before normal EGX daily noise takes you out. The box says "Sweeping stop distances on COMI…" while it runs.

**What you see**

*Summary box* (always amber — a sweep is by nature a search that flatters the winner): e.g. "On COMI the best stop distance was 2 x ATR (about 4.1% at today's volatility): 48% wins, +0.30R average. Tighter stops get shaken out by normal daily range; looser ones give back too much." Or "No trades triggered at any stop distance." The "best" stop is the one with the highest average profit per trade in EGP.

*Table* — one row per stop distance; the best is bold with a ★:

| Column | Meaning |
|---|---|
| **Stop (× ATR)** | The multiple, followed by what that distance is in EGP at *today's* ATR, e.g. "2.0  ≈ 2.94 EGP ★" |
| **Trades** | Closed trades at this distance (a tighter stop frees the slot sooner, so counts differ) |
| **Win %** | Net winners |
| **Stopped out %** | Share of trades that ended at the stop (including gap fills) |
| **Avg R** | Average R per trade — note that R itself is measured against *this* stop, so 1R at 1 × ATR is half the money of 1R at 2 × ATR |
| **Per trade (EGP)** | Average net profit per trade in EGP — the fairest column for comparing rows |
| **Total %** | Total return |
| **Max DD %** | Worst drawdown |

Then a `Full payload` expander. Failure shows "Stop sweep failed: …".

**What the buttons do** — Sort by any column. Change the Entry or Exit rule and press again to sweep a different pair (the sweep honours whichever exit rule is selected).

**How to benefit from it**
- **Use this to sanity-check the stop the Stock page proposes.** The app's plans use 2 × ATR. If the sweep shows 1 × and 1.5 × with "Stopped out %" near 80–90% and negative Avg R, that is the proof that a tight stop on this stock is a donation to the market — do not tighten below 2 × ATR because a loss "feels" too big. Reduce share count instead.
- **Look for a plateau, not a peak.** If 2, 2.5 and 3 × ATR all show similar EGP per trade, the rule is robust to the stop and you can pick the one whose EGP distance you can stomach. If only one distance works and its neighbours lose, the "best" stop is a fluke and the amber border is earned.
- The "≈ x EGP" figure next to each row is today's ATR times the multiple — the actual distance you would put below an entry made today. Multiply it by your planned share count to see the money at risk, and compare with the 1% figure the Portfolio page allows.
- **Compare Per trade (EGP), not Avg R, across rows.** R is relative to the stop, so a wide stop mechanically shrinks the R numbers while risking the same 1% of equity.
- Do **not** treat the ★ as a setting to copy. A sweep picks the best of six on one price history; expect the winner to look worse next year. Its job is to rule out the distances that clearly fail.

---

### 6.7 Controls — `Universe` and `Run on universe`

**What it is** — The selected entry + exit rule run on **every** stock in `EGX30`, `EGX70` or `EGX100` (up to 101 names), so you see a distribution of outcomes instead of one lucky chart. The box says "Running squeeze_breakout + guardian on every EGX30 stock — about a minute…" while it works — it really does take about a minute, longer for EGX100.

**What you see**

*Summary box* (amber when the pooled trade count is under 20): e.g. "'Bollinger squeeze breakout' with 'Guardian rules' exits across 31 EGX30 stocks over 2y: it traded on 24 of them, 187 trades in total, 46% winners, +0.22R average. Median stock result +4.1% (best +38.2%, worst −11.6%); it beat simply holding the stock on 11 of 24. A rule that only works on a handful of names is curve-fitting; this one does not." The last words are "looks broad." when the rule beat holding on at least half the stocks it traded, otherwise "does not." If no stock produced a trade: "'…' triggered no trades across 31 EGX30 stocks." (The app's EGX30 list holds 31 names, EGX70 70 and EGX100 101; the count in the sentence is the number that had enough history.)

*Metric cards*

| Card | Meaning |
|---|---|
| **Pooled trades** | All trades across all stocks added together |
| **Pooled win rate** | Winners as a percent of the pooled trades |
| **Pooled avg R** | Average R across the pooled trades |
| **Median stock result** | The middle stock's total return — half the stocks did better, half worse |
| **Beat buy & hold** | "11 of 24" — how many traded stocks the rule beat holding on |

*Table* — one row per stock, sorted by the rule's return, best first; **click a row to open that stock's page**:

| Column | Meaning |
|---|---|
| **Symbol** | The stock |
| **Trades / Win % / Avg R** | As in 6.4, for this stock alone |
| **Rule %** | The rule's total return on this stock |
| **Buy & hold %** | Holding the stock over the same window |
| **Max DD %** | Worst drawdown on this stock |

Stocks with fewer than 120 sessions of history are skipped (the count is in `Full payload`). Failure shows "Universe run failed: …".

**What the buttons do** — Pick a universe in the `Universe` dropdown, then press `Run on universe`. The Symbol box is ignored. Click any row to jump to the Stock page.

**How to benefit from it**
- **Run this once for each entry rule you actually trade, and keep the verdict in mind for months.** It answers the question a single-stock test cannot: is the Squeeze scanner's trade an edge on Egyptian stocks in general, or does it just happen to have worked on the one name you looked at? "Looks broad." with a positive pooled Avg R over 100+ trades is real evidence; "does not." means the rule is being carried by a few names.
- **Pooled avg R is the most reliable single number on this whole page**, because it is the only one built from enough trades. If it is negative, no amount of good single-stock results should tempt you to trade that rule.
- Use the **Median stock result**, not the best. The best row is the lottery ticket you will not pick in advance; the median is what a typical name gave.
- Sort by **Trades** to find the names where the rule fires often *and* has a positive Avg R — those are the stocks to watch in the Screener for that setup. Click through to the Stock page and star them.
- Do **not** assume a rule that is broad in a bull market stays broad in a bear one; rerun with `5 years` to include a down-cycle, and rerun after any regime change in the index.

---

### 6.8 Result — `Replay my positions`

**What it is** — Every position that is currently **open** on the Portfolio page, replayed from the day you opened it under the Guardian's rules, next to what holding it has actually done and what EGX30 did over the same days. It answers "would the plan already have taken me out — and would that have been better?" The box says "Replaying your open positions under the Guardian's rules…" while it works.

**What you see**

*Summary box* — e.g. "Under the Guardian's rules, 2 of 5 open positions would already have been closed (COMI by stop, ETEL by target_3R). The others are still inside their plan." Or "No open positions to replay."

*Table* — one row per open position; **click a row to open the Stock page**:

| Column | Meaning |
|---|---|
| **Symbol / Opened / Entry** | Your position as recorded |
| **Now** | Latest Yahoo daily close |
| **Holding %** | What you are actually up or down, in percent |
| **Holding R** | The same in R, measured from your risk basis (see last column) |
| **Guardian would have…** | Badge: **green** "still holding"; **teal** "target 3R on 2026-08-20"; **red** "stop on 2026-07-14" or "time stop on 2026-08-02". A red "no history" badge appears if Yahoo has no daily data for the name (the rest of that row is empty) |
| **Plan PnL** | EGP result had you followed the plan — at the plan's exit price if it exited, otherwise marked at the latest close |
| **Holding PnL** | EGP result of what you actually did (still holding), marked at the latest close |
| **EGX30 since** | The index's move since your entry date |
| **Plan stop now** | Where the Guardian's stop would sit today (initial, breakeven, or trailing) |
| **R measured from** | "your initial stop" when you recorded a stop below your entry, otherwise "2 x ATR at entry" |

*Footnote* — "Guardian rules in the replay: stop at your initial stop (or 2×ATR at entry when it was above cost), breakeven then 2.5×ATR trail after +1R, take profit at +3R, time stop after 15 flat sessions. Prices are Yahoo daily closes."

The replay mirrors the live Guardian: stop checked on each session's low (a gap fills at the open), +3R target on the high, breakeven-then-trail once the trade has been up +1R, time stop after 15 sessions inside ±0.5R. It uses one year of daily history and does not charge fees, so PnL figures are gross. Failure shows "Replay failed: …".

**What the buttons do** — Press `Replay my positions`; no form fields are used. Click a row to open the Stock page.

**How to benefit from it**
- **Run it whenever the Guardian on the Portfolio page is nagging you and you are tempted to argue.** If a row says "stop on 2026-07-14" and Holding PnL is worse than Plan PnL, the market has already given you the answer: following the plan would have saved money. Hoping did not.
- **When Plan PnL is worse than Holding PnL, do not conclude the plan is wrong.** One position that recovered after its stop would have been hit is survivorship in action — the ones that did not recover are exactly what the stop is for. Look at the *pattern* across all rows over months, not one lucky hold.
- Use **Plan stop now** as your reference stop for the trade. If the price is sitting just above it, that is the level to watch tomorrow at 10:00; if it is far above, you have room and no reason to fidget.
- Use **EGX30 since** to separate skill from tide. A position up 8% while the index is up 12% is underperforming; a position flat while the index fell 10% is doing its job.
- "R measured from: 2 x ATR at entry" means you never recorded a stop for that position. Fix that on the Portfolio page — a position without a written stop cannot be guarded properly.

---

### 6.9 Tab — `Indicator strategies` (panel `Backtest result`)

**What it is** — The result of `Run backtest` from the setup panel: one indicator strategy on one stock. Before the first run the panel reads **'Fill the form and press "Run backtest".'** While a run is in progress it shows 'Backtesting COMI with "rsi"…'.

**What you see**

*Header line* — "COMI · rsi · 1y / 1d", then the assumptions note: "Sharpe uses EGP risk-free 25.0%/yr and EGX session annualization (245d/yr, 4.5h/d). Prices are dividend/split-adjusted where Yahoo provides adjclose."

*Metric cards*

| Card | One-line meaning |
|---|---|
| **Return** | Total percentage gain or loss on the starting capital after all costs, compounded trade by trade. |
| **Win rate** | Percent of trades that ended with a net gain. |
| **Max drawdown** | The worst peak-to-trough fall in account value, marked to every candle's close (so dips *inside* a trade count). Shown as a negative number. |
| **Sharpe** | Return above the 25% EGP risk-free rate, per unit of volatility, annualised for EGX sessions. Positive means the strategy beat a deposit for the risk it took; negative means it did not. |
| **Trades** | Number of trades. |
| **Buy & hold** | What holding the stock from the first to the last candle returned, after one round trip of the same costs. |

*Red warning* when there are fewer than 20 trades: "INSUFFICIENT SAMPLE: only 9 trades. The 56% win rate has a 95% CI of roughly ±32 points — statistically indistinguishable from luck. Do not act on these numbers."

*`Equity curve`* — account value plotted at the start and at **each trade exit** (not every session, unlike the App-rules chart). If it cannot be built: "No equity-curve series found in the backtest response." or "Equity chart unavailable: …".

*`Trade log`* — every trade, sortable by clicking a header. Columns, in the order shown: "exit price", "capital after", "capital before", "cost pct", "cumulative return pct", "entry date", "entry price", "exit date", "gross return pct", "holding days", "return pct" (the net return after costs). A trade the engine had to close at the last candle because it was still open is marked as a forced exit in `All returned fields`. If empty: "No trade log in the response."

*`All returned fields`* — an expander with the rest of the engine's output. The useful ones:

| Field | One-line meaning |
|---|---|
| **profit factor** | Total percentage gained on winners ÷ total percentage lost on losers. Above 1 the winners paid for the losers; "inf" means no losers at all. |
| **expectancy pct** | The average net return per trade in percent — what one more trade is "worth" on average. Positive is the minimum bar. |
| **calmar ratio** | Total return ÷ max drawdown — return per unit of pain. |
| **avg gain pct / avg loss pct** | Average winner and average loser in percent. |
| **best trade / worst trade** | Dates and return of the largest winner and loser. |
| **vs buy and hold pct** | Return minus Buy & hold. |
| **candles analyzed, date from, date to** | How much history was actually tested. |
| **liquidity warning** | Appears when your capital is more than 10% of the stock's 20-day median daily traded value: "Backtest deploys 100,000 EGP per trade but XYZ's 20-day median daily value is only ~600,000 EGP — real fills would move the price; results are optimistic. Consider slippage ≥0.5%/side." |

(CAGR — the yearly rate the total return works out to — is not part of this engine's output; you will find it in the App-rules `Full payload` as "cagr pct".)

*Errors* appear as a red box "Backtest failed: …" with the engine's reason, e.g. "Not enough data (18 bars). Try a longer period.", "Strategy 'rsi_pullback' needs ≥220 bars (SMA200 warmup); got 121. Use period='1y' or '2y'.", or "Failed to fetch data for 'XYZ.CA': …".

**What the buttons do** — Sort the trade log by clicking a header. Expand `All returned fields`. Change the form above and press `Run backtest` again to replace the result.

**How to benefit from it**
- **Check Trades first.** Under 20 and the red box tells you the truth: nothing here is evidence. A 6-trade strategy with a 67% win rate is four winners and two losers; flip two coins.
- **Return must beat Buy & hold, or the strategy earned nothing for the effort** — remember it went all-in on every trade with no stop, so it took *more* risk than you would, not less. If it still lost to holding, the timing rule has no edge on this stock.
- **Max drawdown is the honesty test for you, not the strategy.** Ask whether you would really have stayed in through that fall. If not, you would have quit at the bottom and the Return number is fiction for you.
- Use the **Sharpe in EGP terms** as a filter: with a 25% risk-free rate, a positive Sharpe on EGX is a genuinely good sign; a negative one says the strategy did not beat a deposit for the risk. Do not compare it to Sharpe figures quoted for US markets.
- Scan the trade log for **one trade carrying the total** and for **very short holding periods** — many one- or two-day trades at 0.8% cost each are exactly where fees eat a strategy alive.
- Do **not** size real positions from these results. This engine has no stop-loss and uses all capital; your real trades use the 1% rule and a 2 × ATR stop. Use this tab to learn a stock's character, and the `App rules` tab to test the plan you actually follow.

---

### 6.10 Tab — `Compare all` (panel `Strategy comparison`)

**What it is** — All nine indicator strategies raced on the same stock, period and costs, ranked by total return. Before the first run: **'Press "Compare all" to rank every strategy on this symbol.'** While it works: "Comparing all strategies on COMI — this can take a while…".

**What you see**

*Header line* — "COMI · 1y / 1d · 9 strategies".

*Red warning* (always shown): "Best-of-9 on ONE price history — the "winner" is systematically overestimated and should be expected to regress. Strategies with few trades are ranked on noise. Cross-check any winner with Walk-forward before trusting it."

*Table* — one row per strategy, best total return first, sortable. Columns: strategy, calmar ratio, expectancy pct, max drawdown pct, profit factor, rank, sharpe ratio, strategy label (the long name, e.g. "Bollinger Band Mean Reversion"), total return pct, total trades, win rate pct.

*`Raw response`* — expander with the winner's name, the Buy & hold return for the window, and any engine warning — on periods shorter than 220 sessions: "Strategies ['rsi_pullback', 'triple_ema'] need ≥220 bars (use period='1y' or '2y') to produce signals; their zero-trade results below are not meaningful."

Failure shows "Comparison failed: …".

**What the buttons do** — Sort by any column (sort by "total trades" first to see which rows have a sample worth reading). Expand `Raw response` for the buy-and-hold figure.

**How to benefit from it**
- **Read this as "what kind of stock is this?", not "which strategy should I run?"** If trend-followers (`ema_cross`, `supertrend`, `triple_ema`, `keltner_breakout`, `donchian`) fill the top half, the stock trends — favour the Squeeze and Volume-Breakout scanners and trailing exits on it. If `rsi` and `bollinger` are on top, it chops — breakouts on this name will fail often, and pullback entries make more sense.
- **Ignore any row with a single-digit trade count**, however good its return. Sorting by "total trades" first is the quickest way to see what is real.
- The top row is *expected* to disappoint — that is what the red warning means. Nine tries on one history guarantee that something looks good by chance. Before believing the winner, run it through `Walk-forward` (6.11) and, better, look at whether it beats Buy & hold in `Raw response`.
- Compare "max drawdown pct" across rows for the same return: two strategies with similar gains and very different drawdowns are not equally good.
- Do **not** run this on `1mo` or `3mo` — most strategies will show zero trades and the two slow ones cannot run at all.

---

### 6.11 Tab — `Walk-forward` (panel `Walk-forward analysis`)

**What it is** — The strategy from the setup panel tested on **three consecutive slices of history**, each split 70% "learn" (in-sample) and 30% "prove" (out-of-sample), to see whether what worked in one stretch kept working in the next. Before the first run: **'Press "Walk-forward" to test in-sample vs out-of-sample robustness.'** While it works: "Walk-forward testing COMI / macd…". A `1y` period is upgraded to `2y` automatically because three folds need the room. `rsi_pullback` and `triple_ema` are refused with an explanation (their 200-day average would swallow a whole fold).

**What you see**

*Header line* — "COMI · macd · 2y / 1d".

*Engine caveat* (always shown): "Engine caveat: No parameters are optimised on the train window (fixed defaults run on both slices), so this score measures regime consistency across windows, not parameter overfitting in the classical sense." In plain words: the strategy's settings are the same in every slice, so the test asks "does this rule keep behaving the same way from one stretch of history to the next?" rather than "were the settings tuned to the past?".

*Red warning* when a fold's test slice was too short for the strategy's indicators to even start: "1 fold(s) had too little data to trade — the robustness score rests on fewer folds than configured."

*`In-sample` / `Out-of-sample` cards* — shown only when the engine returns those summary blocks; with the current engine the per-window table below is what you get, and the overall figures live in `Raw response`.

*`Windows` table* — one row per fold: fold number, fold robustness score, insufficient data (yes/no), test candles / from / to, test return pct, test sharpe, test trades, train candles / from, train return pct.

*`Raw response`* — the expander holds the headline numbers:

| Field | Meaning |
|---|---|
| **robustness score** | Average over the valid folds of (out-of-sample return ÷ in-sample return), capped at 2. When both slices lost money it becomes (in-sample loss ÷ out-of-sample loss), so losing *less* out of sample scores higher. A fold whose learn slice lost money while its prove slice made money scores 0 (the engine reads the two slices as disagreeing); a fold where neither slice traded scores 1. 1.0 means the prove slice matched the learn slice. |
| **verdict** | "ROBUST — strategy performs consistently in-sample and out-of-sample" (score ≥ 0.8) · "MODERATE — some degradation out-of-sample, use with caution" (≥ 0.5) · "WEAK — significant out-of-sample degradation, likely overfitted" (≥ 0.2) · "OVERFITTED — strategy fails out-of-sample, do not trade live" (below 0.2) |
| **avg train return pct / avg test return pct** | Average return of the learn slices and of the prove slices |
| **oos total trades / win rate / sharpe / max drawdown / total return** | All the prove-slice trades pooled together |
| **scored folds / insufficient data folds** | How many folds actually counted |
| **buy and hold return pct** | Holding over the whole window, after one round trip of costs |

Failure shows "Walk-forward failed: …", e.g. "Not enough data (…) for 3 splits. Try longer period." or "Every test window is shorter than the ~50-bar warmup 'ema_cross' needs to trade at all. Use a longer period or fewer splits."

**What the buttons do** — Sort the `Windows` table; expand `Raw response` for the verdict and score. Change the strategy in the setup panel and press `Walk-forward` again.

**How to benefit from it**
- **Use it as the tie-breaker after `Compare all`.** A strategy that topped the comparison but comes out WEAK or OVERFITTED here was lucky in one stretch of history. Only ROBUST or, cautiously, MODERATE results deserve a place in how you read that stock.
- **Look at the test return in every window, not just the average.** Three folds where the prove slice was positive each time is far stronger than one huge prove slice and two losers that average out to the same score.
- **Count the out-of-sample trades ("oos total trades").** Each prove slice is only 30% of a third of the history — roughly 50 sessions on a 2-year run — so it is normal to see single-digit trade counts. A ROBUST verdict on 6 out-of-sample trades is still a small sample; the red "too little data" line tells you when a fold could not trade at all.
- Read the caveat literally: because settings are never tuned, a low score here means **the stock changed character between windows** (trend to chop, or the reverse), which is itself useful — it warns you that whatever the Screener shows on this name today may stop working when the regime turns.
- Do **not** treat "ROBUST" as permission to trade the strategy with real money — the engine still went all-in with no stop. Treat it as permission to trust the stock's *character* reading and to test the matching app rule in the `App rules` tab.

---

### 6.12 Putting it together — deciding whether to trust a setup or a stop

**To decide whether a setup is worth taking on a stock:**
1. `App rules` → the entry rule that matches the scanner signal + `Guardian rules` → `Run`, with `2 years` or more and your real capital. Read Trades, then the verdict, then Avg R and Max drawdown.
2. `Run on universe` for the same pair, once, on EGX30 or EGX70. If the pooled Avg R is negative or the summary says "does not" (look broad), the setup is not an edge on EGX — stop here regardless of how good the single stock looked.
3. If both are positive with decent samples, look at the stock's `Compare all` ranking as a character check: a trend-following top half agrees with a breakout setup; an RSI/Bollinger top half is a warning that breakouts on this name fail often.

**To decide on a stop distance:**
1. `Stop sweep` on the pair you trade. Rule out the distances where "Stopped out %" is very high and Avg R is negative — that is noise, not a plan.
2. Look for a plateau of similar "Per trade (EGP)" across neighbouring rows and choose the distance inside it that you can afford at 1% risk (the "≈ x EGP" figure × shares). If only 2 × ATR works, 2 × ATR it is — the app's default exists for a reason.
3. `Compare exits` to see whether trailing, fixed target or the full Guardian set gets the most out of that stock once the stop is right.

**What not to conclude, ever:**
- That a rule with fewer than 20 trades "works" or "does not work." It has not been tested yet.
- That the best row in any comparison or sweep will repeat. Best-of-N on one history always flatters the winner.
- That backtest returns are what you would have earned. Delayed data, price-limit bands, illiquid opens and your own nerves are not in the model; the fills here are conservative on purpose, but they are still a model.
- That a bull-market backtest says anything about a bear market. Extend to `5 years` and rerun after the index changes character.

The Backtest page cannot tell you what a stock will do. It can tell you, honestly and with the sample size in your face, what your plan *has* done — and that is the only defence against trading a pattern that has never paid.

**How to benefit from it**
- Make this a gate, not a study. Run the three-step setup check (single stock, then universe, then `Compare all`) *before* you open the Portfolio page to record a trade, never after — a backtest read after buying only ever confirms what you wanted to hear.
- Write down the two numbers that matter for each rule you trade — pooled Avg R on the universe and the trade count — and refresh them once a quarter or when the index changes character. If Avg R turns negative or the summary flips to "does not", stop taking that entry rule until it recovers, however good the individual chart looks.
- Use the `Stop sweep` plateau to size, not to tighten: choose the distance where neighbouring rows agree, then let the `Position size` card (4.15) turn that distance into a share count at 1% risk. If the count feels too small, the answer is a smaller position, not a closer stop.
- When a stock's `Compare all` ranking puts mean-reversion strategies on top, treat any breakout setup on it as a WATCH at best and demand above-average volume on the break day before acting.
- Treat every result with fewer than 20 trades as "untested" and say so in the Note when you record the position — your weekly review (8.7) should show whether those untested rules are the ones losing money.

---

## 7. Page 5 — Portfolio

**This page tracks what you actually did, watches what you hold, and watches the market for you while you are away.** Everything else in the app helps you decide what to *buy*; the Portfolio page is where the harder half of trading lives — recording the trade honestly, knowing when to sell, and finding out whether your discipline is making or losing you money.

Open it from the sidebar. Seven panels, top to bottom: **Performance**, **Position Guardian — when to sell**, **Open positions**, **New position**, **Closed positions**, **Alert rules**, **Fired alerts**. Section 7.8 explains the jobs that run in the background without you.

Two things to keep in mind on every panel:

- The app never places, changes or cancels orders. You trade at your broker; here you *record* what you did and read what the app thinks about it.
- Prices are delayed about 15 minutes, and for EGX stocks the free price feed often hands back the **last daily close** rather than a live quote. In the Guardian and Open positions tables the source of every mark is printed in small text under the price so you know how fresh it is; the footer of the page reminds you: *Analysis tooling — not financial advice. Data delayed ~15 min.*

Every money figure on this page — profit, loss, win rate, R — is **net of transaction fees**. The fee rate is per side and configurable; by default it is 0.25% per side (buy and sell), which is a typical all-in EGX retail cost (commission, stamp duty, exchange fees, risk insurance). The account size used for all percentage-of-account maths is also configurable; by default it is 100,000 EGP. Set both to your real numbers before trusting the percentages.

---

### 7.1 Panel — `Performance`

**What it is** — A row of cards summarising your whole trading record: what you have banked, what is still open, how often you win, how big your wins are compared to your losses, and how much you would lose right now if every open stop were hit at once.

**What you see**

| Card | What the number means |
|---|---|
| **Realized PnL (net)** | Profit or loss in EGP on trades you have finished — every closed position *plus* every partial sale you booked with the `−` button — after subtracting round-trip fees. Green with a `+` when positive, red when negative. |
| **Unrealized PnL (net)** | Profit or loss on the positions still open, valued at the current mark, minus the fees an exit at that price would cost. This is money you do not have yet. |
| **Win rate (net)** | Percentage of closed positions whose *net* result was above zero, to one decimal (e.g. `55.0%`). Shows `no closed trades yet` until you have closed at least one. |
| **Avg R (net)** | Average result of your closed trades measured in **R** — multiples of the risk you took at entry (entry minus your initial stop), shown as a number followed by R, e.g. `0.85R` or `-0.40R`. 1R means you made what you risked; -1R means you lost exactly your planned risk. Shows `no closed trades yet` until there is data. Trades whose initial risk is unknown (stop recorded at or above entry) are left out rather than guessed. |
| **Fees paid** | Total EGP of transaction costs on everything you have closed or partially sold (the fees stored on each trade at the time it was closed, so a later change to your fee setting does not rewrite history). Reads 0 EGP until you have closed or trimmed something. |
| **Open risk** | Total EGP you would lose if every open position were stopped out at its *current* stop, followed in brackets by the same figure as a percentage of your account — e.g. `3,450 EGP (3.5% heat)`. This is the "open heat" the New position form enforces (see 7.4). |
| **Avg R · plan followed** | Average R of closed trades where you answered "yes, I followed the plan" at close time. Only appears once you have at least one such trade. |
| **Avg R · deviated** | Average R of closed trades where you admitted you deviated from the plan. Only appears once you have at least one such trade. |

Under the cards a small grey line states the basis, word for word: `All PnL, win rate and R figures are NET of 0.25%/side transaction costs; gross figures carry a _gross suffix.` (the percentage reflects your configured fee rate). In plain words: every headline number already has fees taken out; the before-fees versions exist too, and inside the detail block below they are the entries whose name ends in the word "gross".

Below that, **`Full performance payload`** is a collapsed block you can click open. Besides the gross figures, counts of plan-followed and deviated trades, and the per-position mark details, it holds the **EGX30 benchmark note** — a one-liner comparing you with the index since your first recorded trade, in the form `Since 2026-03-02: EGX30 +4.10% · your net PnL +2,300 EGP (≈+2.30% of ACCOUNT_SIZE) as of 2026-09-02.` — `ACCOUNT_SIZE` is simply the app's name for the account size you set in your settings (by default 100,000 EGP). "Your first trade" is the earliest position you ever recorded, open or closed. Until you have trades it reads `EGX30 benchmark: no trades recorded yet.`; until the post-close job has stored at least two daily index values since your first trade it reads `EGX30 benchmark comparison needs at least 2 daily index rows since your first trade — they accumulate each post-close run.`; if the comparison itself fails it reads `EGX30 benchmark comparison unavailable (…).` The portfolio side is approximated as your total net PnL (realized plus unrealized) divided by the configured account size — the note says so rather than hiding it.

If the numbers cannot be loaded the panel shows a red box `Performance failed: …`.

**What the buttons do** — There are no buttons. The panel refreshes itself every time you open, add to, trim, close or remove a position. Click `Full performance payload` to expand or collapse the detail.

**How to benefit from it**

- **Read Avg R before Win rate.** As an illustration, a trader who wins 40% of the time but averages +0.8R per trade is profitable; one who wins 70% of the time at -0.3R is bleeding slowly. Win rate flatters; R tells the truth. Anything positive after fees is genuinely good on EGX; if Avg R is negative once you have a meaningful number of closed trades, stop adding new positions and read the Closed positions table (7.5) to find out what your losers have in common.
- **The followed-vs-deviated pair is the cheapest discipline test that exists.** If `Avg R · plan followed` is clearly higher than `Avg R · deviated`, your plan is better than your improvisation — obey it. If deviated is higher over a meaningful number of trades, your *plans* are the problem (stops too tight, targets too greedy), and the fix is on the Stock page's trade plan, not in your nerves.
- **Watch Open risk as a percentage.** The app blocks new trades that would push open heat above 6% of the account (see 7.4); treat anything approaching that as "no new positions until something is closed or a stop is raised". Raising stops on winners (7.3, `Stop` button) is the cleanest way to bring heat down without selling.
- **Fees paid is not a footnote.** On EGX, a round trip costs about half a percent of the position by default. A strategy that scalps 1% moves hands half its edge to the broker; the Fees card shows you exactly how much has already left.
- **Look at the EGX30 note once a month, not once a day.** If the index is up 10% and your net PnL is flat, you are working hard to underperform a passive holding — a signal to trade less and hold leaders longer. If you are beating it in a falling market, your stops are doing their job.
- Common mistake: judging yourself on Unrealized PnL. It is a snapshot of delayed marks, often yesterday's close. Only Realized PnL is real.

---

### 7.2 Panel — `Position Guardian — when to sell`

**What it is** — For every open position, the guardian marks the price, re-reads the daily candles since you bought, compares today's score and signal with the ones you bought on, and gives **one verdict** with every reason behind it. It is the only part of the app that answers "what do I do with what I already hold?". The grey text under the heading says it in one line: *One exit verdict per open position: stop or target reached, trailing-stop tighten, thesis broken (score/signal turned since entry), or time stop. Runs automatically every 10 min in session and after the close.*

**What you see**

When you have no open positions: `No open positions — nothing to guard. Open one below and the guardian starts watching it.`

Otherwise, four summary cards:

| Card | Meaning |
|---|---|
| **Open positions** | How many positions are being watched. |
| **Need a decision** | How many carry a critical, action or warning verdict. Shown as a red badge (`2 positions`, or `1 position` in the singular) when above zero, a green badge (`0 positions`) when nothing needs you. |
| **Critical / action / warning** | Counts by severity, e.g. `1 / 0 / 1`. |
| **Advice / hold** | Counts of advisory verdicts and plain holds, e.g. `1 / 3`. |

Then one row per position, most severe first, then by symbol. Click any row to open that stock's page.

| Column | Meaning |
|---|---|
| **Symbol** | The stock. |
| **Verdict** | A coloured badge (see the verdict table below). Red = critical, teal = action, amber = warning or advice, green = hold. |
| **Entry** | Your average entry price. |
| **Stop** | Your *current* protective stop. |
| **Mark** | The price the verdict was computed on, with its source and date underneath in small grey text — e.g. `candle close · 2026-09-02` or `snapshot · 2026-09-01`. For EGX symbols this is very often a daily close, not a live tick. |
| **R now** | Current result in R (mark minus entry, divided by the risk you took at entry). Green when positive, red when negative. |
| **Peak R** | The best R the trade reached since entry, measured on the highest daily close after the entry date (or the current mark, if that is higher). If Peak R is +2.1 and R now is +0.4, you have given back most of a winner. |
| **Suggested stop** | Filled only for a TIGHTEN STOP verdict — the level the guardian thinks your stop should move up to. Empty otherwise. |
| **Sessions** | Number of daily candles completed after the entry date — the trading days you have held through, not counting the day you bought. |
| **Why** | Every reason that applied, in plain sentences, one per line. |

Under the table, a grey basis line: `Advisory only. Marks may be daily closes (see mark_source); trailing levels use 14-day ATR on Yahoo daily candles; thesis checks compare the latest post-close snapshot with the score at entry.` — "mark_source" is the app's name for the small grey text under the `Mark` column in the `Open positions` panel (7.3), i.e. whether the price used was a live quote, a daily candle close or a stored snapshot. Then a collapsed **`Full guardian payload`** with every stored detail (score at entry and now, ATR, highest close since entry, days held, the thresholds in force).

If the check cannot run: `Guardian failed: …`.

**The verdicts and the exact rule behind each** (most severe first; when several apply, the position gets the most severe one and *all* the reasons are listed):

| Verdict (as shown) | Severity | Fires when | The guardian's own words |
|---|---|---|---|
| **EXIT STOP** | critical | The mark is at or below your current stop. | `Mark 44.90 is at/below your stop 45.20 (-1.05R). The plan you wrote at entry says exit — hoping is not a plan.` |
| **TRAIL EXIT** | action | The trade had already reached at least +1R on a closing basis, and the mark is now at or below the trailing level (highest close since entry minus 2.5 × the 14-day ATR by default). Not raised if EXIT STOP already applies. | `Price has given back more than 2.5xATR (0.85) from its post-entry high 52.10 (peak +2.40R, now +0.90R). The trailing exit says the move is over; take what is left.` |
| **TARGET2 HIT** | action | The mark is at or above Target 2. | `Mark 53.00 is at/above target 2 (52.50). Book the profit or trail a tight stop — do not let a completed trade turn into a new one.` |
| **TARGET1 HIT** | action | The mark is at or above Target 1 (and below Target 2). | `Mark 50.10 is at/above target 1 (50.00). Consider taking a partial and moving the stop to breakeven so the rest is a free trade.` |
| **PLAN INVALID** | warning | A recorded target sits at or below your entry, or Target 2 is not above Target 1. This is a data-entry error, not a market event: the Guardian **ignores** the bad target (so a losing trade can never be reported as "target hit") and asks you to fix the record with the row's `Targets` button. Real targets on the same row are still checked normally. | `Fix this record: target 1 (6.88) is at/below your entry 7.20. A target must sit above cost, so the Guardian ignored it rather than call a loss a 'target hit'. Use the row's Targets button to enter real profit levels.` |
| **STOP TOUCHED** | warning | The low of the most recent daily candle since entry went to or below the stop, but the mark is still above it. (When the mark is a daily close, "today" here means the last completed session.) Not raised if EXIT STOP applies. | `Today's low 45.00 pierced the stop 45.20 but the close recovered to 45.80. If you hold a resting stop order, confirm whether it filled; if not, decide now whether the level still holds.` |
| **THESIS BROKEN** | warning | The latest daily snapshot signal for the stock contains SELL, **or** the composite score has fallen by 15 points or more (by default) since the score you bought on (taken from the trade plan stored at entry, else the nearest snapshot before entry). | `The reason you bought no longer holds: snapshot signal is SELL (2026-09-02); composite score fell 74 -> 56 since entry (plan). Re-read your entry note — if the setup is gone, so is the trade.` |
| **TIGHTEN STOP** | advice | The trade has reached at least +1R on a closing basis, and the trailing level (highest close minus 2.5 × ATR by default, but never below your entry price) sits **above** your current stop and below the mark. The level is shown in **Suggested stop**. Not raised when TRAIL EXIT applies instead. | `Reached +1.60R. Raise the stop from 45.20 to about 48.70 (high 50.80 minus 2.5xATR 0.85, floored at breakeven) — a winner must not be allowed to become a loser.` |
| **BEARISH EVENT** | warning | The sell checklist (below) found a **confirmed bearish event or shape within the last 3 sessions** on a stock you hold. Not raised when EXIT STOP or TRAIL EXIT already applies. | `Confirmed bearish signal 1 session(s) ago: Bull Trap at 5.91, measured target 5.10. That target sits below your stop — the chart expects the stop to be hit; leaving before it is beats waiting for it.` |
| **CHECKLIST EXIT** | warning | The sell checklist's own verdict is `exit` — thesis and weekly structure both broken, or three of six pillars against, or two against including a fresh bearish event — while the stop is intact. Not raised when EXIT STOP or TRAIL EXIT applies. | `Sell checklist says EXIT: 3 of 6 pillars say leave — thesis / daily trend, weekly structure, relative strength. Sell into strength above 3.10 if it comes, otherwise at market; the trade ends below 2.93.` |
| **TIME STOP** | advice | Held for 15 or more sessions (by default) and still inside ±0.5R, with nothing else to say. | `Held 17 sessions and still +0.20R. Dead money has a cost: the capital could be in a setup that is actually moving.` |

**The sell checklist behind every row (added 2026-09-05).** Each Guardian row now also runs a six-pillar **sell checklist** — the mirror of the buy checklist on the Stock page — and the `Exit plan` column shows its result: a badge `HOLD` (green) / `REDUCE` (amber) / `EXIT` (red), then the levels the verdict cites: `exit < 6.60` (the line that ends the trade — your stop, or a levels-based stop if you have none), `reduce @ 7.53` (where to take a partial: target 1, then target 2, else the nearest resistance), `stop → 6.95` (a stop anchored just under a tested daily or weekly support that sits between your stop and the price — when this appears the Guardian also raises TIGHTEN STOP with that level as the suggested stop) and `bear trigger 5.91` (the nearest bearish neckline above your exit line — a close below it changes the picture before the stop does). Hover the badge to read the headline sentence. The six pillars, holder's view (✓ still supports holding, ⚠ deteriorating, ✗ says leave): **Thesis / daily trend** (price vs the 20- and 50-day averages, swing structure, and the score you bought on versus today's), **Weekly structure** (10/40-week averages and the weekly low that must hold), **Relative strength** (1- and 3-month return versus EGX30 — a leader that starts lagging is fading), **Distribution volume** (share of the last 20 sessions' volume traded on down days), **Bearish events** (confirmed bearish events and shapes, with the level each one names), **Exit plan** (stop distance in ATR, structure stop, and the partial-exit ladder from your own targets). Verdict rule: `exit` when thesis and weekly both fail, or three pillars fail, or two fail including a fresh bearish event, or the mark is at/below the stop; `reduce` when one or two fail or target 1 is reached; otherwise `hold`. **Ladder:** when target 1 is hit the reason text spells it out — `Exit ladder: sell 50% (1,716 shares) at market ~13.15; move the stop to 12.60 (under structure); let the rest run to 13.55 (target 2).` The Telegram message carries a `Levels:` line with the same three numbers.
| **HOLD** | ok | None of the above. | `Stop intact, no target reached, thesis unchanged — nothing to do. Doing nothing is a decision too.` |

Four special reasons can appear on any row: `No price available for this symbol (Yahoo and snapshots both empty) — verdict cannot be computed; check the position manually.` (the row is shown as HOLD because nothing can be judged); `Daily history unavailable (…) — trailing-stop and time-stop checks skipped.` when the candle download failed; `No daily snapshot exists for MENA (it was outside the scanned universe), so the thesis check — score and signal since entry — could not run. Held stocks are now snapshotted at every close; this fills itself from the next session.` when the stock has never been in a post-close snapshot (every snapshot now adds your open positions and watchlist to the EGX100 universe, so this disappears after one close); and `Initial risk is unknown (the stop was recorded at/above cost), so R multiples and the trailing-stop logic are unavailable. Use the row's Stop button and enter the stop you actually had at entry to restore them.` for a winner recorded with its stop already above cost — the `Stop` button asks for that original stop once (see 7.4).

The three thresholds are configurable: the ATR multiple (2.5 by default), the score drop that counts as a broken thesis (15 points by default) and the number of sessions before a time stop (15 by default).

**What the buttons do**

- **`Run & notify`** (top right; hover text: "Persist today's verdicts and push actionable ones to Telegram") — runs the guardian right now, **stores** today's verdicts, and pushes every critical / action / warning verdict to Telegram. Advice and hold verdicts stay in the app. Each position is pinged **once per verdict per day** — a standing breach does not spam you, and pressing the button twice does not re-send. On success a green message: `Guardian ran — 2 position(s) need a decision, 2 pushed to Telegram` (the Telegram part is omitted when nothing was sent or Telegram is not configured). On failure: `Guardian run failed: …`. The Telegram message reads like `[Guardian] COMI #12: TIGHTEN_STOP`, then the mark and its source, your R, the suggested stop if any, the first reason, and `Your entry note: "…"`.
- Without pressing anything, the panel still evaluates **live** every time the page loads or refreshes — but a page load does not store verdicts or send Telegram. The background jobs (7.8) do store and notify: every 10 minutes during the session and again after the close, once the day's snapshot is in, so the thesis check sees today's score.
- Click a row to jump to the stock's page. Click any column heading to sort the table by that column (click again to reverse; a small ▲ / ▼ marks the sorted column) — the default order is most severe first.

**How to benefit from it**

- **Why it exists:** every study of retail traders finds the same asymmetry — losers are held too long and winners are cut too early. A written stop you then ignore is worse than no stop at all. The guardian simply reads your own plan back to you every day and refuses to let you forget it.
- **Make this the first thing you read at 15:05 and the last thing before 10:00.** The post-close run at 15:00 has the fresh score, so the verdict you see in the evening is the one to act on at tomorrow's open. Anything in red or teal is an order to place; anything amber is a question to answer before the bell.
- **EXIT STOP is not a discussion.** The stop in that row is the one *you* wrote when you were calm and had no position. If the mark is below it, you sell at the open, then press `Close` (7.3) and record whether you followed the plan. If you find yourself arguing with this verdict, that is exactly the moment the followed-vs-deviated cards in 7.1 were built for.
- **TIGHTEN STOP is free money protection.** Press the `Stop` button on that row in Open positions and type the Suggested stop (or higher). Your R-multiples keep measuring against the original stop, so raising it never flatters your stats — it only cuts the amount you can give back. A trade that reached +1.6R and closes at −1R is the most avoidable loss in trading.
- **TARGET1 HIT pairs with the `−` button.** Sell part (a third or a half) at your broker, record it with `−`, then raise the stop to at least your entry. The rest of the trade is then risk-free before fees.
- **THESIS BROKEN means re-read the Why column, not the price.** If your note said "breakout above 50 with the sector leading" and the signal is now SELL with the score down 20 points, the setup is gone regardless of whether you are up or down 2%. Sell or, at minimum, tighten the stop to the most recent swing low.
- **STOP TOUCHED is a broker question first.** If you left a resting stop order, check whether it filled — the app cannot know. If it did not, decide *today* whether the level still holds; do not wait for tomorrow's low to answer for you.
- **Do not fight TIME STOP with hope.** Fifteen sessions inside half an R is capital doing nothing while the Screener page (Leaders, Setups) is showing you stocks that are moving. Advisory, yes — but the opportunity cost is real.
- **Watch Peak R against R now even on HOLD rows.** A large gap means a winner is being given back; the guardian will not flag it until the trailing level breaks, but you may prefer to tighten earlier on a stock that has run far above its average range.
- Common mistakes: treating a daily-close mark as a live price (check the source under Mark); ignoring the Why column and reacting to the badge alone; and lowering a stop after a STOP TOUCHED because the close recovered — that is how a small loss becomes a large one.

---

### 7.3 Panel — `Open positions`

**What it is** — Your live trades, one row per position, with current marks and every action you can take on a position: add shares, sell part, move the stop, close, or erase a record entered by mistake.

**What you see**

When empty: `No open positions. Record what you hold in "New position" below — symbol, shares and your fill price are enough.`

Otherwise a table (click a row anywhere except a button to open the stock's page; click a column heading to sort, click again to reverse):

| Column | Meaning |
|---|---|
| **Symbol** | The stock, in bold. |
| **Shares** | How many you hold in this row (whole number). |
| **Avg entry** | Your average purchase price. If you added shares with `+`, this is the blended average. |
| **Mark** | The latest price the app could find, with its source in small grey text underneath (e.g. `candle close`, `yahoo quote`, `snapshot`). Shows `—` when no price is available anywhere. The marks come from the same refresh that fills the Performance cards, so if Performance shows a red error this column shows `—` too. |
| **Unrealized** | Profit or loss in EGP at the mark, **net of the round-trip fees an exit there would cost** — green with `+`, red when negative. Under it, the simple percentage change from your entry (before fees). `—` when there is no mark. |
| **R now** | (Mark − entry) ÷ (entry − *initial* stop). Green/red. Shows `n/a` when the initial risk is unknown — hovering explains: `Initial risk unknown (stop at/above entry)`. |
| **Stop** | Your **current** protective stop. If you have moved it since entry, a small `was 45.20` appears underneath showing the stop at entry — hover: `Stop at entry — R is measured against this`. |
| **Targets** | Target 1 / Target 2, e.g. `50.00 / 52.50`; a missing target shows as `—`. |
| **Since** | The date you opened the position. |
| **Why** | Your entry note, shortened to about 70 characters. Hover to read all of it. `—` if the note is empty (which cannot happen for positions opened through this form — a note is required). |

If the table cannot load: `Positions failed: …`.

**What the buttons do** — Five small buttons at the end of every row. Success messages appear as green pop-up toasts; risk warnings appear as red toasts beginning with `⚠`; a failed request shows `Buy failed: …`, `Sell failed: …`, `Stop update failed: …`, `Close failed: …` or `Remove failed: …` with the reason.

**`+` (buy more — hover text: "Buy: bought more shares — blends your average entry")**
1. A pop-up asks `How many shares did you BUY?` under a line like `COMI (#12) — holding 500 @ avg 47.10`. Cancel does nothing. A non-positive number is rejected: `Quantity must be a positive number`.
2. A second pop-up asks `Buy price per share for 200 × COMI:`, pre-filled with the current mark (or your entry if there is no mark). A bad price is rejected: `Invalid price`.
3. The app recomputes your average entry — (old shares × old average + new shares × new price) ÷ total shares — and records the buy in the fill journal. **Stop, targets and the initial stop are not changed.**
4. Confirmation: `Bought 200 × COMI @ 46.50 — now 700 shares @ avg 46.93`.
5. Possible red warnings after a buy: `Averaging DOWN: bought at 46.50 below your 47.10 average. Adding to a loser is the most expensive habit in trading — make sure the setup, not the price, is the reason.` and, if your total open risk now exceeds the cap, `Open heat is now 7.2% of the account — above the 6% cap. Consider trimming somewhere.` (a buy is warned, never blocked — the shares are already bought).

**`−` (sell part — hover text: "Sell: sold part of the position — realizes PnL on those shares")**
1. Pop-up: `How many shares did you SELL?` with the same holding line. If you type more than you hold: `You only hold 500 shares`.
2. Pop-up: `Sell price per share for 200 × COMI:`, pre-filled with the mark.
3. If the quantity equals your whole holding, a confirmation appears: `That is the whole position — it will be CLOSED at 49.80. Continue?` — OK closes the position exactly like the `Close` button but **without** the plan question, so its `Plan followed` cell in Closed positions stays `—`; Cancel aborts. If you want the plan question answered, use `Close` instead.
4. Otherwise the app books the profit or loss on the sold shares, net of round-trip fees at your average entry, leaves the remaining shares at the same average, and adds the result to **Realized PnL (net)** immediately.
5. Confirmation: `Sold 200 × COMI @ 49.80 — realized 493.50 EGP net (1.30R), 300 shares left` (the R part is omitted when the initial risk is unknown). If the whole position was closed: `Position closed at 49.80 — net PnL 1,240.00 EGP`.

**`Stop` (hover text: "Move the protective stop (act on a TIGHTEN_STOP verdict)")**
1. Pop-up: `New protective stop for COMI (#12)` then `Current stop: 45.2 · entry: 47.1 · initial stop: 45.2` then `R multiples keep measuring against the initial stop.` Pre-filled with the current stop. A non-positive value is rejected: `Invalid stop`.
   - If the row has **no initial stop** (you recorded a winner with its stop already above cost, so `R now` shows `n/a`), a second pop-up follows: `R multiples for ISPH are n/a because the stop was recorded above cost. What protective stop did you have AT ENTRY (below 11.65)?` Type the stop you actually had when you bought and R multiples come alive for that position; leave it empty to skip. It must be below your entry and is recorded **once** — it is the risk you took, not a number to tune later.
2. The current stop is updated; the **initial stop is never touched**, so R now, Peak R and the closed-trade R keep measuring the risk you actually took at entry. Raising a stop can never inflate your statistics.
3. Confirmation: `Stop for COMI set to 48.70`.
4. Possible warnings: `Stop LOWERED from 45.20 to 44.00. Widening a stop after entry is the classic way a small loss becomes a large one — make sure this is a plan, not a hope.` and `Stop 48.70 is at/above entry 47.10: the trade is now risk-free (before fees/gaps).`

**`Targets` (hover text: "Edit target 1 / target 2 (both must be above your entry)")**
1. Pop-up: `Targets for MENA (#4) — entry 7.2` then `Type target1, target2 separated by a comma (or one value for target1 only).` Pre-filled with the current targets.
2. Both must be **above your entry** and Target 2 above Target 1; otherwise the app refuses: `target1 6.88 must be above your entry 7.20 — a target at/below cost is not a profit level.` The same rule now applies when you open a position with typed targets — a target at or below cost is rejected up front, because the Guardian would otherwise report a loss as a target hit.
3. Confirmation: `Targets for MENA updated`. This is how you clear a **PLAN INVALID** verdict.

**`Close` (red outline)**
1. Pop-up: `Exit price for COMI (#12):` followed, if you wrote one, by `Your entry note:` and the note in quotes — the app deliberately reads your reason back to you at the moment of exit. **The box is pre-filled with your average entry price, not the current mark** — always type your real exit price over it. Cancel does nothing; a bad price is rejected: `Invalid exit price`.
2. A second pop-up asks the one journaling question that matters: `Did you follow the plan on this trade?` / `OK = followed the plan · Cancel = deviated`. Your answer is stored and feeds the `Plan followed` column (7.5) and the two `Avg R · …` cards (7.1).
3. The position moves to Closed positions with its exit, fees, net PnL and R-multiple. Confirmation: `Position closed — net PnL 1,240.00 EGP (1.30R)` (the R part is omitted when the initial risk is unknown), with ` — recorded as plan deviation` appended when you pressed Cancel on the plan question.

**`×` (remove — hover text: "Remove: erase a record entered by mistake (duplicate / typo). Not a sale.")**
1. Confirmation: `Remove this record?` then `COMI #12 — 500 shares @ 47.10` then `This erases the row as if it was never entered (for duplicates and typos). It is NOT a sale — if you actually sold, use Close or − Sell instead.`
2. On OK the row, its fill journal and its stored guardian verdicts are deleted; nothing is booked to Realized PnL. Confirmation: `Removed COMI #12`.
3. The app **refuses** to remove a row that already has partial sales recorded (`Remove failed: this position has partial sales journaled — removing it would erase realized PnL. Close it instead, or remove the fills first.`), because that would silently erase real profit or loss.

**How to benefit from it**

- **Record every fill the same day**, at the real price, including the ugly ones. Memory lies — it remembers the winners and quietly edits out the losers; a written record is the only way to find out whether your instincts actually work. The guardian can only protect a position it knows about, and the Performance cards are only as honest as the rows here. A holding you "forgot" to log is the one that will hurt you.
- **Use `+` for adds, never a second row.** Two rows for the same stock double-count the holding and the open heat. If you do try, the New position form warns you (see 7.4). Adding *above* your average into strength is a legitimate pyramid; adding *below* it is averaging down — the app warns because it is, statistically, the most expensive habit in retail trading.
- **Use `−` to take partials at Target 1**, then `Stop` to move the stop to at least breakeven. The realized part lands in Performance straight away, so you see exactly what the partial was worth in R.
- **Check the `was …` line under Stop on every winner.** If a trade is +1R or better and there is no `was`, you have not raised the stop yet — go do it. If R now is far below Peak R (Guardian panel), you have already given back too much.
- **Before pressing `Close`, read the note the pop-up shows you.** If you are closing for a reason that has nothing to do with the note ("it dipped", "I got nervous", "I need the cash"), answer the plan question honestly with Cancel. Lying to the journal is the only way to make it useless.
- **`×` is for typos only.** If you sold, use `−` or `Close`. Erasing a losing trade to keep the win rate pretty destroys the one dataset that can make you better.
- Common mistakes: reading Unrealized as banked money; forgetting that a mark labelled `candle close` or `snapshot` may be yesterday's price; pressing OK on the `Close` pop-up without replacing the pre-filled entry price with your real exit (that would record a zero-move trade); and lowering a stop with the `Stop` button after a STOP TOUCHED warning.

---

### 7.4 Panel — `New position`

**What it is** — The form that records a trade you have just made at your broker. **You only have to type three things: symbol, shares and your fill price.** Stop, targets and note are filled in from the stock's own trade plan — the same levels the Stock page shows — and you can overwrite any of them. The form also performs the risk checks that the sizing calculator can only advise about: a mandatory reason, a per-trade risk warning, a hard block on total open heat, and a sector concentration warning.

**What you see**

| Field | Required? | What happens |
|---|---|---|
| **Symbol** | Yes | e.g. `COMI`. `EGX:` prefixes are removed and the symbol is upper-cased. |
| **Qty (shares)** | Yes | The number of shares you bought. Use the number the Stock page's `Position size` card gave you. |
| **Entry** | Yes | Your actual fill price. |
| **Stop** *(auto)* | Auto-filled | Placeholder `from trade plan`. Filled the moment you leave the Symbol box, and re-filled when you enter the price (so the stop is checked against *your* entry, not the plan's). |
| **Target 1** *(auto)*, **Target 2** *(auto)* | Auto-filled | Placeholder `from trade plan`. Plan targets that are not above your entry are left blank. |
| **Note** *(auto)* | Required (auto-filled) | Placeholder `from trade plan — add your own reason if you like`. Filled with a sentence like `Auto-filled from the COMI trade plan · scenario … · score 72 · signal BUY · planned R:R 2.3 to T2.` |
| **`Open position`** button | — | Records the trade. |

**Anything you type yourself is never overwritten by the auto-fill.** Clear a field and it becomes eligible for auto-fill again.

The grey line under the form is the **plan hint**. It starts as `Type the symbol, shares and your fill price. Stop, targets and note are taken from the stock's trade plan (the same levels the stock page shows) — you can overwrite any of them.` and changes to:

- `Loading COMI trade plan…` while fetching;
- `COMI trade plan: stop 45.20 (trade plan) · T1 50.00 · T2 52.50 · score 72 · BUY · last 47.10. You can overwrite any auto-filled field.` on success — the bracket after the stop tells you where it came from: `trade plan`, `entry − 2×TradingView ATR`, or `entry − 2×Yahoo 14-day ATR`; `last` is the stock's current price (or Yahoo's last daily close when TradingView is unavailable). If the plan offers nothing at all the line reads `COMI trade plan: no levels available. You can overwrite any auto-filled field.`;
- the same line with warnings appended after a dash, for example `The plan's stop 47.90 is not below your entry 47.10 — falling back to entry minus 2×ATR.`, `Plan target 1 (46.00) is not above your entry — left empty.`, `TradingView analysis is unavailable right now (usually a 1-2 minute rate-limit pause): … Stop falls back to a Yahoo ATR; retry in a minute for the full plan (score, targets).`, or `No stop available: the trade plan has none below your entry and no ATR could be computed — enter the stop yourself.`; up to three of the Stock page's own plan sanity checks may also be echoed here;
- `Could not load a trade plan for COMI (…). Enter the stop yourself.` when the stock cannot be analysed at all.

Directly under the plan hint there is a second, always-empty grey line reserved for form messages. Nothing in this version writes to it — every result of pressing `Open position` arrives as a pop-up toast (2.9) instead — so a blank line there is normal, not a sign that something failed to load.

**How the stop fallback works, in order:** (1) the plan's stop, if it is below your entry; otherwise (2) your entry minus 2 × the 14-day ATR from TradingView; otherwise (3) your entry minus 2 × a 14-day ATR computed from Yahoo daily candles (this is what saves you during TradingView's short rate-limit pauses); otherwise (4) nothing — you must type a stop.

**What the buttons do** — `Open position`:

1. Local checks, each with its own red message: `Symbol is required`, `Qty must be a positive number`, `Entry must be a positive price`, `Stop must be a positive price`, `Target 1 must be a positive price`, `Target 2 must be a positive price`.
2. **Stop at or above entry** — a confirmation appears: `Stop 48 is at/above entry 47.1.` / `Only continue if this is an EXISTING position whose stop you have ALREADY raised above cost. The initial risk is unknown, so R multiples for this trade will show as unavailable.` / `For a NEW trade, press Cancel and enter a stop below your entry.` Cancel aborts. OK records the position with the initial risk marked unknown: R now shows `n/a`, the trade is excluded from Avg R, and a warning confirms it: `Stop 48.00 is at/above entry 47.10: initial risk unknown, so R multiples for this trade will show as unavailable. The guardian still watches the stop.`
3. If Stop or Note is empty, the app fills them (and any empty target) from the trade plan and stores the plan's score with the position so the guardian later knows what you bought on. (If you typed both a stop and a note yourself, the plan is not consulted at all.) If no stop can be found: `Open position failed: stop is required — the trade plan offers no stop below your entry; enter one yourself.`, or, when the stock could not be analysed, `Open position failed: stop is required — could not auto-fill it: …`. If the note is still empty (plan unavailable and you typed nothing): `Open position failed: note is required — record WHY you are taking this trade (setup, scanner that flagged it, planned R:R). You will re-read it at close time.`
4. **Open-heat cap (hard block).** The app adds this trade's risk (entry − stop) × shares to the risk of every open position and compares the total with your account size. If it exceeds **6%**, the trade is refused and a confirmation shows the full reason: `BLOCKED: this trade takes total open risk to 7.4% of the account (7,400 EGP of 100,000) — above the 6% open-heat cap. Reduce size, close something, or resubmit with an explicit override.` followed by `Override the cap and open it anyway?` Cancel leaves it unrecorded (`Position not opened (open-heat cap).`); OK records it with a red warning `OVERRIDDEN: open heat is 7.4% of the account — above the 6% cap.`
5. Success: `Opened 500 × COMI @ 47.10 · stop 45.20`, then an info message listing what was auto-filled, e.g. `Auto-filled from trade plan: stop 45.20 (trade plan), target1 50.00, target2 52.50, note`. The form clears, and the Performance, Guardian and Open positions panels refresh.
6. Possible red warnings after a successful open, each shown as a toast beginning with `⚠` (they do not stop the record):
   - `This single trade risks 2.50% of the account (> 2% guideline).` — per-trade risk above 2%.
   - `You already hold 500 COMI in 1 open position(s) (#12). If this is the same holding, use '+ Buy' on that row instead — a second row double-counts it. Use 'Remove' to delete a row entered by mistake.`
   - `Sector concentration: already holding 2 open position(s) in 'banks' (ADIB, COMI) — EGX sectors move together.` — appears when you already have two or more open positions in the same sector as the new stock.

**How to benefit from it**

- **Size first, record second.** Get the share count from the Stock page's `Position size` card (1% of account risk by default), buy at your broker, then come here and type symbol, shares and fill. Let the plan fill the rest, then read the hint line: if the stop source is an ATR fallback rather than `trade plan`, the plan had no sensible stop for your price — that is worth a second look before you accept it.
- **The Note is your future self's evidence.** The auto-filled sentence (scenario, score, signal, planned R:R) is a good start; add one line of your own — "breakout above 3-month base, sector leading, Setups tab 5/6". The `Close` pop-up will show it back to you, and the THESIS BROKEN verdict tells you when it stopped being true.
- **Treat the 6% block as a real wall, not a nag.** Six per cent of open heat means six simultaneous full-size losses would cost you 6% of the account in one bad week — and EGX has those weeks. Override only for a specific reason you can write down; if you find yourself overriding routinely, your position sizes are too big.
- **Take the sector warning seriously.** Three banks are one trade with three tickers. If the warning fires, either skip the trade, size it smaller, or trim one of the existing positions.
- **Never use "stop above entry" for a new trade.** It is only for recording an existing winner whose stop you already raised. For a new trade it is a typo that would corrupt your risk maths; the confirmation exists to stop exactly that.
- Common mistakes: typing the plan's ideal entry instead of your real fill; opening a second row for a stock you already hold (use `+` in 7.3); and blanking the auto-filled note to save five seconds.

---

### 7.5 Panel — `Closed positions`

**What it is** — Your trade history: every finished position with its exit price, net result, return, R-multiple, and whether you followed the plan. This is where the lessons are.

**What you see**

When empty: `No closed trades yet. When you sell, press Close (or − for part of a position) and the result lands here with its R-multiple.`

Otherwise a sortable table (click a column heading to sort, click again to reverse — a ▲ / ▼ marks the sorted column; click a row to open the stock):

| Column | Meaning |
|---|---|
| **Symbol** | The stock. |
| **Shares** | Shares closed in this row (after any partial sales, the remaining quantity). |
| **Entry** | Average entry. |
| **Exit** | The exit price you recorded. |
| **Net PnL** | Shares × (exit − entry) minus the round-trip fees stored on the trade. Green/red with sign. |
| **Return** | Net PnL as a percentage of the money you put in (entry × shares). |
| **R** | Net profit per share divided by the risk per share you took at entry (entry − initial stop). `n/a` when the initial risk was unknown. Green/red with sign. |
| **Plan followed** | Green badge `yes`, red badge `deviated`, or `—` when no answer was recorded — trades closed before the question existed, and positions closed by selling the whole holding with the `−` button (that path does not ask). |
| **Opened** / **Closed** | The dates. |
| **Why** | Your entry note, shortened to about 60 characters; hover for the full text. |

Partial sales made with `−` are **not** separate rows here — they are booked straight into Realized PnL (7.1) and kept in the fill journal; the row that eventually appears here is the final remainder of the position.

**What the buttons do** — No buttons. Sort by clicking headings; click a row to open the Stock page.

**How to benefit from it**

- **Once a month, sort by R and read the bottom five.** Ask what they had in common: against the weekly trend? Planned R:R under 2? A sector already crowded in your book? Bought on a Friday morning rumour? That pattern is your tuition fee, and this table is where you collect the lesson.
- **Then sort by Plan followed.** If your `deviated` rows are mostly red, the rule is simple: stop deviating. If they are mostly green, your plans are wrong for how you actually trade — widen the stops or shorten the targets on the Stock page, and follow *those*.
- **Compare Return with R.** A +4% return on a trade you risked 1.5% for is a fine +2.7R; a +4% return that risked 8% is a poor +0.5R and a sign your stop was too wide for the move you expected.
- **Look at holding time (Opened → Closed) against R.** If your winners are held two days and your losers three weeks, you have the classic retail asymmetry — cutting winners and nursing losers — and the guardian's TIME STOP and TIGHTEN STOP verdicts are the cure.
- Common mistake: judging a trade by Net PnL alone. A −300 EGP loss at −0.8R is a good trade that did not work; a +300 EGP gain that once stood at +3R is a bad trade that got lucky.

---

### 7.6 Panel — `Alert rules`

**What it is** — Standing instructions that make the app watch the market for you and message you (in the app, and on Telegram if configured) when a condition is met. Rules are checked every 10 minutes during the session, once after the close, and whenever you press `Evaluate now`.

**What you see** — A form at the top, and the table of existing rules below it.

The form:

| Field | Notes |
|---|---|
| **Name** | Optional (placeholder `optional`). If blank, the app names the rule after its type and symbol or universe, written with the underscore, e.g. `price_above COMI` or `squeeze EGX30`. |
| **Rule type** | A dropdown: `price above`, `price below`, `score min`, `squeeze`, `signal change`, `entry hit`. The parameter boxes change with the type. |
| Parameter boxes | See the table below. Number boxes accept decimals. Symbols are upper-cased and `EGX:` prefixes removed. Placeholders: `COMI` for a symbol; for score min, `EGX30 (or blank)` in the universe box and `or one symbol` in the symbol box. |

| Rule type | Parameters shown | What it watches | Message when it fires |
|---|---|---|---|
| **price above** | `symbol`, `level` | The stock's price at or above your level. | `COMI is 47.60 — at/above your 47.50 level (candle_close)` — the bracket names the price source exactly as the feed reports it, underscore included (`yahoo`, `candle_close`, or `snapshot 2026-09-01` for a stored close). |
| **price below** | `symbol`, `level` | The stock's price at or below your level. | `COMI is 44.90 — at/below your 45.00 level (snapshot 2026-09-01)` |
| **score min** | `universe` (e.g. `EGX30`, or blank) **or** `symbol`, `threshold` (pre-filled 70) | Any stock in the universe — or the one symbol — whose latest daily composite score is at or above the threshold. Reads the post-close snapshot, so it changes once a day. If you fill in a symbol, the universe is ignored. | `HRHO score 74.0 >= 70.0 (signal: BUY, 2026-09-02)` |
| **squeeze** | `universe` (pre-filled `EGX30`), `bbw max` (pre-filled 0.04) | Stocks in the universe whose Bollinger band width in the latest snapshot is at or below your maximum — a volatility squeeze, the coiled spring before a move. | `SWDY in Bollinger squeeze: BBW 0.0350 <= 0.0400 (2026-09-02)` |
| **signal change** | `symbol` | The stock's daily snapshot signal differing from the previous day's (e.g. BUY → NEUTRAL, or → SELL). | `COMI signal changed BUY -> SELL (2026-09-02)` |
| **entry hit** | `symbol`, `entry` | The price **crossing** your planned entry since the previous close — in either direction. Needs a real quote with a previous close; when only a stale snapshot price is available the rule stays silent rather than firing forever on a level that was crossed days ago. | `COMI crossed trade-plan entry 47.00 since previous close 46.80 (now 47.20, yahoo)` |

Universe names you can type: `EGX30`, `EGX70`, `EGX100`, `SHARIAH33`, `EGX35LV`, `TAMAYUZ`, or `ALL` for the full EGX listing. A blank universe box means `ALL`; a name the app does not recognise is treated as `EGX30`.

Price rules use the fast quote feed and fall back to the latest saved snapshot price; the source (and the snapshot's date) is always printed in the message so you know how old the price is. Every fired message is prefixed with the rule's name in square brackets, e.g. `[price_above COMI] COMI is 47.60 — …`.

The same rule and symbol will not fire again within **6 hours**, so an alert that stays true does not ping you every 10 minutes.

The rules table (click a heading to sort):

| Column | Meaning |
|---|---|
| **ID** | The rule's number (this is what the Fired alerts table shows in its `Rule` column). |
| **Name** | The name you gave, or the automatic one. |
| **Type** | The rule type in its stored form, e.g. `price_above`. |
| **Params** | The parameters in compact form, e.g. `{"symbol":"COMI","level":47.5}`; hover for the full text. |
| **Enabled** | Badge `on` (teal) or `off` (grey). Only enabled rules are checked. |
| **Created** | When you created it. |

If the list cannot load: `Rules failed: …`.

**What the buttons do**

- **`Create rule`** — validates the boxes first; problems appear as `Rule invalid: …` with one of: `symbol is required`, `level must be a number`, `provide a universe or a symbol`, `threshold must be a number`, `universe is required`, `bbw max must be a number`, `entry must be a number`. On success: `Alert rule created: price_above COMI`, the Name box clears (the parameter boxes keep their values), and the table refreshes. The rule is enabled immediately. Problems the app finds when saving show as `Create rule failed: …`.
- **`Evaluate now`** — checks every enabled rule this instant instead of waiting for the schedule. Result: `Evaluated 4 rule(s) — 1 fired`. Anything that fired appears in Fired alerts (7.7) and is sent to Telegram if configured. The 6-hour rule still applies, so a condition that already fired recently is not counted again. On failure: `Evaluate failed: …`.
- **`Disable` / `Enable`** (per row) — pauses or resumes a rule without deleting it: `Rule "price_above COMI" disabled` / `… enabled`. On failure: `Toggle failed: …`.
- **`Delete`** (red, per row) — asks `Delete alert rule "price_above COMI"?`; on OK: `Rule deleted` and both tables refresh. Deleting a rule does not erase the alerts it already fired. On failure: `Delete failed: …`.

**How to benefit from it**

- **Put your plan into rules the moment you write it.** For every stock on your watchlist with a trade plan, create an `entry hit` at the plan's entry so you are told when the price actually gets there, instead of discovering it at 16:00. For every open position, a `price below` at your stop is a second pair of eyes alongside the guardian, and a `signal change` on the symbol warns you the day the daily signal turns.
- **Use `score min` on a universe as a hands-free scanner.** `EGX30` (or blank for everything) with threshold 70 tells you each evening which names crossed into strong territory; then confirm on the Stock page's checklist before doing anything.
- **Use `squeeze` to find coiled springs early.** A band width at or below 0.04 marks a stock that has gone quiet; the move that follows a squeeze is often the tradable one. Pair a squeeze alert with a `price above` at the top of the range so you catch the breakout, not the waiting.
- **Read the source in every message.** `(snapshot 2026-09-01)` means the price is from yesterday's close — good enough for a daily-signal rule, not for a stop.
- **Keep the list short.** Ten well-chosen rules you act on beat fifty you ignore. Disable rules for stocks you no longer follow; delete the ones for trades already taken.
- Common mistakes: expecting `entry hit` to fire on a level already crossed days ago (it needs a fresh cross); putting `score min` on a single symbol and wondering why it fires once a day at most (it reads the daily snapshot); misspelling a universe name (it silently becomes EGX30); and creating a rule without ever pressing `Evaluate now` to see it work.

---

### 7.7 Panel — `Fired alerts`

**What it is** — The history of every alert that triggered — from your rules, the scheduled checks, or `Evaluate now` — newest first, the most recent 50.

**What you see**

| Column | Meaning |
|---|---|
| **Fired at** | Date and time (Cairo) the condition was met, as a full timestamp. |
| **Rule** | The ID number of the rule that fired (match it with the `ID` column in Alert rules). |
| **Symbol** | The stock. |
| **Message** | The full text, e.g. `[price_above COMI] COMI is 47.60 — at/above your 47.50 level (candle_close)`. |
| **Delivered** | Badge `telegram` (teal) when the message reached your Telegram chat, `local` (grey) when it was only recorded here — either Telegram is not configured or the send failed. |

Click a row to open the stock's page; click a heading to sort. If the list cannot load: `Fired alerts failed: …`.

Guardian verdicts are **not** listed here — they are stored separately (visible in the Guardian panel and its `Full guardian payload`) even though they also go to Telegram.

**What the buttons do** — No buttons. The list refreshes after `Evaluate now` and after deleting a rule.

**How to benefit from it**

- **Treat this as your morning inbox.** Before 10:00, read what fired since yesterday's close: entries reached, stops threatened, signals turned. Each row is a decision you deferred to the app; now make it.
- **If everything says `local` and you expected Telegram**, your bot token or chat id is missing or wrong. Fix it and press `Evaluate now` on a rule you know is true to test the delivery.
- **Use it to grade your own rules.** A rule that fires every session and never leads to a trade is noise — disable it. A rule that fired once and you missed a 15% move is the one to keep and act on faster.
- **Cross-check old alerts against Closed positions.** When an `entry hit` fired and the trade went on to hit Target 2 without you, that is the cost of not having the app open — or of not having Telegram configured.
- Old alerts are pruned automatically after 180 days by the weekly maintenance job, so export or note anything you want to keep long-term.

---

### 7.8 What runs automatically

**What it is** — Once the app is running (and background jobs are enabled, which they are by default), a scheduler works on Cairo time so you do not have to press anything. Every run is recorded, failures never crash the app, and the first failure of any job is pushed to Telegram. Weekends and Egyptian market holidays are skipped automatically — no stale data is re-stamped and no alerts are evaluated against frozen prices.

**What you see** — Nothing on this page directly; the results appear in the Guardian panel, Fired alerts, the Dashboard and the Screener tabs. On Telegram, a failed job arrives as `[EGX scheduler] job 'post_close' FAILED` followed by the error detail — sent when a job *starts* failing, not on every repetition (a day-long outage produces one message, not 27).

| When (Cairo time) | Job | What it does, in order |
|---|---|---|
| **Sun–Thu, every 10 minutes from 10:00 to 14:20** | Intraday check | (1) Evaluates every enabled alert rule and fires/sends what is due. (2) Runs the **Position Guardian** on every open position, stores today's verdicts and pushes critical / action / warning ones to Telegram — so a stop or target breach does not wait until 15:00. The once-per-position-per-verdict-per-day rule means a standing breach pings once. |
| **Sun–Thu 15:00** | Post-close pipeline | (1) Saves the daily **snapshot** of the whole EGX100 universe (price, score, signal, band width — the data every daily-signal alert and thesis check reads). (2) Stores today's **EGX30 index** value for the benchmark note. (3) Re-runs the **Candidates** scans and stores the hits. (4) Evaluates **alert rules** against the fresh snapshot. (5) Runs the **Position Guardian** — after the snapshot, so THESIS BROKEN sees today's score and signal. (6) Grades the **Scorecard** — older scanner hits are marked as winners or losers against what happened next. (7) Computes the **Leaders** relative-strength ranking of the EGX100 (top 40 stored). (8) Scans for chart **Patterns** across the EGX100; confirmed patterns become scanner hits so the Scorecard can grade them. (9) Computes the **Setups** checklist across candidates, leaders, your watchlist and your holdings. Only one copy of this pipeline can run at a time. |
| **Sun–Thu 09:30** | Morning brief | Writes the Dashboard's morning brief. Skipped unless an AI key is configured. |
| **Every hour at :07** | Catch-up sentinel | After 15:05 on a trading day, checks whether today's snapshot exists (at least 20 stocks). If the laptop was asleep or offline at 15:00 and the snapshot is missing, it runs the entire post-close pipeline now so the trading day is not silently lost. |
| **Saturday 12:00** | Weekly maintenance | (1) Prunes old records — job history older than 90 days, fired alerts older than 180 days, scanner hits older than 180 days, backtest runs older than 365 days. (2) Takes a **backup** of the app's data. (3) Probes the EGX symbol list (the first 200 symbols) and reports any that no longer return data (delisted or renamed). |

Telegram delivery for everything above needs the bot token and chat id set in your configuration; without them, alerts and verdicts are still recorded in the app and simply marked `local`. Setting the scheduler switch to off disables all of the jobs — the page still works, but you must press `Evaluate now` and `Run & notify` yourself.

**How to benefit from it**

- **Leave the app running on trading days**, at least from 09:30 to 15:15. The 15:00 pipeline is what builds the score history that makes the Guardian's thesis check, the Scorecard, Leaders, Patterns and Setups meaningful — miss it and the catch-up sentinel will try, but only if the machine is awake later that day.
- **Configure Telegram on day one.** Ten-minute intraday guardian pings on your phone are the difference between honouring a stop at 11:20 and discovering the breach at 16:00. It also tells you when a job fails, which otherwise you would only notice as a stale Dashboard.
- **Build your evening routine around 15:05:** open this page, read the Guardian verdicts computed on today's snapshot, act on red and teal at tomorrow's open, then check Fired alerts and the Screener's Setups tab for tomorrow's candidates.
- **If the Guardian's Mark says `snapshot` with an old date, or Fired alerts stop appearing**, look for a Telegram failure message and check that the app is still running — a dead scheduler is silent by design except for that one message.
- Common mistakes: closing the laptop lid at 14:45 (the 15:00 run is missed; the sentinel needs the machine awake after 15:07 to catch up); assuming an alert that fired at 10:10 will fire again at 10:20 (6-hour dedupe); and expecting daily-signal rules (`score min`, `squeeze`, `signal change`) to change during the session — they move once a day, after the 15:00 snapshot.

---

## 8. Your daily routine (how to actually use this)

The app has many cards, but a trading day only needs a handful of them, in a fixed order. This section is that order. Times are Cairo time; EGX trades Sunday to Thursday, 10:00–14:30, and the app's own post-close work runs at 15:00. Every price you see is delayed about 15 minutes (or is the last close when the market is shut), the app never places an order, and nothing below is advice — it is a way of making sure you look at the right evidence before you act at your broker.

### 8.1 The evening before, or early morning (10–15 minutes)

1. **Open the Dashboard.** Read the `% Advancing` tile and the `Session (Cairo)` tile first. If most of the market was falling, plan smaller or plan nothing. Glance at `Global snapshot` — a deep-red world strip on top of weak breadth is a stay-in-cash day.
2. **Read the `Today — what needs a decision` card, left to right, positions first.** The `Your positions` column shows every open trade whose Guardian verdict is not a plain HOLD. A red `EXIT STOP`, or a green `TARGET1 HIT` / `TARGET2 HIT` / `TRAIL EXIT`, is tomorrow's first order. Amber `TIGHTEN STOP` and `THESIS BROKEN` are questions to answer before the bell. Deal with what you hold before you look at anything new.
3. **Shop from `Best setups`.** Only the green SETUP rows (5/6 or 6/6 with nothing against them) are candidates for money. For a WATCH row, read the grey `needs …` note — that is the condition you are waiting for, and a good reason to set an alert rather than to buy. Cross-check each name against `Strongest vs EGX30` and the `Sector heatmap`: a SETUP that is also a leader in a green sector is the best combination the Dashboard produces.
4. **Check `Patterns on your stocks`.** A red `bearish` on a stock you hold is an early exit warning the Guardian may not have yet; a green `bullish` on a watchlist name is a cue to open its Stock page.
5. **Skim `Candidates`**, the stored scan from 15:00. Read the badges, not the badge count: two different families on one stock (a `squeeze` plus `smart_money`, say) is the combination to prize. `No candidates from today's scans.` is a valid answer, not a broken card.
6. **Read the `Morning brief`** if the AI key is configured (it is written automatically at 09:30). Turn its WATCH CONDITIONS into alert rules on the Portfolio page rather than into orders.

You should leave this step with **two or three names at most**. If you have eight, you have not filtered; if you have none, you have a free day.

**How to benefit from it**
- Do this step when the market is shut — the evening after the 15:00 post-close run or before 09:30 — so every stored card (Setups, Leaders, Patterns, Candidates) shows the same completed session and nothing is moving while you think.
- Positions before prospects, always. A red `EXIT STOP` or an amber `TIGHTEN STOP` on a stock you hold is worth more than any new SETUP row: protecting the money you already have at risk is the only step here that cannot wait a day.
- Use breadth as a size dial, not a switch: with `% Advancing` well under half and a red `Global snapshot`, halve the number of names you carry forward, or carry none. Strong breadth does not make a weak stock a buy, but weak breadth makes a good one wait.
- Turn WATCH rows into alert rules (`entry hit` at the trigger price, `price above` at the neckline), not into orders. The grey `needs …` note tells you exactly what has to change; let the app tell you when it does.
- If you routinely leave with more than three names, tighten the filter: keep only SETUP rows that are also in the `Strongest vs EGX30` list. Two names you research properly beat eight you skim.

### 8.2 Research each candidate (5 minutes each, on its Stock page)

7. **`Decision checklist` first.** `NO SETUP` = close the page, whatever the story. `WATCH` = star it, read the headline for what is missing, move on. `SETUP` = permission to do the rest of the work — not an order. Read the crosses and warnings before the ticks; Trend and Risk plan are the two pillars that veto a trade outright.
8. **`Support & resistance` and the chart.** Where are the walls? `AT SUPPORT` is the low-risk spot; `AT RESISTANCE` means buying into the people who sold there before — wait for the break or the pullback. Check that the plan's `stop` line on the chart sits *below* a dark-green `support xN` line, not on top of it. Compare `room up` with `room down`.
9. **`Chart patterns`.** A `forming` shape is a watchlist entry with the `Trigger / neckline` as your alert price. A `confirmed` shape is only a signal if the `Break` volume is above average and `Move done` is low — a confirmed break on quiet volume is the classic EGX false breakout. Note the `Stop hint`.
10. **`Multi-timeframe alignment`.** If the weekly tile is red and `Diverging:` names `1W`, walk away — a buy signal inside a weekly downtrend is the most common trap on this exchange. Short-frame divergence under green weekly and daily tiles is often just a better entry price.
11. **`Trade plan`.** If the red `Reject: R:R to T2 … < 2` banner is showing, skip the trade — there will be another one tomorrow. Read the amber ⚠ lines as edits: move the stop below the tested support they name, take profit a little before the tested resistance, size smaller if the stop is beyond one limit session.
12. **`Smart Money`, `News`, `Debate` — the veto tabs.** `DISTRIBUTION` while price makes highs, fresh material bad news, or a bear case you cannot answer in one sentence are each a reason to stand aside. Run the AI debate only on names that already passed the checklist; it is slow and costs an AI call.

**How to benefit from it**
- Follow the order on the page from top to bottom and stop at the first veto. `NO SETUP` in the checklist, `1W` in the `Diverging:` line, or the red `Reject: R:R to T2 … < 2` banner each end the research in under a minute — that saved time is the point.
- Two pillars, Trend and Risk plan, veto a trade outright; the other four only lower the score. Read a `✗` on Trend as "close the page", a `✗` on Volume as "wait for the break day", and do not average them into a feeling.
- Before you accept the plan's `stop`, find it on the chart. If it sits *above* the nearest dark-green `support xN` line, move your own stop just below that line and re-check R:R — a stop inside the support zone is the single most common way a correct idea loses money.
- Treat the `Smart Money`, `News` and `Debate` tabs as reasons to say no, never as reasons to say yes. A `DISTRIBUTION` phase or a bear case you cannot answer in one sentence overrides a 6/6 checklist.
- Star the WATCH names as you go (2.2); the `Patterns on your stocks` card and the Watchlist keep them in front of you tomorrow without a second search.

### 8.3 Before committing money (once per rule, and once per stock)

13. **Screener → `Leaders`.** Is the name in the top of the relative-strength table, `New high` = yes, `> SMA50` = yes? Buying strength is the single most reliable swing-trade habit. A candidate near the bottom of the Leaders table has a fresh signal on a stock the market has been rejecting for months.
14. **Backtest → `App rules`.** Put the stock in the Symbol box, choose the entry rule that matches the scanner that flagged it (Bollinger squeeze breakout, 20-day high breakout, Pullback in uptrend, Three rising closes) with `Guardian rules` exits, `2 years` or longer, and press `Run`. Read Trades, then the verdict, then Avg R and Max drawdown. Under about 20 trades the page itself tells you it is a sketch — take the direction, not the decimals.
15. **`Stop sweep`** on the same pair. If 1× and 1.5× ATR are stopped out most of the time with negative Avg R, a tight stop on this stock is a donation to the market: keep the stop at a real level and reduce the share count instead of moving the stop closer.
16. **`Run on universe`** once for each entry rule you actually trade, and remember the verdict for months. A negative pooled Avg R, or a summary that ends "does not." (look broad), means the rule is not an edge on EGX no matter how good one chart looks.
17. **Back on the Stock page, `Position size`.** Account and Risk % are pre-filled from your settings (by default 100,000 EGP and 1%); Entry and Stop are pre-filled from the checklist or the trade plan. Overwrite them with the stop you will *actually* use after the ⚠ corrections, press `Size position`, and read the amber note: the `2R target`, the round-trip fee estimate, and any `LIQUIDITY WARNING`. Never raise Risk % to make a small share count look better — a small count means the stop is too far for this stock at your account size.

**How to benefit from it**
- Split the work in two: the Backtest checks per *rule* (steps 14–16) are done once and remembered for months; only the Leaders check and the sizing (steps 13 and 17) are repeated per stock. Doing the rule checks every evening wastes time; skipping them for a new rule is how an untested idea gets real money.
- Rank order matters: a stock in the bottom half of `Leaders` with `New high` = no is a weak candidate even with a fresh signal — buy strength, or wait for the name to climb the table.
- Read the backtest verdict *with* its trade count. Fewer than 20 trades means take the direction, not the decimals; a negative pooled Avg R on the universe means stop, regardless of how the single stock looked.
- Size from the stop you will actually use after the chart and the ⚠ corrections, at the default 1% risk. If `Position size` returns a `LIQUIDITY WARNING` or a share count that looks tiny, the position is smaller — never move the stop closer to make the maths look better.
- Keep the fee estimate in mind: with fees on both sides (by default 0.25% per side), a target only 2% above entry gives away a quarter of the move to costs. That is another reason the app rejects plans with R:R under 2.

### 8.4 Placing and recording the trade

18. **Place the order with your real broker** at the planned entry, and place the stop-loss order at the same time — not "later". The app shows prices a quarter of an hour late; confirm the live quote at your broker before you enter.
19. **Portfolio → `New position`.** Type only the symbol, the shares and your real fill price. Stop, Target 1, Target 2 and the Note are auto-filled from the stock's trade plan; read the grey plan hint to see where the stop came from (`trade plan`, or an ATR fallback when TradingView was pausing), and overwrite anything you disagree with. Add one line of your own to the Note — the `Close` pop-up will read it back to you and the Guardian's `THESIS BROKEN` verdict is built on it.
20. **Respect the open-heat block.** If the app says `BLOCKED: this trade takes total open risk to … above the 6% open-heat cap`, the honest answer is Cancel. Override only for a specific reason you can write down. Take the `Sector concentration` warning the same way: three banks are one trade with three tickers.
21. **Create the alert rules that put your plan on autopilot:** an `entry hit` at the plan's entry for a stock you are waiting on, a `price below` at your stop for a stock you hold, a `signal change` on the symbol. Press `Evaluate now` once so you see a rule work before you rely on it.

**How to benefit from it**
- Record the trade within minutes of the fill, while the broker screen is still open, and type the *real* fill price — not the plan's entry. Every R figure, the Guardian's verdicts and the `Performance` cards are built on that one number; a rounded or wished-for price quietly corrupts all of them.
- Place the stop-loss order at your broker in the same sitting. The app only *tells* you when the stop is hit (once every 10 minutes during the session, and 15 minutes late); it never sells for you.
- Read the plan hint before accepting the auto-filled stop: `trade plan` means the stop is a real level; an ATR fallback means the plan had no sensible stop for your price, so check the chart and overwrite it if a tested support sits closer.
- Take `BLOCKED … above the 6% open-heat cap` and `Sector concentration` at face value: press Cancel. If you override, write the reason in the Note so the weekly review can judge whether overrides ever paid.
- Set the alert rules the same evening: `price below` at your stop for what you hold, `entry hit` for what you are waiting on. A plan without alerts depends on you watching the screen, which is exactly what step 8.5 tells you not to do.

### 8.5 During the session (Sunday–Thursday, 10:00–14:30)

22. **Let the app watch.** Every 10 minutes from 10:00 to 14:20 the alert rules are evaluated and the Position Guardian runs on every open position, storing the verdict and pushing critical, action and warning ones to Telegram once per position per verdict per day. If Telegram is not configured, `Fired alerts` and the Guardian panel are your inbox.
23. **When you come back to the screen, reload.** The `data as of` chip turning red is your cue. Then read `Fired alerts` and the Guardian panel. Act on `EXIT STOP` at your broker, then press `Close` and answer the plan question honestly.
24. **Do not build plans during the session.** The scanners read daily bars, so `Rescan` and `Refresh` change slowly; pressing them every ten minutes and chasing whatever moved to the top is how a quiet week becomes a losing one. Live time is for executing the evening's plan.

**How to benefit from it**
- The intraday jobs run every 10 minutes from 10:00 to 14:20 Cairo, Sunday to Thursday, and prices are about 15 minutes behind — so a stop can be breached for up to 25 minutes before the app tells you. That is why the stop order must already sit at your broker (8.4); the app is a second pair of eyes, not the first.
- When you look at the screen, look at two things only: `Fired alerts` and the `Position Guardian` panel. A red `EXIT STOP` means sell at your broker now, then press `Close` and answer the plan question honestly; everything else on the site can wait until 15:05.
- Reload when the `data as of` chip turns red — stale numbers during a session are worse than none, because they look current.
- Resist acting on a new stock during the session. The scanners and the checklist read completed daily bars, so nothing a `Rescan` shows at 12:30 is a signal until the candle closes at 14:30; the trade you plan tonight is the same trade, at a price you have thought about.
- If Telegram is configured, let the phone do the watching and keep the browser shut: one push per position per verdict per day is designed to be enough, and it removes the temptation to fiddle.

### 8.6 After the close (15:05 onwards)

25. **Wait for the 15:00 post-close run** (it takes a few minutes: snapshot, EGX30 index, Candidates, alerts, Guardian, Scorecard grading, Leaders, Patterns, Setups — in that order). Then open the Portfolio page and read `Position Guardian — when to sell` computed on today's score: red and teal verdicts are tomorrow's opening orders, amber ones are tonight's questions.
26. **Act on `TIGHTEN STOP` tonight.** Press `Stop` on that row in `Open positions` and type the `Suggested stop` (or higher). Raising the stop never flatters your statistics — R keeps measuring against the initial stop — it only cuts what you can give back.
27. **If you are tempted to argue with a verdict, press `Replay my positions` on the Backtest page.** It shows what following the Guardian's rules from your entry date would already have done, next to what holding has actually done and what EGX30 did.
28. **Then plan tomorrow** with the fresh `Setups`, `Leaders` and `Patterns` tabs (all stored by the 15:00 job) — which is step 1 again.

**How to benefit from it**
- Wait for the post-close run to finish before reading anything; the `checklist of …` date under the decision card and the `as of` lines on the Screener tabs should show today's date. If they show yesterday's, the machine was asleep at 15:00 — the hourly catch-up will run it, or press `Rescan` / `Scan now` yourself.
- Tonight's Guardian verdicts are computed on today's close and today's score, so they are the most reliable ones you will see all day. Convert each red or teal verdict into a written opening order now, while you are calm, rather than deciding at 10:00 with the price moving.
- `TIGHTEN STOP` is the verdict that pays over time: raise the stop tonight to at least the `Suggested stop`, and raise the stop order at your broker to match. It never hurts your R statistics and it is the only way to keep a winner from becoming a scratch.
- If you catch yourself arguing with a verdict, run `Replay my positions` before you overrule it. The comparison with what holding actually did, and with EGX30, usually settles the argument in under a minute.
- Keep the evening to the fixed loop — Guardian, then Setups, Leaders, Patterns, then the next day's two or three names. Adding research on stocks that did not pass the filter is how the routine grows from 15 minutes to two hours and stops being done.

### 8.7 Weekly review (Friday or Saturday, 20 minutes)

29. **Portfolio → `Performance`.** Read `Avg R (net)` before `Win rate (net)`. Compare `Avg R · plan followed` with `Avg R · deviated`: if followed is higher, obey the plan; if deviated is higher over a meaningful number of trades, your plans are wrong for how you trade — fix them on the Stock page, not in your nerves. Check `Open risk` as a percentage of the account.
30. **`Closed positions`.** Sort by R and read the bottom five. What did they share — against the weekly trend, planned R:R under 2, a crowded sector, a Friday rumour? Then sort by `Plan followed`. Look at holding time against R: winners held two days and losers three weeks is the classic retail asymmetry, and the Guardian's `TIME STOP` and `TIGHTEN STOP` verdicts are the cure.
31. **Screener → `Scorecard`.** Read `Beat EGX30 10d %`, not `Win 10d %`, and only for rows with 20 or more graded hits — the app itself keeps a scanner's weight at 1.0 until then, and so should you. Watch the `pattern_…` rows and the `Catalog`'s EGX columns fill in over the months; they are the only Egyptian evidence for which shapes actually work here.
32. **Prune.** Un-star watchlist names you would not buy this week; disable or delete alert rules for trades already taken or abandoned. Ten rules you act on beat fifty you ignore.
33. **Housekeeping.** The Saturday 12:00 job backs up your data and tidies old records — but only if the app is running. Every few weeks, with the app stopped, copy the data file somewhere safe yourself.

**How to benefit from it**
- Do the review when the market is shut and no position is moving — Friday or Saturday — and read the same cards in the same order every week so a change stands out: `Avg R (net)` first, then `Avg R · plan followed` against `Avg R · deviated`, then the bottom five `Closed positions` by R.
- The plan-followed versus deviated comparison is the most valuable number in the app. If followed is higher over a meaningful number of trades, your job for the next month is obedience; if deviated is higher, fix the plans (stop placement, R:R, entry timing) rather than trusting your improvisation to keep paying.
- Look for the retail asymmetry in `Closed positions`: winners held two days, losers three weeks. If you see it, the fix is mechanical — obey `TIGHTEN STOP` and `TIME STOP` verdicts — not psychological.
- On the `Scorecard`, ignore anything with fewer than 20 graded hits and read `Beat EGX30 10d %` rather than `Win 10d %`: a scanner that wins 60% of the time but trails the index is costing you the index return. Give more of your research time to the scanners that beat it.
- Prune ruthlessly: an alert rule for a trade you already took, or a starred stock you would not buy this week, is noise that dilutes the signals you need. Then confirm the Saturday backup ran (the app must be running at 12:00 Saturday), and copy the data file yourself every few weeks regardless.

### 8.8 How to benefit from the routine

The routine is deliberately boring, and that is the point. Every step exists to make one of three mistakes harder: buying a stock with two crosses because one indicator looked exciting (the checklist), betting too much on one idea (the sizer and the 6% cap), and holding a loser past the stop you wrote when you were calm (the Guardian and the plan question). None of the cards will make a trade for you, and no card can see tomorrow — but a trader who runs this loop every day builds something no indicator provides: a written record of what they actually did, graded in R, that tells them within a few months whether their discipline or their improvisation is the thing making money. Follow the order, record every fill, answer the plan question honestly, and let the `Performance` cards judge you — not your memory.

---

## 9. Glossary — every term explained

**Accumulation / Distribution** — Institutions appear to be quietly buying (accumulation) or quietly selling (distribution), inferred from price-and-volume behaviour on the `Smart Money` tab. A proxy, not real fund-flow data.

**Advancers / Decliners / Unchanged** — How many EGX stocks closed up, down, or flat today. Together they measure breadth.

**ADV / Liquidity / Median daily value** — How much money changes hands in a stock on a typical day, measured by the app as the 20-day median of price × volume from its own snapshots. Below the liquidity floor (by default 5,000,000 EGP) a stock is filtered out of Candidates and Leaders and fails the Risk plan pillar; "unknown" (fewer than five stored sessions) is never treated as illiquid.

**Alert rule** — A standing instruction (`price above`, `price below`, `score min`, `squeeze`, `signal change`, `entry hit`) checked every 10 minutes in session and after the close; the same rule and symbol will not fire again within 6 hours.

**App rules (Backtest)** — The engine that tests the scanners' own entries with the Guardian's exits, buying at the next open, risking 1% of equity per trade by default, checking the stop before the target and charging fees and slippage. The tab that tests what you actually do.

**ATR (Average True Range)** — How much a stock typically moves in a day, in EGP, averaged over 14 sessions. The app uses it to place stops far enough away that normal noise does not hit them (2×ATR initial stops, 2.5×ATR trailing).

**Averaging down** — Buying more of a position below your average entry. The `+` button warns you because it is, statistically, the most expensive habit in retail trading.

**Backtest** — Replaying a trading rule over past prices to see what it would have earned, after costs.

**Banker-fund oscillator** — An indicator on the `Smart Money` tab that rises when big-money buying appears to dominate the volume.

**BBW (Bollinger Band Width)** — How wide the volatility envelope around price is. A low BBW (0.04 or below in the app's Squeeze scanner) is a squeeze.

**Best setups / Setups** — The six-pillar checklist run after every close across the latest Candidates, the Leaders ranking, your watchlist and your holdings; shown on the Dashboard and the Screener's `Setups` tab.

**Blended average** — Your average entry after adding shares with `+`: (old shares × old average + new shares × new price) ÷ total shares. Stop, targets and initial stop are not changed by an add.

**Bollinger Bands** — A band drawn above and below the average price; when it narrows sharply a big move usually follows.

**BOS / CHoCH (Break of Structure / Change of Character)** — Price-action events. BOS = a close through the last swing *with* the trend (continuation). CHoCH = the first close through the last swing *against* the trend — an early reversal warning; the checklist treats it as a red flag.

**Breadth** — How many stocks take part in a move, not just how far the index went. A rising index with weak breadth is a few big names carrying the market — fragile.

**Breakeven** — A stop raised to your entry price, making the trade risk-free before fees and gaps. The Guardian's suggested stop is never below breakeven once the trade has reached 1R.

**Breakout / False breakout** — A close beyond the prior 20-session range (breakout); a close back inside within 3 sessions makes it a false breakout. Volume on the break day is what separates the two.

**Bull trap / Bear trap** — A breakout above resistance that fails and traps buyers (bull trap, bearish) or a break below support that fails and traps sellers (bear trap, bullish).

**Buy & hold** — Simply buying at the start of the window and holding to the end. The benchmark every rule must beat.

**CAGR** — The yearly growth rate a total return works out to; shown in the App-rules `Full payload` for windows longer than about two and a half months.

**Candidates** — The merged multi-scanner shortlist: Squeeze, Volume Breakout, Smart Money and Momentum run together, hits merged by stock, ranked by evidence weight and family count. The stored copy on the Dashboard comes from the 15:00 run.

**Candlestick** — One bar = one session, showing open, high, low and close. Candlestick *patterns* (Hammer, Engulfing, Doji, Shark-32…) are one-to-three-bar signals — the noisiest group, hidden by default on the `Patterns` tab.

**Catch-up sentinel** — The hourly check (at seven minutes past each hour) that runs the missed post-close pipeline if the machine was asleep at 15:00 on a trading day.

**Composite score / Score** — The app's 0–100 technical quality score for a stock (green at 70 or above, amber 45–69, red below 45). The Guardian compares today's score with the one you bought on.

**Confirmed vs forming (pattern)** — Confirmed = a daily close beyond the neckline or trigger within the last 15 sessions (5 for trendline shapes, rounding shapes, diamonds and flags; 3 for price-action events). Forming = the shape is complete but the trigger has not been broken — a watchlist entry, not a trade.

**Curve-fitting / Overfitting** — Tuning a rule until it looks perfect on past data; it then fails on new data. Walk-forward and `Run on universe` exist to expose it.

**Data-age chip** — The `data as of HH:MM` pill in the top bar: when the page last received data from the app. Red at 20 minutes old or more — reload.

**Dead money** — A position held 15 or more sessions (by default) still inside ±0.5R. The Guardian's `TIME STOP` advice.

**Donchian** — An indicator strategy that buys when price beats its highest level of the last 20 sessions.

**Drawdown / Max drawdown** — The fall from a peak in account value to the following trough; max drawdown is the worst one — the real test of whether you could have stayed in.

**EGX30 / EGX70 / EGX100** — Egypt's main indices: the 30 largest and most liquid companies, the next 70, and the two combined. The app's benchmark is EGX30 (or an equal-weight proxy of its members when the index history is thin).

**EMA / SMA** — Exponential / simple moving average of price over N sessions; EMA weights recent prices more. The checklist's Trend pillar uses the 20- and 50-day averages.

**Entry** — The price at which the plan says to buy — a *level*, not an order to buy now.

**Entry hit** — An alert type that fires when the price *crosses* your planned entry since the previous close, in either direction. It needs a fresh quote and will not fire on a level crossed days ago.

**Evidence weight** — In Candidates, the family count with each family weighted by its scanner's Scorecard track record (2 × the 10-day beat rate, kept between 0.5 and 1.5, only after 20 graded hits). Until then it equals the family count.

**Expectancy** — The average net result per trade — in EGP (`Per trade (EGP)` on the Backtest page) or in percent. Positive is the minimum bar.

**Fees per side** — Your all-in trading cost as a percentage, charged on the buy *and* the sell; by default 0.25% each way. Every Portfolio profit, win rate and R figure is net of it.

**Fibonacci retracement / extension** — Levels where pullbacks often stop before a trend resumes (retracements) and where moves often stall beyond the old high (extensions, marked `ext`). Zones of interest, not walls.

**Fills / Fill journal** — Every buy and partial sale you record (`+`, `−`, `Open position`) is stored as a fill. A position with partial sales journaled cannot be removed with `×`, because that would erase real profit or loss.

**Forward return** — What a stock did 5, 10 and 20 sessions after a scanner hit — the raw material the Scorecard grades.

**Grade** — The engine's letter or word quality grade for a stock or a trade plan (e.g. `A`, `Grade: Good`).

**Guardian verdicts** — One per open position, most severe first: `EXIT STOP` (mark at/below stop), `TRAIL EXIT` (gave back more than 2.5×ATR from the post-entry high after reaching 1R), `TARGET2 HIT`, `TARGET1 HIT`, `STOP TOUCHED` (low pierced the stop, close recovered), `THESIS BROKEN` (signal turned SELL or score fell 15+ points since entry), `TIGHTEN STOP` (a higher stop is available after 1R), `TIME STOP` (15+ sessions inside ±0.5R), `HOLD`. Multipliers and thresholds are defaults and configurable.

**HH-HL / LH-LL** — Higher high, higher low (bullish swing structure) / lower high, lower low (bearish). The Trend pillar drops to a warning when an uptrend's recent swings turn to LH-LL ("the trend is tiring").

**Hit rate / Beat rate** — Hit rate: the share of graded signals where the stock was simply up N sessions later (`Win 10d %`). Beat rate: the share where it beat EGX30 over the same window — the number that matters, because in a bull month every scanner "wins".

**In-sample / Out-of-sample** — In a walk-forward test, the 70% "learn" slice of each fold and the 30% "prove" slice the rule did not see. Out-of-sample is the honest half.

**Initial stop** — The stop you recorded when you opened the position. All R figures measure against it, so raising the stop later never inflates your statistics.

**Inside bar** — A candle whose whole range sits inside the previous candle's range — a pause. Two in a row is a Shark-32.

**Keltner Channel** — Like Bollinger Bands but built from ATR; the `keltner_breakout` strategy buys a close above the upper channel.

**Leaders / Relative strength / RS score** — Stocks beating EGX30 over 1, 3 and 6 months. RS score 0–100 = the percentile rank of excess return over the index, weighted 30/40/30; 90 means stronger than 90% of the universe.

**Limit-up / limit-down / Price band** — EGX caps how far a stock may move in one session (the app assumes ±20% by default, configurable). A stop or target farther than one band away can be gapped over; a limit-locked stock often cannot be bought or sold at all.

**Mark** — The price a position is valued at right now, with its source printed under it (`yahoo quote`, `candle close`, `snapshot`). For EGX stocks it is very often the last daily close, not a live tick.

**Measured move** — A pattern's projected target: the height of the shape projected from the neckline.

**Momentum (scanner)** — A strong bullish daily candle verified against history: three consecutive higher closes, each closing above its open.

**Morning brief** — The AI-written daily summary (market pulse, sectors, candidates with WATCH CONDITIONS, alerts and positions, plan for today), generated at 09:30 or with `Generate`; ends with "Not financial advice."

**Move done %** — For a confirmed pattern, how much of the measured move price has already travelled (0 = at the neckline, 100 = at target). Patterns at 100% are dropped; quality loses a point for every 5% done.

**Multi-timeframe alignment** — Whether the weekly, daily and intraday trends agree. Never fight the weekly.

**Neckline / Trigger** — The line a pattern must break to be confirmed: across the bounces of a double bottom, under the dips of a head and shoulders, the trendline of a triangle. Your alert price for a forming shape.

**New high** — Within 2% of the 52-week high. Strength lives there; a stop under a real support still decides the trade.

**No setup / Watch / Setup** — The checklist verdicts. SETUP: 5–6 pillars pass, none fails. WATCH: 3–4 pass with none failing, or one non-critical pillar fails with 3+ passing. NO SETUP: Trend or Risk plan fails, two or more fail, or fewer than 3 pass.

**Open heat / Open risk** — The total EGP you would lose if every open position were stopped at its current stop, as a percentage of your account. `New position` blocks a trade that would push it above 6% unless you explicitly override.

**Partial** — Selling part of a position with `−`; the profit or loss on those shares is booked to Realized PnL at once and the rest stays at the same average.

**Peak R** — The best R a trade has reached on a closing basis since entry. A large gap between Peak R and R now means a winner is being given back.

**Pillars (the six)** — Trend, Support / resistance, Volume, Price action, Patterns, Risk plan — each PASS / WARN / FAIL with one sentence of evidence. Trend and Risk plan veto a trade outright.

**Plan followed / deviated** — Your answer to `Did you follow the plan on this trade?` at close time. Feeds the `Avg R · plan followed` and `Avg R · deviated` cards — the cheapest discipline test there is.

**PnL** — Profit and loss. Realized = closed trades and partials, net of fees. Unrealized = open positions at the mark, minus the fees an exit would cost.

**Post-close pipeline** — The 15:00 job: snapshot, EGX30 index, Candidates, alerts, Guardian, Scorecard grading, Leaders, Patterns, Setups. Skipped on weekends and holidays.

**Profit factor** — Total money won ÷ total money lost. Above 1 the winners paid for the losers; below 0.5 the rule "lost money on this stock".

**Pullback / Throwback / Retest** — Pullback: 2–5 down sessions into the 20-day average inside an uptrend — the classic buy-the-dip spot in a leader. Throwback: price returning to a broken neckline from above and holding. Retest: price coming back to test a broken level; a *failed* retest is a red flag.

**Quality score** — 0–100 for a pattern: how clean the shape is, how deep, whether confirmed and on what volume (no credit below 0.8× average, full at 2×), how recent, minus a penalty for move already done. A tiebreaker, not a gate.

**R / R-multiple** — Your result measured in units of what you risked to the initial stop. Risk 1,000 EGP, make 2,000 → +2R. Speaking in R makes trades of different sizes comparable.

**R:R (Reward-to-risk)** — Potential profit ÷ potential loss from the entry. The trade plan shows a red `Reject` banner below 2 (measured to Target 2); the checklist's Risk plan pillar passes at 2R or more and fails under 1R.

**R n/a** — Shown when the initial risk is unknown because the stop was recorded at or above the entry. That position is excluded from Avg R; the Guardian still watches its stop.

**Rate limit** — A data provider (TradingView or Yahoo) briefly refusing requests after heavy use. Cards show a plain message; wait a minute or two and reload. Stored results and Yahoo-based cards keep working.

**Reliability tier / Frequency tier** — The textbook (Western) prior for a pattern: high / medium / low reliability, common / uncommon / rare frequency. Trust the `Catalog`'s EGX columns over the tier once they have 20 or more graded detections.

**Robustness score / Verdict (walk-forward)** — Average of out-of-sample return ÷ in-sample return across the folds, capped at 2. ROBUST (0.8 or more), MODERATE (0.5), WEAK (0.2), OVERFITTED (below 0.2).

**RSI (Relative Strength Index)** — A 0–100 momentum gauge; over 70 traditionally "overbought", under 30 "oversold" — though in strong trends stocks stay overbought for a long time.

**Scorecard** — The track record: every stored scanner hit and confirmed pattern graded by what the stock did 5, 10 and 20 sessions later versus EGX30. A scanner's 10-day beat rate becomes its weight in Candidates after 20 graded hits.

**Sector concentration** — A warning from `New position` when you already hold two or more open positions in the new stock's sector — EGX sectors move together.

**Shark-32** — Two consecutive inside bars: a coil that continues the prior trend about 60% of the time by the textbook statistics. Enter on a close outside the first bar's range; target = the pattern's height.

**Sharpe ratio (EGP)** — Return above the EGP risk-free rate per unit of volatility, annualised for EGX sessions. The app uses a 25% yearly risk-free rate by default and 245 sessions of 4.5 hours, so a positive Sharpe here means the rule out-earned a deposit for the risk it took. Not comparable to US figures.

**Signal** — The engine's one-word reading (BUY / SELL / NEUTRAL and variants). A snapshot signal turning to SELL is one trigger for `THESIS BROKEN`.

**Signal family** — Candidates groups its scanners into three kinds of evidence: coil (Squeeze), thrust (Volume Breakout and Momentum — they measure the same big up-day, so together they count once) and flow (Smart Money). Two families beat two badges from one family.

**Slippage** — The gap between the price you wanted and the price you got. The App-rules engine assumes 0.1% per side; raise it to 0.5% or more for thin stocks.

**Smart money** — Institutional players, inferred from volume behaviour. See Accumulation / Distribution.

**Snapshot** — The daily record of every EGX100 stock (price, score, signal, band width) taken at 15:00. Daily-signal alerts, the thesis check, the liquidity filter and the Scorecard all read it.

**Spring / Upthrust** — Wyckoff events. Spring: a dip under range support that closes back inside — a shakeout, one of the better low-risk entries because the stop sits just under the spring low. Upthrust: a poke above range resistance that closes back inside — bearish, a red flag in the checklist.

**Squeeze** — Volatility compressing to unusual tightness (BBW at or below 0.04 in the app). Quiet periods precede violent ones — a squeeze says *where* energy is stored, not *which way* it goes.

**Stop / Stop-loss** — Your predetermined exit if you are wrong. The most important number in any trade; place it with your broker the moment you enter.

**Stop gap** — In a backtest, a session that *opens* at or below the stop is filled at the open, not at the stop — the price gapped through it.

**Stop hint** — Where a pattern is invalidated: beyond the lows or head for reversal shapes, the opposite trendline for triangles and channels, beyond the signal bar for candlesticks and events.

**Stop sweep** — The same rule pair run with the initial stop at 1, 1.5, 2, 2.5, 3 and 4 × ATR, to show how tight a stop can be before daily noise takes you out. Look for a plateau, not a peak.

**Stop touched** — Today's low pierced the stop but the close recovered. A broker question first: did your resting order fill?

**Supertrend** — A trend-following indicator built on ATR that flips between buy and sell states.

**Support / Resistance** — Price zones where buyers (support) or sellers (resistance) have shown up before. The app counts only zones tested two or more times as the level you are "at"; round numbers, 52-week extremes and averages are context.

**Swing high / low** — A bar higher (or lower) than the bars either side of it — the pivots from which patterns and structure are built.

**T+2 settlement** — Trades settle two business days after execution; your cash is not instantly reusable.

**Target 1 / Target 2** — Planned profit-taking levels. The classic response to T1 is to sell part and move the stop to breakeven; T2 is where the completed trade must not be allowed to become a new one.

**Thesis** — The reason you bought, written down — in your entry Note and, optionally, the AI `Thesis` tab. `THESIS BROKEN` is the Guardian telling you it no longer holds.

**Time stop** — Selling a position that has gone nowhere (inside ±0.5R) for 15 sessions or more (by default). Capital has a cost.

**Trade plan** — Entry, stop, two targets, R:R and a grade for one scenario (`Pullback plan` or `Breakout plan`), with EGX sanity checks; the `Alt —` line shows the other scenario.

**Trailing stop / Chandelier** — A stop that follows price up: the highest close since entry minus 2.5×ATR (by default), never below breakeven once the trade has reached 1R.

**Triple EMA** — An indicator strategy using a fast and slow average plus a 200-day trend filter; needs 220 sessions of history.

**Universe** — The set of stocks a tool scans: `EGX30`, `EGX70`, `EGX100` (also `SHARIAH33`, `EGX35LV`, `TAMAYUZ`, `ALL` for alert rules).

**Volume** — Shares traded. Rising price on rising volume is conviction; rising price on falling volume is suspicion. The Volume pillar passes when at least 55% of the last 20 sessions' volume traded on up days and this week runs at or above the 20-day average.

**Walk-forward test** — Testing a rule on three consecutive slices of history, each split learn / prove, to see whether it keeps behaving from one stretch to the next. The most honest backtest there is.

**Watchlist** — Your starred shortlist in the sidebar (up to 15 shown). The Dashboard's `Patterns on your stocks` column and the Setups run both read from it.

**Win rate** — Percent of closed trades that ended with a net profit. It flatters; Avg R tells the truth.

**Wyckoff** — A school of reading price and volume for the footprints of large players; the source of the Spring and Upthrust events.

---

## 10. Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `API offline` in the top-bar session pill; every card fails | The app's server is not running, or the browser cannot reach it | Look at the PowerShell window — if it is closed or shows an error, start the app again exactly as in section 1.1 and open http://127.0.0.1:8642 (the address printed at start-up is always the right one). Then hard-reload. |
| The page will not load at all | Wrong address, or the app is stopped | The address is **http://127.0.0.1:8642**. If Windows refused the port at start-up (error 10013), the start-up text shows the address that was actually used. |
| `Watchlist unavailable.` in the sidebar | The app could not read its own database — almost always because the server stopped | Check the PowerShell window; restart if needed. If it persists with the app running, stop the app and make sure the data file is not open or locked by another program. |
| `Empty — star a stock.` in the sidebar | You have not starred anything yet | Open any Stock page and click the ☆ next to the price. |
| Prices do not move; the `Mark` says `snapshot` or `candle close`; `Session (Cairo)` says `CLOSED` | The market is shut (outside Sunday–Thursday 10:00–14:30 Cairo, or a holiday), so everything is the last session's close | Nothing is wrong. Plan with it; do not read a stale close as a price you can get at the open. Hover the session pill for `Next open: …`. |
| `data as of … · 25m old — reload` in red | This browser page has not fetched anything for 20 minutes or more | Press F5. Pages only fetch when you load them or press their own buttons. |
| *TradingView is pausing this app for a minute or two (rate limit)…* in a card; `Analysis: …` / `Trade plan: …` errors while the chart works | The scanner provider is throttling after heavy use | Wait one to two minutes and reload. The `Decision checklist`, `Support & resistance`, `Chart patterns`, Leaders, Patterns and stored cards keep working from daily candles. Do not hammer `Rescan` — it prolongs the pause. |
| *Yahoo is rate-limiting requests for a short while…* | The price-history provider is throttling | Wait a minute and try again. |
| `New position` hint says the stop came from `entry − 2×Yahoo 14-day ATR` or `entry − 2×TradingView ATR` instead of `trade plan` | The plan had no stop below your entry, or TradingView was pausing, so the app fell back to two daily ranges below your fill | Acceptable in an emergency, but check the Stock page's `Support & resistance` and put the stop under a real tested support before you accept it. Retry in a minute for the full plan. |
| A card described in this guide is missing; a button does nothing; the sidebar shows a plain list headed `EGX Engine` | Your browser is showing an old copy of the page | Hard-reload with `Ctrl+F5` (or `Ctrl+Shift+R`). Open a new tab if the symbol search seems to lack new tickers. |
| Alerts and Guardian verdicts are recorded but never reach your phone; `Fired alerts` shows `local` | Telegram is not configured, or the bot token / chat id is wrong | Set both Telegram values in your settings (section 1.4), restart the app, then press `Evaluate now` on a rule you know is true to test delivery. Also check the app was actually running at the time — a stopped app sends nothing. |
| `Candidates` shows `No candidates from today's scans.` | The scanners ran and nothing qualified | Real information — no multi-scanner agreement today. Press `Rescan` once if you want a live run; if the list is suspiciously short during a TradingView pause, one of the four scanners may have failed — wait and rescan. |
| `Candidates` spins for a long time | Normal — four market-wide scans are running | Give it up to a minute. |
| `No checklist run stored yet…`, `No ranking stored yet…`, `No patterns stored yet for this filter…` | The 15:00 post-close job has not run since you installed, or you are on a Universe / filter the job does not store (it stores EGX100 only) | Wait for the next 15:00 on a trading day, or press `Run now` (Setups), `Refresh` (Leaders) or `Scan now` (Patterns). Widen the `Status` / `Category` filter or untick `Hide candlesticks`. |
| `Patterns` tab empty on EGX30 or EGX70 | Only EGX100 is scanned automatically | Press `Scan now (≈1 min)` on that universe once; it is stored from then on. |
| `Scorecard` says `Nothing graded yet…`; every `Weight` badge is amber 1.0 | A hit can only be graded 5 sessions after it fired, and a scanner's weight stays neutral until it has 20 graded hits at 10 days | Wait. The first rows appear about a week after the post-close job starts running; weights start moving after a few weeks. A live `Refresh` on Candidates does not add hits — only the 15:00 run does. |
| `Position Guardian — when to sell` shows `No open positions — nothing to guard.`; the Dashboard says `No open positions recorded…` | You have not recorded any positions | Record what you hold in `New position` (symbol, shares, fill price are enough). The Guardian starts watching at once. |
| The Guardian row says `No price available for this symbol (Yahoo and snapshots both empty)` | Neither price source has anything for that ticker | Check the position manually at your broker; the verdict cannot be computed. Common for very small or newly listed names. |
| The `Your position` card on the Stock page never appears, or `Chart patterns` stays at `Scanning…` | Those two cards load only after the live analysis has answered, and the analysis failed (usually a rate limit) | Reload in a minute or two. |
| `R now` shows `n/a`; the trade is missing from `Avg R (net)` | The stop was recorded at or above the entry, so the initial risk is unknown | Correct for an existing winner whose stop you had already raised. For a new trade it is a typo — remove the row with `×` (only if it has no partial sales) and re-enter it with a stop below the entry. |
| `BLOCKED: this trade takes total open risk to … above the 6% open-heat cap` | Your open positions plus this one would risk more than 6% of the account if every stop were hit | Reduce size, close or trim something, or raise stops on winners (`Stop` button) to bring heat down. Override only for a reason you can write down. `Position not opened (open-heat cap).` means you cancelled — nothing was recorded. |
| `Checklist unavailable: not enough daily history (… bars)`; `Levels unavailable: not enough daily history (need 60+ bars)`; `No price history available for this symbol.` | The stock has too little daily history (the checklist needs 120 sessions, levels 60), or Yahoo has none | Nothing to fix; the rest of the page still works. Treat it as a liquidity warning — such names are rarely tradeable at size anyway. |
| Backtest: `Backtest failed: not enough daily history…`, `INSUFFICIENT SAMPLE`, `(few)` after the trade count, amber verdict box | Too little history, or fewer than 20 trades | Use `2 years` or longer. Under 20 trades take only the direction, never the decimals. |
| `Brief generation failed: ANTHROPIC_API_KEY not configured`; `News: MARKETAUX_API_TOKEN not configured`; `Debate failed` / `Thesis failed` | The optional AI key or news key is not set | Everything else works without them. Add the key in your settings (section 1.4) and restart if you want those features. |
| You changed a setting and nothing happened | Settings are read once, when the app starts | Stop the app (`Ctrl+C` in the PowerShell window) and start it again (section 1.1). |
| No fresh snapshot, Setups, Leaders or Patterns this evening | The machine was asleep or the app was stopped at 15:00, or it is a weekend / holiday | On a trading day, keep the app running past 15:07 — the hourly catch-up runs the missed pipeline. On Fridays, Saturdays and holidays nothing runs by design. |
| A Telegram message `[EGX scheduler] job '…' FAILED` | A background job started failing (sent once, not on every repetition) | Read the detail; usually a provider outage that clears itself. If it repeats daily, check the PowerShell window for errors. |
| An `entry hit` rule never fires although the level was crossed | It needs a fresh cross since the previous close with a real quote; a stale snapshot price keeps it silent on purpose | Use `price above` / `price below` for a level that is already past. |
| A `score min`, `squeeze` or `signal change` rule fires at most once a day | These read the daily snapshot, which changes once after 15:00 | Expected. Use `price above` / `price below` / `entry hit` for intraday levels. |
| The same alert does not fire again ten minutes later | The 6-hour dedupe per rule and symbol | Expected — a standing condition pings once. |
| Start-up warns that the analytics core is unavailable / degraded mode | The analysis library the scanners depend on is missing or moved | Pages load but data cards fail. Restore the folder and restart; if it persists, ask whoever set the app up. |

### 10.1 Three rules worth more than any indicator in this app

1. **Never trade without a stop-loss — and never lower it.** Decide the exit before you enter, place the stop order at your broker the same minute, and record it in `New position`. The Guardian reads it back to you every day; when it says `EXIT STOP`, that is not a discussion.
2. **Never risk more than 1% of your account on one trade, and never let open heat pass 6%.** Use `Position size` every time, size from the stop you will actually use, and treat the open-heat block as a wall. Most traders do not blow up by picking bad stocks; they blow up by betting too much on one.
3. **Never take a setup with R:R below 2, or a checklist verdict of `NO SETUP`.** If the red banner shows or Trend or Risk plan is against it, there will be another trade tomorrow. Winners that pay twice what losers cost let you be wrong more often than right and still come out ahead.

**How to benefit from it**
- Each rule has a card that enforces it: the stop lives in `New position` and is policed by the `Position Guardian` (`EXIT STOP`); the 1% and 6% limits live in `Position size` and the open-heat block; the R:R and checklist rules live in `Trade plan` and `Decision checklist`. Use those cards every time rather than trusting yourself to remember the rule under pressure.
- Test yourself against them weekly in `Closed positions`: any closed trade with a red `deviated` badge under `Plan followed`, an `R` worse than −1 (you let a loss run past the stop you wrote), or a `Why` note that mentions a rejected plan is a rule broken. Three such rows in a month is a habit, not bad luck.
- The one exception the app allows — a stop *above* entry when recording an existing winner — is exactly that: recording, not opening. For a new trade, a stop at or above entry is a typo; press Cancel.
- If you break a rule on purpose, write the reason in the position's Note before you do it. In three months the `Avg R · deviated` card will tell you whether your exceptions were insight or noise — and for most traders the answer is the same.
- When the rules keep you out of a trade that then works, that is the rules working. The money you did not make on the one that ran is the price of not being in the five that did not.

*Analysis tooling — not financial advice. Data delayed ~15 minutes. The app never places an order; you are responsible for your own trades.*
