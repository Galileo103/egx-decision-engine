/* ============================================================
   EGX Decision Engine — shared UI helpers (Module F)
   Globals: el, fmtNum, fmtPct, fmtCompact, toast,
            renderSidebar, renderTopbar, renderFooter,
            plus window.UI with defensive-data helpers.
   Requires api.js loaded first.
   ============================================================ */
(function () {
  "use strict";

  /* ---------------- DOM builder ---------------- */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    for (var k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
      var v = attrs[k];
      if (v === null || v === undefined) continue;
      if (k === "class" || k === "className") node.className = v;
      else if (k === "text") node.textContent = v;
      // No `html` attribute: an innerHTML path is an XSS sink the moment any
      // caller passes API data through it. Nothing in web/ ever used it.
      else if (k === "dataset" && typeof v === "object") {
        for (var d in v) node.dataset[d] = v[d];
      } else if (k.slice(0, 2) === "on" && typeof v === "function") {
        node.addEventListener(k.slice(2).toLowerCase(), v);
      } else if (k === "style" && typeof v === "object") {
        for (var s in v) node.style[s] = v[s];
      } else {
        node.setAttribute(k, v);
      }
    }
    appendChildren(node, children);
    return node;
  }

  function appendChildren(node, children) {
    if (children === null || children === undefined) return;
    if (Array.isArray(children)) {
      for (var i = 0; i < children.length; i++) appendChildren(node, children[i]);
    } else if (children instanceof Node) {
      node.appendChild(children);
    } else {
      node.appendChild(document.createTextNode(String(children)));
    }
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

  /**
   * Return a URL only when it is safe to put in an href, else null.
   * External content (Marketaux headlines carry their own `url`) could
   * otherwise supply `javascript:...`, which executes on click.
   */
  function safeUrl(value) {
    if (typeof value !== "string") return null;
    var trimmed = value.trim();
    return /^https?:\/\//i.test(trimmed) ? trimmed : null;
  }

  /* ---------------- Number coercion & formatting ---------------- */

  function toNum(v) {
    if (v === null || v === undefined || v === "") return null;
    if (typeof v === "number") return isFinite(v) ? v : null;
    if (typeof v === "string") {
      var n = parseFloat(v.replace(/[%,\s]/g, "").replace(/EGP/i, ""));
      return isFinite(n) ? n : null;
    }
    return null;
  }

  function fmtNum(v, digits) {
    var n = toNum(v);
    if (n === null) return "—";
    if (digits === undefined) digits = Math.abs(n) >= 1000 ? 0 : 2;
    return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function fmtCompact(v) {
    var n = toNum(v);
    if (n === null) return "—";
    var a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return fmtNum(n);
  }

  function changeClass(v) {
    var n = toNum(v);
    if (n === null || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  /** Returns a <span> with class up/down/flat, e.g. "+1.23%". */
  function fmtPct(v, digits) {
    var n = toNum(v);
    var span = el("span", { class: "num " + changeClass(n) });
    if (n === null) { span.textContent = "—"; return span; }
    if (digits === undefined) digits = 2;
    span.textContent = (n > 0 ? "+" : "") + n.toFixed(digits) + "%";
    return span;
  }

  /* ---------------- Toast ---------------- */

  function toast(msg, kind) {
    var host = document.getElementById("toast-host");
    if (!host) {
      host = el("div", { id: "toast-host" });
      document.body.appendChild(host);
    }
    var t = el("div", { class: "toast " + (kind || "info"), text: String(msg) });
    host.appendChild(t);
    setTimeout(function () {
      t.style.opacity = "0";
      t.style.transition = "opacity 0.3s";
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
    }, 4200);
  }

  /* ---------------- Defensive data extraction ----------------
     Core-library payload field names vary; these helpers try
     several candidate keys and never assume a shape.          */

  /** First non-null value among candidate keys (case-tolerant). */
  function pick(obj, keys) {
    if (!obj || typeof obj !== "object") return null;
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (obj[k] !== undefined && obj[k] !== null && obj[k] !== "") return obj[k];
    }
    // case-insensitive / snake-camel tolerant second pass
    var lower = {};
    for (var ok in obj) lower[ok.toLowerCase().replace(/[_\s-]/g, "")] = obj[ok];
    for (var j = 0; j < keys.length; j++) {
      var lk = keys[j].toLowerCase().replace(/[_\s-]/g, "");
      if (lower[lk] !== undefined && lower[lk] !== null && lower[lk] !== "") return lower[lk];
    }
    return null;
  }

  function pickNum(obj, keys) { return toNum(pick(obj, keys)); }

  var PRICE_KEYS = ["price", "close", "lastPrice", "last_price", "last", "current_price", "currentPrice", "close_price"];
  var CHANGE_KEYS = ["change_pct", "changePercent", "change_percent", "pct_change", "percent_change", "change%", "chg_pct", "change"];
  var VOLUME_KEYS = ["volume", "vol", "total_volume", "volume_24h", "avg_volume"];
  var SYMBOL_KEYS = ["symbol", "ticker", "name", "code", "sym", "stock"];
  var SIGNAL_KEYS = ["signal", "recommendation", "rating", "verdict", "action", "summary_signal", "rating_text"];

  function symbolOf(row) {
    var s = pick(row, SYMBOL_KEYS);
    if (typeof s !== "string") return null;
    return s.replace(/^EGX:/i, "").trim().toUpperCase();
  }

  /** Find the first array of objects inside a payload, preferring hinted keys. */
  function firstArray(obj, keyHints, _depth) {
    _depth = _depth || 0;
    if (Array.isArray(obj)) return obj;
    if (!obj || typeof obj !== "object" || _depth > 3) return null;
    keyHints = keyHints || [];
    for (var i = 0; i < keyHints.length; i++) {
      var hinted = pick(obj, [keyHints[i]]);
      if (Array.isArray(hinted) && hinted.length) return hinted;
    }
    // any array of dicts
    for (var k in obj) {
      if (Array.isArray(obj[k]) && obj[k].length && typeof obj[k][0] === "object") return obj[k];
    }
    // recurse one level into nested dicts
    for (var k2 in obj) {
      if (obj[k2] && typeof obj[k2] === "object" && !Array.isArray(obj[k2])) {
        var found = firstArray(obj[k2], keyHints, _depth + 1);
        if (found) return found;
      }
    }
    return null;
  }

  /** Deep-find the first nested dict containing ALL of the given keys (fuzzy). */
  function findObjWith(obj, keys, _depth) {
    _depth = _depth || 0;
    if (!obj || typeof obj !== "object" || _depth > 4) return null;
    if (!Array.isArray(obj)) {
      var hasAll = true;
      for (var i = 0; i < keys.length; i++) {
        if (pick(obj, [keys[i]]) === null) { hasAll = false; break; }
      }
      if (hasAll) return obj;
    }
    var vals = Array.isArray(obj) ? obj : Object.keys(obj).map(function (k) { return obj[k]; });
    for (var j = 0; j < vals.length; j++) {
      if (vals[j] && typeof vals[j] === "object") {
        var found = findObjWith(vals[j], keys, _depth + 1);
        if (found) return found;
      }
    }
    return null;
  }

  /* ---------------- Fallback object renderer ----------------
     Always renders SOMETHING legible from an unknown dict.    */

  function prettyKey(k) {
    return String(k).replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
  }

  function renderValue(v, depth) {
    if (v === null || v === undefined) return el("span", { class: "muted", text: "—" });
    if (typeof v === "number") {
      return el("span", { class: "num", text: fmtNum(v, Math.abs(v) < 100 && v % 1 !== 0 ? 2 : undefined) });
    }
    if (typeof v === "boolean") return el("span", { class: v ? "up" : "muted", text: v ? "yes" : "no" });
    if (typeof v === "string") {
      if (/^https?:\/\//.test(v)) return el("a", { href: v, target: "_blank", rel: "noopener", text: v.length > 60 ? v.slice(0, 57) + "…" : v });
      return el("span", { text: v.length > 400 ? v.slice(0, 397) + "…" : v });
    }
    if (Array.isArray(v)) {
      if (!v.length) return el("span", { class: "muted", text: "(empty)" });
      if (typeof v[0] !== "object") return el("span", { class: "num", text: v.slice(0, 20).join(", ") + (v.length > 20 ? " …" : "") });
      if (depth >= 2) return el("span", { class: "muted", text: "[" + v.length + " items]" });
      var wrap = el("div");
      v.slice(0, 12).forEach(function (item, i) {
        wrap.appendChild(el("div", { class: "muted", style: { fontSize: "11px", marginTop: i ? "6px" : "0" }, text: "#" + (i + 1) }));
        wrap.appendChild(renderObject(item, depth + 1));
      });
      if (v.length > 12) wrap.appendChild(el("div", { class: "muted", text: "… " + (v.length - 12) + " more" }));
      return wrap;
    }
    if (typeof v === "object") {
      if (depth >= 3) return el("span", { class: "muted", text: "{…}" });
      return renderObject(v, depth + 1);
    }
    return el("span", { text: String(v) });
  }

  /** Definition-list rendering of an arbitrary dict — the last-resort renderer. */
  function renderObject(obj, depth) {
    depth = depth || 0;
    if (obj === null || obj === undefined) return el("div", { class: "empty-note", text: "No data." });
    if (typeof obj !== "object") return el("div", { class: "num", text: String(obj) });
    if (Array.isArray(obj)) return renderValue(obj, depth);
    var keys = Object.keys(obj);
    if (!keys.length) return el("div", { class: "empty-note", text: "No data." });
    var dl = el("dl", { class: "kv" });
    keys.forEach(function (k) {
      dl.appendChild(el("dt", { text: prettyKey(k), title: k }));
      var dd = el("dd");
      dd.appendChild(renderValue(obj[k], depth));
      dl.appendChild(dd);
    });
    return dl;
  }

  /* ---------------- Loading / error states ---------------- */

  function skeleton(lines) {
    var box = el("div", { class: "skeleton", "aria-busy": "true" });
    lines = lines || 4;
    for (var i = 0; i < lines; i++) {
      box.appendChild(el("div", { class: "sk-line", style: { width: (55 + ((i * 17) % 40)) + "%" } }));
    }
    return box;
  }

  function loadingPill(msg) {
    return el("div", { class: "loading-pill", text: msg || "Loading…" });
  }

  /** Turn upstream/plumbing errors into a sentence a trader can act on. */
  function friendlyError(msg) {
    var s = String(msg || "Something went wrong.");
    var label = /^([^:]{1,40}):\s/.exec(s);
    var prefix = label ? label[1] + ": " : "";
    if (/Upstream TradingView|transient errors|empty-body outage|scanner\.tradingview/i.test(s)) {
      return prefix + "TradingView is pausing this app for a minute or two (rate limit). The chart, your position and patterns still work from Yahoo data. Reload in a minute for the score and trade plan.";
    }
    if (/rate limit|429|backing off/i.test(s)) {
      return prefix + "Yahoo is rate-limiting requests for a short while. Cached data is shown where available; try again in a minute.";
    }
    if (/Failed to fetch|NetworkError|ECONNREFUSED|API offline/i.test(s)) {
      return prefix + "The app's server is not responding. Is it running? (see the guide, section 1)";
    }
    return s;
  }

  function errorBox(msg) {
    var friendly = friendlyError(msg);
    var box = el("div", { class: "error-box", text: friendly });
    if (friendly !== String(msg)) box.title = String(msg);   // the raw error stays one hover away
    return box;
  }

  /**
   * Standard fetch-into-container pattern: shows skeleton, runs loader(),
   * passes result to render(container, data); on failure shows inline error.
   */
  async function load(container, loader, render, opts) {
    opts = opts || {};
    clear(container).appendChild(opts.pill ? loadingPill(opts.pill) : skeleton(opts.lines || 4));
    try {
      var data = await loader();
      clear(container);
      render(container, data);
    } catch (e) {
      clear(container).appendChild(errorBox((opts.label ? opts.label + ": " : "") + (e && e.message ? e.message : e)));
    }
  }

  /* ---------------- Chrome: sidebar / topbar / footer ---------------- */

  var NAV = [
    { href: "index.html", label: "Dashboard", ico: "▦", key: "dashboard" },
    { href: "screener.html", label: "Screener", ico: "⌗", key: "screener" },
    { href: "backtest.html", label: "Backtest", ico: "↻", key: "backtest" },
    { href: "portfolio.html", label: "Portfolio", ico: "☷", key: "portfolio" },
  ];

  function renderSidebar(active) {
    var host = document.getElementById("sidebar");
    if (!host) {
      host = el("aside", { id: "sidebar" });
      document.body.insertBefore(host, document.body.firstChild);
    }
    host.className = "sidebar";
    clear(host);

    host.appendChild(el("div", { class: "brand" }, [
      el("span", { class: "brand-mark", text: "EGX//DE" }),
      el("span", { class: "brand-sub", text: "Decision Engine" }),
    ]));

    var nav = el("nav", { class: "nav" });
    NAV.forEach(function (item) {
      nav.appendChild(el("a", {
        href: item.href,
        class: item.key === String(active || "").toLowerCase() ? "active" : "",
      }, [el("span", { class: "nav-ico", text: item.ico }), item.label]));
    });
    host.appendChild(nav);

    var wlWrap = el("div");
    wlWrap.appendChild(el("div", { class: "side-section-title", text: "Watchlist" }));
    var wlBox = el("div", { class: "watchlist-quick" });
    wlBox.appendChild(loadingPill(""));
    wlWrap.appendChild(wlBox);
    host.appendChild(wlWrap);

    API.get("/api/watchlist").then(function (data) {
      clear(wlBox);
      var rows = Array.isArray(data) ? data : firstArray(data, ["watchlist", "items", "symbols"]) || [];
      if (!rows.length) {
        wlBox.appendChild(el("div", { class: "side-empty", text: "Empty — star a stock." }));
        return;
      }
      rows.slice(0, 15).forEach(function (row) {
        var sym = typeof row === "string" ? row : symbolOf(row);
        if (!sym) return;
        var price = typeof row === "object" ? pickNum(row, PRICE_KEYS) : null;
        wlBox.appendChild(el("a", { href: "stock.html?symbol=" + encodeURIComponent(sym) }, [
          el("span", { text: sym }),
          el("span", { class: "wl-note num " + (price !== null ? "" : "muted"), text: price !== null ? fmtNum(price) : (pick(row, ["note"]) || "") }),
        ]));
      });
    }).catch(function () {
      clear(wlBox).appendChild(el("div", { class: "side-empty", text: "Watchlist unavailable." }));
    });
  }

  function renderTopbar(title) {
    var host = document.getElementById("topbar");
    if (!host) {
      var main = document.querySelector(".main") || document.body;
      host = el("header", { id: "topbar" });
      main.insertBefore(host, main.firstChild);
    }
    host.className = "topbar";
    clear(host);

    host.appendChild(el("div", { class: "page-title", text: title || document.title || "EGX Decision Engine" }));

    var pill = el("span", { class: "pill loading", id: "session-pill" }, [
      el("span", { class: "dot" }), "checking…",
    ]);
    host.appendChild(pill);
    host.appendChild(buildDataAgeChip());
    host.appendChild(el("div", { class: "spacer" }));

    host.appendChild(buildSearchBox());

    // Session pill from /api/health
    API.get("/api/health").then(function (h) {
      var sess = (h && h.session) || {};
      var open = !!pick(sess, ["open", "is_open", "market_open"]);
      clear(pill);
      pill.className = "pill " + (open ? "open" : "closed");
      pill.appendChild(el("span", { class: "dot" }));
      pill.appendChild(document.createTextNode(open ? "Market open" : "Market closed"));
      var nx = pick(sess, ["next_open", "nextOpen"]);
      if (!open && typeof nx === "string") pill.title = "Next open: " + nx;
    }).catch(function () {
      clear(pill);
      pill.className = "pill closed";
      pill.appendChild(el("span", { class: "dot" }));
      pill.appendChild(document.createTextNode("API offline"));
    });

  }

  /* ---------------- Data-age chip ----------------
     Every number on screen comes from a delayed feed and only refreshes on
     page load — this chip says when the data was actually fetched, and goes
     amber once it's more than ~20 minutes old.                            */

  var _dataAgeTimer = null;

  function buildDataAgeChip() {
    var chip = el("span", { class: "pill loading", id: "data-age-pill", text: "no data yet" });
    chip.title = "When this page last received data from the API. Feed itself is delayed ~15 min (or end-of-day).";

    function tick() {
      var at = (window.API && API.lastDataAt) ? API.lastDataAt() : null;
      if (!at) { chip.textContent = "no data yet"; chip.className = "pill loading"; return; }
      var d = new Date(at);
      var hh = String(d.getHours()).padStart(2, "0");
      var mm = String(d.getMinutes()).padStart(2, "0");
      var ageMin = Math.floor((Date.now() - at) / 60000);
      chip.textContent = "data as of " + hh + ":" + mm + " (~15m delayed feed)";
      chip.className = "pill " + (ageMin >= 20 ? "closed" : "open");
      if (ageMin >= 20) chip.textContent += " · " + ageMin + "m old — reload";
    }

    if (_dataAgeTimer) clearInterval(_dataAgeTimer);
    _dataAgeTimer = setInterval(tick, 30000);
    setTimeout(tick, 800);   // after the page's first fetches usually land
    setTimeout(tick, 4000);
    return chip;
  }

  /* ---------------- Symbol catalog + autocomplete ---------------- */

  var CATALOG_KEY = "egxde.symbols.v1";
  var _catalogPromise = null;

  /**
   * Full EGX ticker catalog ({symbol, name, sector, index}), cached in
   * sessionStorage so every page after the first renders suggestions instantly.
   * Resolves to [] rather than rejecting — typing a symbol must always work.
   */
  function loadCatalog() {
    if (_catalogPromise) return _catalogPromise;

    var cached = null;
    try {
      var raw = sessionStorage.getItem(CATALOG_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && parsed.length) cached = parsed;
      }
    } catch (e) { /* private mode / disabled storage */ }

    if (cached) {
      _catalogPromise = Promise.resolve(cached);
      return _catalogPromise;
    }

    _catalogPromise = API.get("/api/symbols").then(function (res) {
      var rows = (res && res.symbols) || [];
      if (!rows.length) return [];
      try { sessionStorage.setItem(CATALOG_KEY, JSON.stringify(rows)); } catch (e) { /* ignore */ }
      return rows;
    }).catch(function () { return []; });

    return _catalogPromise;
  }

  /**
   * Rank catalog rows against a query: exact ticker, then ticker prefix,
   * then name prefix, then name/ticker substring. Catalog order (index
   * membership, then market cap) breaks ties, so EGX30 names surface first.
   */
  function matchSymbols(rows, query, limit) {
    var q = String(query || "").trim().toUpperCase().replace(/^EGX:/, "");
    if (!q) return rows.slice(0, limit || 10);

    var hits = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var sym = row.symbol || "";
      var name = (row.name || "").toUpperCase();
      var rank = -1;

      if (sym === q) rank = 0;
      else if (sym.indexOf(q) === 0) rank = 1;
      else if (name.indexOf(q) === 0) rank = 2;
      else if (name.indexOf(q) !== -1) rank = 3;
      else if (sym.indexOf(q) !== -1) rank = 4;

      if (rank >= 0) hits.push({ row: row, rank: rank, ord: i });
    }

    hits.sort(function (a, b) { return a.rank - b.rank || a.ord - b.ord; });
    return hits.slice(0, limit || 10).map(function (h) { return h.row; });
  }

  /**
   * Top-bar search: a real autocomplete (keyboard-navigable dropdown showing
   * company name, sector and index badge) rather than a bare datalist.
   */
  function buildSearchBox() {
    var rows = [];
    var open = false;
    var active = -1;
    var items = [];

    var input = el("input", {
      type: "text", placeholder: "Search symbol or company…",
      autocomplete: "off", spellcheck: "false", "aria-label": "Search symbol",
      role: "combobox", "aria-autocomplete": "list", "aria-expanded": "false",
    });
    var menu = el("div", { class: "ac-menu", role: "listbox" });
    var box = el("div", { class: "search-box" }, [
      el("span", { class: "search-ico", text: "⌕" }), input, menu,
    ]);

    function go(symbol) {
      var v = String(symbol || "").trim().toUpperCase().replace(/^EGX:/, "");
      if (v) window.location.href = "stock.html?symbol=" + encodeURIComponent(v);
    }

    function close() {
      open = false; active = -1; items = [];
      clear(menu);
      menu.classList.remove("show");
      input.setAttribute("aria-expanded", "false");
    }

    function highlight(idx) {
      if (!items.length) return;
      if (idx < 0) idx = items.length - 1;
      if (idx >= items.length) idx = 0;
      active = idx;
      for (var i = 0; i < items.length; i++) {
        items[i].el.classList.toggle("active", i === active);
      }
      if (items[active] && items[active].el.scrollIntoView) {
        items[active].el.scrollIntoView({ block: "nearest" });
      }
    }

    function render(list) {
      clear(menu);
      items = [];
      if (!list.length) {
        menu.appendChild(el("div", { class: "ac-empty", text: "No matching symbol" }));
        menu.classList.add("show");
        open = true;
        input.setAttribute("aria-expanded", "true");
        return;
      }
      list.forEach(function (row) {
        var meta = [];
        if (row.sector) meta.push(row.sector);
        var node = el("div", { class: "ac-item", role: "option" }, [
          el("span", { class: "ac-sym", text: row.symbol }),
          el("span", { class: "ac-name", text: row.name || "" }),
          row.index ? el("span", { class: "ac-badge", text: row.index }) : null,
        ].filter(Boolean));
        if (meta.length) node.title = meta.join(" · ");
        node.addEventListener("mousedown", function (ev) {
          ev.preventDefault();          // keep focus so blur doesn't beat the click
          go(row.symbol);
        });
        node.addEventListener("mouseenter", function () {
          highlight(items.findIndex(function (it) { return it.el === node; }));
        });
        menu.appendChild(node);
        items.push({ el: node, symbol: row.symbol });
      });
      menu.classList.add("show");
      open = true;
      active = -1;
      input.setAttribute("aria-expanded", "true");
    }

    function refresh() {
      var q = input.value.trim();
      if (!q) { close(); return; }
      render(matchSymbols(rows, q, 10));
    }

    input.addEventListener("input", refresh);
    input.addEventListener("focus", function () { if (input.value.trim()) refresh(); });
    input.addEventListener("blur", function () { setTimeout(close, 120); });

    input.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        if (!open) refresh(); else highlight(active + 1);
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        if (open) highlight(active - 1);
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        // A highlighted suggestion wins; otherwise honour exactly what was typed.
        if (open && active >= 0 && items[active]) go(items[active].symbol);
        else go(input.value);
      } else if (ev.key === "Escape") {
        close();
        input.blur();
      }
    });

    loadCatalog().then(function (list) {
      rows = list || [];
      if (rows.length && document.activeElement === input && input.value.trim()) refresh();
    });

    return box;
  }

  /**
   * Mobile navigation. app.css hides the sidebar below 860px and the topbar
   * carries no links, so every page was a dead end on a phone or a
   * half-width laptop window. This renders a horizontal nav strip that CSS
   * shows only at those widths.
   */
  function renderMobileNav(active) {
    if (document.getElementById("mobile-nav")) return;
    var bar = el("nav", { id: "mobile-nav", class: "mobile-nav", "aria-label": "Main" });
    NAV.forEach(function (item) {
      bar.appendChild(el("a", {
        href: item.href,
        class: item.key === String(active || "").toLowerCase() ? "active" : "",
      }, [el("span", { class: "nav-ico", text: item.ico }), item.label]));
    });
    var host = document.querySelector(".main") || document.querySelector(".pg-main") || document.body;
    var topbar = document.getElementById("topbar");
    if (topbar && topbar.parentNode === host) host.insertBefore(bar, topbar.nextSibling);
    else host.insertBefore(bar, host.firstChild);
    return bar;
  }

  function renderFooter() {
    var existing = document.querySelector(".footer");
    if (existing) return existing;
    var f = el("footer", { class: "footer" }, [
      el("span", { text: "Analysis tooling — not financial advice. Data delayed ~15 min." }),
      el("span", { class: "muted", text: "EGX Decision Engine · local" }),
    ]);
    (document.querySelector(".main") || document.body).appendChild(f);
    return f;
  }

  /* ---------------- Exports ---------------- */

  window.el = el;
  window.fmtNum = fmtNum;
  window.fmtPct = fmtPct;
  window.fmtCompact = fmtCompact;
  window.toast = toast;
  window.renderSidebar = renderSidebar;
  window.renderTopbar = renderTopbar;
  window.renderFooter = renderFooter;
  window.renderMobileNav = renderMobileNav;
  window.safeUrl = safeUrl;

  window.UI = {
    el: el, clear: clear, toast: toast,
    fmtNum: fmtNum, fmtPct: fmtPct, fmtCompact: fmtCompact,
    toNum: toNum, changeClass: changeClass,
    pick: pick, pickNum: pickNum, symbolOf: symbolOf, safeUrl: safeUrl,
    renderMobileNav: renderMobileNav,
    firstArray: firstArray, findObjWith: findObjWith,
    renderObject: renderObject, renderValue: renderValue,
    skeleton: skeleton, loadingPill: loadingPill, errorBox: errorBox, load: load,
    renderSidebar: renderSidebar, renderTopbar: renderTopbar, renderFooter: renderFooter,
    loadCatalog: loadCatalog, matchSymbols: matchSymbols,
    KEYS: { PRICE: PRICE_KEYS, CHANGE: CHANGE_KEYS, VOLUME: VOLUME_KEYS, SYMBOL: SYMBOL_KEYS, SIGNAL: SIGNAL_KEYS },
  };
})();
