# EGX Decision Engine — Complete User Guide

**A plain-English manual for every page, every section, and every button.**

This guide assumes you love stocks but are not a programmer. Every feature is explained three ways:
**What it is** → **What the button does** → **Why it helps you make money (or avoid losing it)**.

> ⚠️ **Important:** This app is an *analysis assistant*, not a broker and not a fortune teller. It never
> places orders. It shows you evidence and does the arithmetic; **you** make the decision and place the
> trade with your real broker. Prices from TradingView are delayed roughly 15 minutes.

---

## Table of Contents

1. [Starting and stopping the app](#1-starting-and-stopping-the-app)
2. [The frame around every page](#2-the-frame-around-every-page-sidebar-top-bar-footer)
3. [Page 1 — Dashboard](#3-page-1--dashboard-indexhtml)
4. [Page 2 — Stock page](#4-page-2--stock-page-stockhtml)
5. [Page 3 — Screener](#5-page-3--screener-screenerhtml)
6. [Page 4 — Backtest](#6-page-4--backtest-backtesthtml)
7. [Page 5 — Portfolio](#7-page-5--portfolio-portfoliohtml)
8. [Your daily routine](#8-your-daily-routine-how-to-actually-use-this)
9. [Glossary — every term explained](#9-glossary--every-term-explained)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Starting and stopping the app

**To start it**, open PowerShell and run:

```powershell
cd D:\MyApps\egx-decision-engine
.venv\Scripts\python.exe run.py
```

Then open your browser at **http://127.0.0.1:8646**

**To stop it**, press `Ctrl+C` in that PowerShell window (or close the window).

**Why the odd port number?** Port 8642 is blocked by Windows on this machine, so the app uses 8646
instead. This is already configured — you don't need to do anything.

**Nothing leaves your computer** except the requests that fetch market data. Your watchlist, positions,
and notes are stored in a local file at `data\egx.db`.

---

## 2. The frame around every page (sidebar, top bar, footer)

These three things appear on **all five pages**, so learn them once.

### 2.1 The left sidebar

| Item | What it shows | What it does |
|---|---|---|
| **EGX//DE** / *Decision Engine* | The app's name badge | Just a label, not clickable |
| **▦ Dashboard** | Nav link | Opens the main market overview page |
| **⌗ Screener** | Nav link | Opens the stock-hunting page |
| **↻ Backtest** | Nav link | Opens the strategy-testing page |
| **☷ Portfolio** | Nav link | Opens your positions and alerts page |
| **Watchlist** | Your starred stocks (up to 15), each with its latest price | **Click any symbol** to jump straight to that stock's page |

The nav link for the page you're currently on is highlighted so you always know where you are.

**Watchlist messages you may see:**
- `Empty — star a stock.` → You haven't starred anything yet. Go to any stock page and click the ☆ star.
- `Watchlist unavailable.` → The app couldn't reach its own database. Usually means the server stopped.

**Why it helps:** Your watchlist is your shortlist. Instead of remembering ticker codes, you keep the
5–15 companies you actually care about one click away, with their current price always visible.

### 2.2 The top bar

| Item | What it shows | What it does |
|---|---|---|
| **Page title** | e.g. `Dashboard`, `COMI — Stock` | Just tells you where you are |
| **Session pill** | `Market open` (green) / `Market closed` (red) / `API offline` | Live status of the Egyptian Exchange. When closed, **hover your mouse over it** to see the next opening time |
| **Search box** `Search symbol or company…` | Type a ticker **or a company name** | A dropdown suggests matches as you type, showing the ticker, the full company name, and an index badge (EGX30 / EGX70 / SHARIAH33…). Use **↑ ↓** to move, **Enter** to open, **Esc** to close — or just click a suggestion |

**Why the search matters:** You don't have to remember that CIB is `COMI` or that Juhayna is `JUFO`.
Type "bank", "juhayna", or "telecom" and the right company appears — all 293 EGX-listed tickers are
searchable by name, with the EGX30 blue chips ranked first.

**Why the session pill matters:** EGX trades **Sunday to Thursday, 10:00–14:30 Cairo time**. Friday and
Saturday are the weekend here (not Saturday/Sunday like Western markets). If the pill says *Market
closed*, the prices you're looking at are from the last session — fine for planning tonight's trades,
but don't expect them to move.

**`API offline`** means the app's server isn't running. Restart it (see section 1).

### 2.3 The footer

Every page ends with: *"Analysis tooling — not financial advice. Data delayed ~15 min."*
It's there on purpose. Treat every number in this app as **evidence to weigh**, not as an instruction.

### 2.4 Little pop-up messages (toasts)

When you do something — add a stock to your watchlist, open a position, create an alert — a small
message slides in at the corner for about 4 seconds. Green-ish means it worked; red means it failed and
tells you why. You never need to dismiss them.

---

## 3. Page 1 — Dashboard (`index.html`)

**This is your "what is the market doing today?" page.** Open it first every day. It loads five things
automatically — you don't press anything to make it work.

### 3.1 The five stat tiles (top row)

| Tile | What the number means | Why you care |
|---|---|---|
| **Advancers** | How many EGX stocks are **up** today | — |
| **Decliners** | How many are **down** today | — |
| **Unchanged** | How many didn't move | — |
| **% Advancing** | Advancers as a percentage of all stocks | **This is the important one.** Above ~60% = broad, healthy buying. Below ~40% = broad selling. Around 50% = a mixed, choppy market |
| **Session (Cairo)** | `OPEN` or `CLOSED`, plus the current Cairo time or the next open time | Tells you whether prices are live or frozen |

**Why this row matters more than any single stock:** This is called **market breadth**. Most Egyptian
stocks follow the index. If only 25% of stocks are advancing, even a great-looking individual setup is
swimming against the tide — that's the day to trade smaller or not at all. If 70% are advancing, your
breakout setups have the wind behind them.

### 3.2 Card — `Global snapshot`

A strip of world markets: major indices, big currencies, key commodities — each with its price and
percent change.

**Why it helps:** Egypt doesn't trade in a vacuum. A crashing global market or a spiking dollar tends to
drag EGX with it. This is a 3-second sanity check before you commit money: *is the world calm today?*

There are no buttons here — it's read-only information.

### 3.3 Cards — `Top gainers`, `Top losers`, `Most active`

Three side-by-side tables, each showing up to 8 stocks with the same four columns:

| Column | Meaning |
|---|---|
| **Symbol** | The ticker code (e.g. COMI = Commercial International Bank) |
| **Price** | Latest price in EGP |
| **Chg %** | Today's percentage move — green if up, red if down |
| **Vol** | Shares traded today, shortened (`1.2K` = 1,200 · `3.45M` = 3,450,000) |

**👉 Click anywhere on a row** to open that stock's full analysis page.

**How to read each table:**
- **Top gainers** — today's strongest movers. *Caution:* on EGX a stock near +9–10% may be **limit-up**
  (frozen at the daily maximum), meaning you often physically cannot buy it. Big gainers are also often
  *late* — the move already happened.
- **Top losers** — today's weakest. Useful two ways: avoid catching a falling knife, or spot a quality
  company being oversold.
- **Most active** — where the *money* is going, measured by volume. This is frequently the most useful
  of the three: real institutional interest shows up as volume before it shows up as price.

### 3.4 Card — `Sector heatmap`

A grid of coloured tiles, one per sector (Banks, Real Estate, Chemicals, etc.), sorted strongest first.
Green tiles = the sector is up; red = down. **The stronger the colour, the bigger the move.** The
timestamp on the right tells you when the data was captured.

**Why it helps — this is professional-level thinking:** Money rotates between sectors in waves. If Banks
are green three days running and Real Estate is red, buying a bank stock means you're swimming *with* the
current. Picking the best stock in a dying sector is much harder than picking an average stock in a
booming one.

Tiles are not clickable — use the Screener page to drill into a sector.

### 3.5 Card — `Candidates`

**This is the heart of the whole app.** It shows up to 10 stocks, ranked, that were flagged by
**multiple independent scanners** at once.

| Column | Meaning |
|---|---|
| **Symbol / scanners** | The ticker, plus a small badge for **each scanner that flagged it** |
| **Price** | Current price |
| **Chg %** | Today's move |
| **Score** | The app's overall quality score for that stock (higher is better) |

**👉 Click any row** to open the full analysis for that stock.

**Why this is so valuable:** One scanner finding a stock is a coincidence. Four scanners finding the same
stock — a volatility squeeze *and* a volume breakout *and* smart-money accumulation *and* momentum — is a
signal. The badges show you exactly *why* each name is on the list. **Start your research here, not with
a random stock you read about on Facebook.**

*It can take up to a minute to load* (it's running four separate market-wide scans), so you'll see
"Running scanners… (can take a minute)" first. If it says `No candidates from today's scans.`, the market
simply has no high-quality setups right now — which is itself useful information: a day to stay in cash.

### 3.6 Card — `Morning brief` + the **`Generate`** button

| Element | What it does | Why use it |
|---|---|---|
| The text area | On page load, shows the **most recent** brief already saved | Read yesterday's/today's summary instantly |
| **`Generate`** button | Sends the market overview, the candidate list, recently fired alerts, and your open positions to Claude (an AI analyst), which writes a fresh written brief and saves it | Turns a wall of numbers into a paragraph of plain reasoning |

**⏱ Takes about a minute** and the button greys out while it works.

**Why it helps:** You get a written second opinion that connects the dots — *"breadth is weak, banks are
leading, three candidates share a squeeze pattern, your open position in X is near its stop"* — the kind
of read-through a human analyst would give you over coffee.

**Requires setup:** This needs an `ANTHROPIC_API_KEY` in the `.env` file. Without it you'll see an error
saying the key isn't configured; everything else on the app still works normally.

---

## 4. Page 2 — Stock page (`stock.html`)

**This is your deep-dive page for one company.** You reach it by clicking any stock anywhere in the app,
or by typing a symbol in the top-bar search.

The web address looks like `stock.html?symbol=COMI`. If you land here with no symbol, the page tells you
so and asks you to use the search box.

### 4.1 The header strip

| Element | What it shows |
|---|---|
| **Symbol** | The ticker you're viewing |
| **Price** | Latest price |
| **Change** | Today's move, green or red |
| **Signal badge** | The app's one-word verdict: a *buy*-flavoured word turns it green, a *sell*-flavoured word turns it red, anything else stays neutral |
| **☆ / ★ Star button** | **Click to add or remove this stock from your watchlist.** ☆ = not saved, ★ = saved. The sidebar updates immediately |

**Why the star matters:** Your watchlist isn't just convenience — it's the list the sidebar keeps live for
you, and it's how you build a focused universe of 10–15 names you know well instead of chasing 260.

### 4.2 Card — `Price · 1Y daily` (the chart)

A one-year candlestick chart with a volume bar chart underneath. Each candle is one day: the body shows
open-to-close, the wicks show the high and low.

**The horizontal dashed lines drawn on it are the important part:**

| Line | Colour | Meaning |
|---|---|---|
| **entry** | Teal | The price the app suggests buying at |
| **stop** | Red | Where you get out if you're wrong |
| **T1** and **T2** | Green | First and second profit targets |
| **fib …** | Amber | Fibonacci retracement levels (see glossary) |

**Why it helps:** Numbers in a table are abstract; lines on a chart are obvious. In one glance you see
whether the suggested entry is right below you, whether the stop sits under real support, and how much
room there is to the targets.

**Messages you might see instead of a chart:** `No price history available for this symbol.` (Yahoo has no
data for this ticker — common for very small companies), or `Chart library failed to load (CDN
unreachable).` (you're offline).

### 4.3 Card — `Multi-timeframe alignment`

A grid of 5 boxes, one per timeframe (1W weekly, 1D daily, 4H, 1H, 15M). Each box shows the **trend** on
that timeframe (green = bullish, red = bearish, grey = neutral) and the **RSI** reading with an arrow
(↑ rising, ↓ falling). **Hover over any box** for a tooltip with the reasons behind that verdict and the
advice for that timeframe.

Under the grid sits the alignment summary as a row of badges: the overall verdict (e.g. `LEAN BULLISH`),
`Confidence`, a `Net` score, and — most usefully — a `Diverging: …` badge naming any timeframe that
disagrees with the rest.

If a timeframe has no reading, an amber note under the grid says which ones and why (usually a temporary
rate limit upstream); wait a few minutes and reload.

**Why this is one of the most important panels in the app:** A buy signal on the 15-minute chart while the
weekly trend is falling is a trap — you're buying a bounce inside a downtrend. When **weekly and daily
both agree** with your direction, your odds improve dramatically. **Rule of thumb: never take a trade
that fights the weekly trend.**

### 4.4 The five tabs

Click a tab to load it. Each loads once and then remembers.

#### Tab `Smart Money`
Shows whether large, informed players appear to be **accumulating** (quietly buying) or **distributing**
(quietly selling), based on volume-flow analysis. A green badge means accumulation, red means
distribution, plus a detailed breakdown of the underlying readings.

**Why it helps:** Price tells you what happened; volume flow hints at *who* did it. Institutions can't
buy quietly without leaving footprints in the volume data. Accumulation under a flat price is one of the
most bullish patterns that exists.

#### Tab `Fibonacci`
A small table of **Level** and **Price** — the classic retracement levels (23.6%, 38.2%, 50%, 61.8%)
calculated from the stock's recent swing.

**Why it helps:** After a stock runs up, it usually pulls back before continuing. These levels are where
pullbacks commonly stop and buyers return. Combining a Fibonacci level with the suggested entry gives you
a much better price than chasing.

#### Tab `News`
Recent headlines about the company, each with its source and date, clickable through to the article, plus
an overall **Sentiment** badge.

**Why it helps:** Charts don't know that the CEO resigned this morning. Use this as a **veto**: if the
technicals look perfect but there's fresh bad news, stand aside. *(Requires a `MARKETAUX_API_TOKEN` in
`.env`; without it this tab reports that news isn't configured.)*

#### Tab `Debate`
Runs a **multi-agent debate**: separate analytical perspectives (technical, sentiment, risk) argue the
case, and you get each one's opinion plus a final verdict badge. Takes up to a minute.

**Why it helps:** It deliberately shows you the *bear* case alongside the bull case. The single most
expensive habit in trading is only looking for evidence that confirms what you already want to do.

#### Tab `Thesis` + the **`Generate thesis`** button
Shows the last AI-written analysis for this stock; the button writes a fresh one using the stock's full
detail, timeframes, smart-money read, and news.

**Why it helps:** It converts six panels of numbers into a written argument you can actually judge — and
because it's saved, you can re-read next month what you were thinking when you bought.

### 4.5 Card — `Score`

A big number **out of 100**, coloured green (70+), amber (45–69), or red (under 45), often with a letter
**grade badge**, plus a set of horizontal bars breaking the score into its components.

**Why the bars matter more than the total:** A score of 72 built from strong trend + strong volume is a
very different animal from a 72 built on one extreme reading. The bars show you *what the score is made
of*, so you can disagree with it intelligently.

### 4.6 Card — `Trade plan`

This is where analysis becomes an actual, executable plan.

| Element | Meaning |
|---|---|
| **Entry** | The price to buy at |
| **Stop** | The exit price if the trade goes wrong — **your maximum loss point** |
| **Target 1** | First profit target (where to consider taking some off) |
| **Target 2** | Second, more ambitious target |
| **R:R badge** | **Risk-to-Reward ratio, measured from the Entry price.** Green when 2 or better, red when below 2 |
| **Scenario badge** | Which plan you're looking at — `Pullback plan` (buy the dip to support/EMA20) or `Breakout plan` (buy strength through resistance). All four levels and the R:R belong to that one scenario |
| **Alt line** | The other scenario's entry/stop/T1/R:R in one grey line, so you can compare both ways to trade the same stock |
| **Grade badge** | The setup's quality rating |
| **Notes** | Why the app built this plan |
| **`Full plan payload`** | Click to expand every underlying number |

**🚨 The red banner `Reject: R:R x.xx < 2`** appears when the reward doesn't justify the risk.

**Why R:R ≥ 2 is a hard rule and not a suggestion:** If every winner makes you 2× what every loser costs
you, you can be **wrong more often than you're right** and still make money. At R:R below 2, you need a
high win rate just to break even — and nobody has a reliably high win rate. **When you see that red
banner, skip the trade.** This single discipline separates profitable traders from the rest.

### 4.7 Card — `Position size`

Four boxes and a button. This is, in practical terms, **the most valuable feature in the whole app.**

| Field | What to enter |
|---|---|
| **Account (EGP)** | Your total trading capital |
| **Risk %** | How much of it you're willing to lose on *this one trade* — **keep it at 1–2%** |
| **Entry** | Buy price (auto-filled from the trade plan) |
| **Stop** | Stop-loss price (auto-filled from the trade plan) |

Press **`Size position`** and you get back:

| Result | Meaning |
|---|---|
| **Shares** | Exactly how many shares to buy |
| **Risk amount** | What you lose in EGP if the stop is hit |
| **Position cost** | The total EGP this position ties up |

An amber warning line appears if your inputs are risky (for example, risking more than 2%).

**Why this matters more than any indicator:** Most people blow up their account not by picking bad
stocks, but by betting too much on one. If you risk 1% per trade, **ten losses in a row** costs you about
10% — survivable. Risk 10% per trade and the same streak wipes you out. This calculator makes correct
sizing take three seconds, so there's no excuse to guess.

If you leave a box empty it tells you: *"Fill account, risk %, entry and stop first."*

---

## 5. Page 3 — Screener (`screener.html`)

**This is your stock-hunting page** — how you *find* opportunities instead of waiting to hear about them.

Two tabs at the top: **`Scanner`** (run one specific scan) and **`Candidates`** (the merged ranking).

### 5.1 Panel — `Run a scanner`

**The `Scanner` dropdown** offers six hunting tools. Picking one shows its description and rebuilds the
parameter boxes underneath it.

| Scanner | What it hunts for | When to use it |
|---|---|---|
| **Bollinger Squeeze** | Stocks whose price range has compressed to unusually tight (`bbw max` sets how tight) | **Before** a big move. Volatility contracts, then expands — squeezes find coiled springs *before* they jump. The most "early" of all the scans |
| **Volume Breakout** | A volume surge (`volume multiplier` × the 20-day average) happening together with a price move of at least `price change min`% | **As** a move begins. Volume confirms a breakout is real rather than a fake-out |
| **Smart Volume** | Volume breakouts filtered by RSI condition (`rsi range`: oversold / overbought / neutral / any) | When you want breakouts that aren't already exhausted |
| **Momentum Candles** | Strong directional candles in a row (`candle count`) with trend agreement (`pattern type`: bullish/bearish) | To ride an established trend rather than anticipate one |
| **Smart Money Flow** | Index members (`index`, e.g. EGX30) ranked by institutional accumulation evidence over `period` | To find quiet accumulation before the crowd notices |
| **EGX Stock Screen** | The full ranking engine — score, grade, trade setups, quality — filtered by `min score` | Your general-purpose "show me the best-rated stocks" tool |

You can change any parameter or leave the sensible defaults. **Press `Run scanner`** and results appear
below.

### 5.2 Panel — `Results`

A sortable table of everything the scan found.

- **👉 Click any column header** to sort by it; click again to reverse. (An ▲ or ▼ shows the active sort.)
- **👉 Click any row** to open that stock's page.
- The line above the table tells you which scanner ran, how many rows came back, and when.
- `Raw response` (when shown) expands the complete unfiltered data.

**Why sorting matters:** Run the squeeze scan, then sort by volume — now you're seeing coiled stocks that
people are *already* starting to trade. Combining two conditions like this is where screeners earn their
keep.

### 5.3 Tab — `Candidates — merged multi-scanner ranking`

The same powerful list as on the dashboard, but with more rows and a **`Refresh`** button to re-run the
scans on demand. The `scanners` column shows badges for every scan that flagged each stock.

**Why start here:** Sort by the number of scanners that agree. Stocks flagged by three or four different
methods deserve your research time far more than stocks flagged by one.

---

## 6. Page 4 — Backtest (`backtest.html`)

**This page answers one question: "would this strategy actually have worked on this stock?"**
It replays a trading rule over real historical prices and reports what would have happened.

### 6.1 Panel — `Backtest setup`

| Field | Default | What it means |
|---|---|---|
| **Symbol** | *(empty)* | The stock to test. Type it or pick from the suggestions |
| **Strategy** | *(first in list)* | Which trading rule to test — nine available (see below) |
| **Period** | `1y` | How far back to test: `3mo`, `6mo`, `1y`, `2y`, `5y`, `max` |
| **Interval** | `1d` | Candle size: `1d` (daily), `1wk` (weekly), `1h` (hourly) |
| **Commission %** | `0.3` | Your broker's fee per trade |
| **Slippage %** | `0.1` | Realistic allowance for not getting the exact price you wanted |
| **Initial capital (EGP)** | `100000` | Starting money for the simulation |

**The nine strategies:** `rsi`, `bollinger`, `macd`, `ema_cross`, `supertrend`, `donchian`,
`rsi_pullback`, `keltner_breakout`, `triple_ema`. (Each is explained in the [glossary](#9-glossary--every-term-explained).)

**⚠️ Always leave commission and slippage switched on.** A strategy that only makes money when trading is
free is not a strategy. These two numbers are what turn a fantasy backtest into an honest one.

**Three buttons:**

| Button | What it does | Why use it |
|---|---|---|
| **`Run backtest`** | Tests **one** strategy on one stock | Your standard check before trusting a signal |
| **`Compare all`** | Races **all nine** strategies on the same stock and ranks them | Discovers which style suits this particular stock — trending stocks favour moving-average strategies, ranging stocks favour RSI/Bollinger |
| **`Walk-forward`** | Splits history into "learn" and "prove" halves and tests on data the strategy never saw. *(Automatically upgrades a 1-year period to 2 years so there's enough data)* | **The honest test.** See below |

If you forget the symbol or strategy, a message tells you before anything runs.

### 6.2 Tab — `Backtest result` (`Single run`)

Six metric cards, then a chart, then the trade list:

| Card | Meaning | What "good" looks like |
|---|---|---|
| **Return** | Total profit/loss percentage | Must beat **Buy & hold**, or why bother trading? |
| **Win rate** | Percentage of trades that made money | 40–50% is perfectly fine *if* R:R is good |
| **Max drawdown** | The worst peak-to-trough fall along the way | **Ask yourself honestly: could I sit through this without panicking?** |
| **Sharpe** | Return relative to volatility | Above 1 is respectable |
| **Trades** | How many trades occurred | Under ~20 means the result may be luck, not skill |
| **Buy & hold** | What simply buying and waiting would have earned | The benchmark that matters |

**`Equity curve`** — a line chart of your simulated account value over time. **Read the shape, not just
the endpoint:** a smooth rising line is a strategy you could live with; a jagged line ending at the same
place will make you quit halfway through.

**`Trade log`** — every simulated trade, sortable. Useful for spotting whether one lucky trade produced
the whole return.

**`All returned fields`** — expandable full detail.

### 6.3 Tab — `Strategy comparison`

A ranked table of all nine strategies on your chosen stock.

**Why it helps:** Different stocks have different personalities. Instead of assuming MACD works
everywhere, you *measure* which approach has actually suited this company's behaviour.

### 6.4 Tab — `Walk-forward analysis`

Two panels — **`In-sample`** (the "learning" period) and **`Out-of-sample`** (the "proving" period) — plus
a table of test windows.

**Why this is the only test that really counts:** Any strategy can be tuned to look brilliant on history
you already know — that's called curve-fitting, and it's why most backtests lie. Walk-forward hides part
of the data, then tests on it. **If in-sample looks great but out-of-sample is weak, the strategy is
fitted to noise and will fail with your real money.** Only trust strategies that hold up out-of-sample.

---

## 7. Page 5 — Portfolio (`portfolio.html`)

**This page tracks what you actually did, and watches the market for you.** Six panels.

### 7.1 Panel — `Performance`

| Card | Meaning | Why it matters |
|---|---|---|
| **Realized PnL** | Profit/loss on **closed** trades, in EGP | Your actual, banked result |
| **Unrealized PnL** | Profit/loss on **open** positions at current prices | What's still at risk |
| **Win rate** | Percentage of closed trades that won | — |
| **Avg R** | Average result measured in *R* (multiples of what you risked) | **The single best measure of skill.** Avg R above 0.3 with decent volume of trades is genuinely good |
| **Open risk** | Total EGP you'd lose if *every* open stop were hit at once | **Your real exposure right now.** If this exceeds ~6% of your account, you're overexposed regardless of how good each individual trade looks |

`Full performance payload` expands the complete breakdown.

### 7.2 Panel — `Open positions`

A table of your live trades — symbol, entry, stop, targets, quantity, plus live price and running
profit/loss where available.

- **👉 Click a row** to open that stock's page.
- **👉 The red `Close` button** on each row: it asks you for the exit price (pre-filled with the current
  price), then closes the position and records the result. Cancel does nothing; a nonsense price is
  rejected.

**Why logging trades matters:** Memory lies. It remembers the winners and quietly edits out the losers.
A written record is the only way to find out whether your instincts actually work.

### 7.3 Panel — `New position`

| Field | Required? | Notes |
|---|---|---|
| **Symbol** | Yes | e.g. `COMI` |
| **Qty (shares)** | Yes | Use the number the Position-size calculator gave you |
| **Entry** | Yes | Your actual fill price |
| **Stop** | Yes | **Must be below entry** — the app enforces this |
| **Target 1** | No | Optional |
| **Target 2** | No | Optional |
| **Note** | No | Why you took the trade — *write this, you'll thank yourself later* |

Press **`Open position`** to record it. Clear messages appear if anything is missing or invalid.

**Why the app refuses a stop above your entry:** That isn't a stop — it's a guaranteed loss on entry. The
rejection is protecting you from a typo that would corrupt all your risk maths.

### 7.4 Panel — `Closed positions`

Your trade history, including exit price, close date, profit/loss, and **R-multiple** per trade. Sortable
by any column.

**Why it helps:** Sort by R-multiple. Look at your worst trades and ask what they had in common — were
they against the weekly trend? Below R:R 2? In a weak sector? **That pattern is your tuition fee, and
this table is where you collect the lesson.**

### 7.5 Panel — `Alert rules`

This is how the app watches the market **for you** while you're at work.

**To create a rule:** optionally give it a **Name**, choose a **Rule type**, fill the parameters that
appear, and press **`Create rule`**.

| Rule type | Parameters | What it watches | Good for |
|---|---|---|---|
| **price above** | `symbol`, `level` | Price rising above your level | Breakout confirmation |
| **price below** | `symbol`, `level` | Price falling below your level | Support breaks, or a buy-the-dip level |
| **score min** | `universe` *or* `symbol`, `threshold` (default 70) | Any stock in a universe reaching a quality score | Finding new opportunities hands-free |
| **squeeze** | `universe` (default EGX30), `bbw max` (default 0.04) | A stock entering a volatility squeeze | Catching coiled springs early |
| **signal change** | `symbol` | The stock's signal flipping (e.g. buy → sell) | Exit warnings on stocks you hold |
| **entry hit** | `symbol`, `entry` | Price reaching your planned entry | So you never miss your own plan |

**The rules table** shows ID, Name, Type, Params, Enabled (`on`/`off`), Created, and two buttons per row:

- **`Disable` / `Enable`** — pauses or resumes a rule without deleting it.
- **`Delete`** — removes it permanently (asks you to confirm first).

**The `Evaluate now` button** checks every enabled rule immediately instead of waiting for the schedule,
and tells you how many fired.

### 7.6 Panel — `Fired alerts`

The history of triggered alerts: when it fired, which rule, which symbol, the message, and whether it was
**`telegram`** (sent to your phone) or **`local`** (recorded here only). Click a row to open the stock.

**To get alerts on your phone:** add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to the `.env` file.
Without them, alerts still fire and are recorded — they just stay in the app.

### 7.7 What runs automatically

Once the app is running, four jobs work on Cairo time without you touching anything:

| When | What happens | Why |
|---|---|---|
| Every 10 min, Sun–Thu 10:00–14:30 | Checks all your alert rules | Catches your levels during the session |
| Sun–Thu 15:00 | Saves a snapshot of the whole market and re-runs the candidate scans | Builds the score history that makes your charts and alerts smarter over time |
| Sun–Thu 09:30 | Writes the morning brief | Ready before the opening bell |
| Saturday 12:00 | Checks that all symbols are still valid | Catches companies delisted or renamed |

**Leave the app running** during the trading week to get the benefit. Everything still works if you don't
— you just have to press the buttons yourself.

---

## 8. Your daily routine (how to actually use this)

**Evening before / early morning (10 minutes):**
1. Open the **Dashboard**. Read `% Advancing` and the session pill. *Is the market healthy?*
2. Glance at the **Sector heatmap**. *Which sectors are leading?*
3. Read the **Morning brief** (press `Generate` if it's stale).
4. Scan the **Candidates** list. Pick **2–3 names**, ideally from leading sectors.

**Research each candidate (5 minutes each):**
5. Click through to its **Stock page**.
6. Check **Multi-timeframe alignment** first — *if weekly disagrees, stop here and move on.*
7. Check the **Score** bars and the **Smart Money** tab.
8. Read the **Trade plan**. **If the red `Reject: R:R < 2` banner is showing, walk away.**
9. Skim the **News** tab for anything that vetoes the setup.

**Before you commit money:**
10. On the **Backtest** page, run a **Walk-forward** test for that stock. Weak out-of-sample = don't trade it.
11. Back on the stock page, use **Position size** with risk at **1%**. Note the share count.

**Placing and tracking:**
12. Place the order **with your real broker** at the planned entry, and put the **stop-loss in immediately**.
13. On the **Portfolio** page, record it under **New position**, with a note explaining why.
14. Create an **entry hit** or **signal change** alert so the app watches it for you.

**Weekly review (15 minutes):**
15. Open **Closed positions**, sort by R-multiple, and study your worst trades for the common pattern.
16. Check **Open risk** — if it's above ~6% of your account, take something off.

---

## 9. Glossary — every term explained

**Advancers / Decliners** — How many stocks are up vs down today. Together they measure *breadth*.

**ATR (Average True Range)** — How much a stock typically moves in a day, in EGP. Used to place stops far
enough away that normal noise doesn't hit them.

**Backtest** — Replaying a trading rule over past prices to see what it would have earned.

**BBW (Bollinger Band Width)** — How wide the price's volatility envelope is. A *low* BBW = a squeeze.

**Bollinger Bands** — A band drawn above and below the average price. Price tends to stay inside; when the
band narrows sharply, a big move usually follows.

**Breadth** — How *many* stocks participate in a move, not just how far the index went. Weak breadth
behind a rising index means only a few big names are lifting it — a fragile rally.

**Buy & hold** — Simply buying and waiting. The benchmark every strategy must beat.

**Candlestick** — One bar = one time period, showing open, high, low and close.

**Curve-fitting** — Tuning a strategy until it looks perfect on past data. It then fails on new data.
Walk-forward testing exists to expose it.

**Donchian** — A strategy that buys when price breaks above its highest level of the last N days.

**Drawdown** — The fall from a peak to the following trough. *Max drawdown* is the worst one — the real
test of whether you could have stayed in the strategy emotionally.

**EGX30 / EGX70 / EGX100** — Egypt's main indices: the 30 largest and most liquid companies, the next 70,
and the two combined.

**EMA / SMA (Exponential / Simple Moving Average)** — The average price over N periods; EMA weights recent
prices more. `ema_cross` buys when a fast average crosses above a slow one.

**Entry** — The price at which the plan says to buy.

**Fibonacci retracement** — Levels (23.6%, 38.2%, 50%, 61.8%) where pullbacks often stop before the trend
resumes. Buying near one gives you a better price and a tighter stop.

**Keltner Channel** — Like Bollinger Bands but built from ATR. `keltner_breakout` buys a break above the
upper channel.

**Limit-up / limit-down** — EGX caps how far a stock may move in one day. A limit-locked stock often can't
actually be bought or sold — which is why the biggest gainer is frequently untradeable.

**Liquidity** — How easily you can buy or sell without moving the price. Outside EGX30, many Egyptian
stocks are thin: a perfect signal you can't execute is worthless.

**MACD** — A momentum indicator built from two moving averages; signals come from their crossovers.

**Multi-timeframe alignment** — Whether the weekly, daily and intraday trends agree. Alignment is one of
the strongest edges available to a private trader.

**PnL** — Profit and Loss. *Realized* = closed trades. *Unrealized* = open positions at today's price.

**R / R-multiple** — Your result measured in units of what you risked. Risk 1,000 EGP, make 2,000 → +2R.
Speaking in R instead of EGP makes trades comparable across different position sizes.

**R:R (Risk-to-Reward)** — Potential profit ÷ potential loss. **The app rejects anything below 2 for a
reason:** at 2:1 you can be wrong more than half the time and still profit.

**RSI (Relative Strength Index)** — A 0–100 momentum gauge. Traditionally, over 70 = overbought, under 30
= oversold — though in strong trends stocks stay "overbought" for a long time.

**Sharpe ratio** — Return relative to the volatility endured. Higher = smoother ride for the same return.

**Slippage** — The gap between the price you wanted and the price you got. Always assume some.

**Smart money** — Institutional players. "Accumulation" means they appear to be quietly buying;
"distribution" means quietly selling.

**Squeeze** — Volatility compressing to unusual tightness. Volatility is cyclical: quiet periods precede
violent ones, which is why squeezes are hunted *before* the move.

**Stop / Stop-loss** — Your predetermined exit if you're wrong. **The most important number in any trade.**
Place it with your broker at the moment you enter, not later.

**Supertrend** — A trend-following indicator built on ATR that flips between buy and sell states.

**T+2 settlement** — Trades settle two business days after execution; your cash isn't instantly reusable.

**Target 1 / Target 2** — Planned profit-taking levels. Many traders sell half at T1 and move the stop to
break-even.

**Triple EMA** — A strategy using three moving averages (fast, slow, and a long-term trend filter).

**Volume** — Shares traded. Rising price on rising volume is conviction; rising price on falling volume is
suspicion.

**Walk-forward test** — Testing a strategy on data it was never tuned on. The most honest backtest there
is.

**Watchlist** — Your saved shortlist, always visible in the sidebar.

---

## 10. Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `API offline` in the top bar | The server isn't running | Restart it: `.venv\Scripts\python.exe run.py` |
| The page won't load at all | Wrong address, or server stopped | Use **http://127.0.0.1:8646** (not 8642) |
| `No data returned for EGX stocks` | TradingView is rate-limiting after heavy use | Wait 2–5 minutes and refresh. It recovers on its own |
| Candidates spins for a long time | Normal — it's running four market-wide scans | Give it up to a minute |
| `No morning brief yet` / brief fails | No AI key configured | Add `ANTHROPIC_API_KEY` to `.env`, restart the app |
| News tab reports not configured | No news key | Add `MARKETAUX_API_TOKEN` to `.env`, restart |
| Alerts fire but never reach your phone | Telegram not configured | Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`, restart |
| `No price history available for this symbol` | Yahoo has no data for that ticker | Common for micro-caps; the rest of the page still works |
| Score history / snapshot alerts look empty | The daily snapshot hasn't run yet | It runs at 15:00 Cairo on trading days — or trigger it now by opening the app and letting the schedule run |
| `Empty — star a stock.` in the sidebar | No watchlist entries | Open any stock page and click the ☆ |

**Where things live:**

| File | What it is |
|---|---|
| `.env` | Your settings and API keys |
| `data\egx.db` | Your watchlist, positions, alerts, snapshots — **this is your data, back it up** |
| `README.md` | Technical setup notes |
| `USER_GUIDE.md` | This document |

---

### Three rules worth more than any indicator in this app

1. **Never trade without a stop-loss.** Decide your exit before you enter, and place it immediately.
2. **Never risk more than 1–2% of your account on a single trade.** Use the Position size calculator every time.
3. **Never take a setup with R:R below 2.** If the red banner shows, there will be another trade tomorrow.

*Analysis tooling — not financial advice. Data delayed ~15 minutes. You are responsible for your own trades.*
