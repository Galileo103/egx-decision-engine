# Senior UI/UX Engineer — Full Review (2026-08-31)

The complete frontend review from the seven-persona panel, preserved verbatim
in substance, with a **STATUS** line added per finding showing what happened to
it across Tiers 1–4. Consolidated cross-reviewer findings: `PANEL_REVIEW.md`.

## Overall verdict

**Strong for a hand-built personal tool; two apps wearing one skin.** The
foundations are unusually good for vanilla JS: real loading skeletons, inline
error boxes everywhere (no infinite spinners), toasts, tabular numerals,
right-aligned numeric columns (on two pages), correct green=up/red=down for
EGX, signed percentages so gain/loss is never color-only, and a genuinely nice
keyboard-navigable symbol autocomplete (`ui.js`). But the codebase has forked
into two design systems — index/stock use `app.css` (`.card`/`.tbl`), while
screener/backtest/portfolio each carry a duplicated ~275-line copy of a second
framework (`window.PG`) plus ~50 lines of duplicated `.pg-*` CSS. The
decision-critical content (candidates, trade plan) is structurally sound but
buried or diluted by "render whatever the API sent" auto-tables, there is no
data-age indicator on prices despite a 15-min-delayed feed, mobile users lose
all navigation, and the UI is English-only for an Arabic-speaking user whose
own manual (`USER_GUIDE_AR.md`) has to apologize for it.

## High severity

### H1. ~825 lines of copy-pasted `window.PG` across three pages — guaranteed drift
The identical IIFE was embedded in portfolio.html, screener.html and
backtest.html; any bug fix had to be made in three places. The three pages
also each re-declared the full `.pg-*` stylesheet inline with different radii
(10px vs `--radius: 8px`), different gaps (20px vs 14px) and different table
styling from app.css.
**STATUS: ✅ FIXED (Tier 4)** — extracted to shared `web/assets/pg.js` +
`pg.css` (~976 duplicated lines removed); layout tokens now follow app.css.
The extraction initially dropped four page-specific classes
(`pg-tabs`/`pg-tab.active`/`pg-subhead`/`pg-wf-grid`) — caught by the Tier 4
post-review and restored.

### H2. `javascript:` URL injection via external news data (Marketaux)
`stock.html` set a news link's `href` from the API payload via `setAttribute`
with no scheme check; a news item whose `url` is `javascript:...` executes on
click. Related latent risks: `el()`'s `html:` attr → innerHTML, and the
`pctNode` fallback `span.innerHTML = String(r)`.
**STATUS: ✅ FIXED (Tier 4 + post-review)** — `UI.safeUrl()` gates news hrefs
to http(s) with `rel="noopener noreferrer"`; `pctNode` uses textContent;
`el()`'s `html:` branch deleted outright and `PG.mk` strips `html` before
delegating.

### H3. No navigation at all below 860px
`app.css` hides the sidebar — the only nav — under 860px with no fallback:
every page is a dead end on a phone or half-width window.
**STATUS: ✅ FIXED (Tier 4 + post-review)** — `renderMobileNav()` renders a
horizontal nav strip on all five pages, shown only ≤860px; the post-review
found it pinned underneath the sticky topbar when scrolled, so the topbar goes
static at those widths and the nav pins at the true top.

### H4. Price data carries no "as of" timestamp anywhere it matters
The footer's static "Data delayed ~15 min" was the only staleness signal;
data loads once per page and silently ages.
**STATUS: ✅ FIXED (Tier 1)** — a topbar data-age chip on every page shows
"data as of HH:MM", turning amber with a reload prompt at 20+ minutes stale.
Tier 2 added per-price provenance (`price_source`, mark as-of dates) and the
alert messages carry the snapshot date.

## Medium severity

### M1. Numeric columns left-aligned and headers unlabeled on 3 of 5 pages
The pg-table set only the mono font, defeating tabular-nums.
**STATUS: ✅ FIXED (Tier 4 + post-review)** — `.pg-table td.pg-num, th.pg-num`
right-aligned; numeric detection excludes dates (`closed_at` had matched
"close") and 0/1 flag columns, and alignment follows the column decision.

### M2. Auto-generated tables dump up to 12 raw API columns with raw-key headers
Screener results deserve a curated schema (Symbol · Price · Chg% · Score ·
Signal · key metric) with the rest behind the details block, like the
dashboard's curated 4-column tables.
**STATUS: ⏳ DEFERRED** — auto-tables improved (priority ordering includes the
new `family_count`; alignment fixed) but a curated fixed schema was not built.

### M3. `fmtNum`'s magnitude-dependent decimals break column consistency
`digits = |n| >= 1000 ? 0 : 2` mixes 999.99 with 1,250 in one column; EGX
prices trade to 2 dp regardless of magnitude. EGP labeling inconsistent.
**STATUS: ⏳ DEFERRED.**

### M4. `window.prompt()` to close a position; sizer accepts stop ≥ entry
The most consequential action in the app went through a native prompt with no
P&L preview.
**STATUS: ◐ PARTIAL** — the close flow now re-shows your entry note, asks
"did you follow the plan?", and reports net PnL + R in the toast (Tier 3);
stop ≥ entry is rejected server-side by both the sizer and open_position. The
full inline close dialog with a pre-commit P&L preview remains deferred (the
one explicitly-deferred UX item, noted in PANEL_REVIEW.md).

### M5. `drawEquity` leaks a window resize listener and an orphaned chart per backtest run
`charts.js` already solved this with a registry + ResizeObserver; backtest.html
bypasses it.
**STATUS: ⏳ DEFERRED.**

### M6. No stale-response guards (AbortController / sequence tokens)
An older `loadPositions` response can paint over a newer one on rapid actions.
**STATUS: ⏳ DEFERRED.**

### M7. English-only, LTR-only UI for an Arabic-speaking user
Autocomplete matches only English company names; the Arabic guide exists to
bridge the gap. Recommended minimum: Arabic name search in the symbol catalog.
**STATUS: ⏭ SKIPPED BY USER CHOICE** (asked 2026-08-31; revisit anytime).

## Low severity

- **L1. URL scheme inconsistency** (relative vs absolute asset paths across
  pages) — ⏳ deferred.
- **L2. Accessibility gaps** — ◐ partial: sortable headers got
  tabindex/role/`aria-sort`/keyboard handlers (Tier 4); tab `role`s, toast
  `aria-live`, star `aria-pressed`, autocomplete `aria-activedescendant`
  remain deferred.
- **L3. Hardcoded theme colors bypassing tokens** (overlay hexes, drawEquity
  colors, heatmap rgba) — ⏳ deferred.
- **L4. Chart CDN is unpkg** — single external point of failure for a local
  tool; vendoring recommended — ⏳ deferred.
- **L5. Two different symbol-input widgets** (rich autocomplete vs bare
  datalist vs plain text input) — ⏳ deferred.
- **L6. Duplicated footers; unused `renderFooter()`** — ⏳ deferred.

## What's done well (worth preserving) — reviewer's own list

Defensive key-picking (`U.pick`/`firstArray`) degrading unknown payloads to a
legible dl; the plan-consistency guard ("entry at/below stop — do not trade");
the R:R reject banner; the MTF "failed timeframe" note; buttons disabling
during async with honest duration hints; sessionStorage symbol-catalog caching.

## Top 5 UX enhancements by decision-making payoff — reviewer's ranking

1. **Put "what do I do today?" above the fold on the dashboard** — Candidates
   as the primary top-left panel, movers demoted to a compact strip.
   **STATUS: ⏳ deferred** (the candidates themselves were made trustworthy in
   Tier 3; the dashboard hierarchy was not reworked).
2. **Data-age everywhere prices appear, plus refresh** — ✅ done (Tier 1/2).
3. **Decision-grade close-position flow** — ◐ partial (journaling + net PnL/R
   feedback added; inline pre-commit preview deferred).
4. **Curated screener/positions columns with right-aligned numerics** —
   ◐ partial (alignment done; curated schema deferred).
5. **Arabic-aware search** — ⏭ skipped by user choice.
