/* ============================================================
   EGX Decision Engine — chart helpers (Module F)
   Wraps Lightweight Charts v4 (standalone CDN build, loaded by
   each page via <script src=".../lightweight-charts@4.2.0/...">).

   window.Charts = {
     renderCandles(containerId, candles, overlays) -> chart|null
       candles: [{time:"YYYY-MM-DD", open, high, low, close, volume}]
       overlays: [{price:Number, title:String, color?, dashed?}]
     renderLine(containerId, points, opts) -> chart|null
       points: [{time, value}] (equity curves etc.)
   }
   Both destroy any previous chart in the container, autosize via
   ResizeObserver, and render an inline error box if the library
   is missing or the data is unusable — never a blank page.
   ============================================================ */
(function () {
  "use strict";

  var registry = {}; // containerId -> {chart, ro}

  function cssVar(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  function theme() {
    return {
      bg: cssVar("--panel", "#161D22"),
      ink: cssVar("--ink", "#E8E6DE"),
      muted: cssVar("--muted", "#8B958F"),
      line: cssVar("--line", "#26313A"),
      up: cssVar("--up", "#34C77B"),
      down: cssVar("--down", "#E5534B"),
      accent: cssVar("--accent", "#2FBFA0"),
      warn: cssVar("--warn", "#D2A44C"),
    };
  }

  function fail(container, msg) {
    container.innerHTML = "";
    var box = document.createElement("div");
    box.className = "error-box";
    box.textContent = msg;
    container.appendChild(box);
    return null;
  }

  function destroyExisting(containerId) {
    var prev = registry[containerId];
    if (prev) {
      try { if (prev.ro) prev.ro.disconnect(); } catch (e) { /* noop */ }
      try { prev.chart.remove(); } catch (e) { /* noop */ }
      delete registry[containerId];
    }
  }

  function baseChart(container, containerId) {
    var t = theme();
    var chart = LightweightCharts.createChart(container, {
      width: container.clientWidth || 600,
      height: container.clientHeight || 420,
      layout: {
        background: { type: "solid", color: t.bg },
        textColor: t.muted,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(38,49,58,0.35)" },
        horzLines: { color: "rgba(38,49,58,0.35)" },
      },
      rightPriceScale: { borderColor: t.line },
      timeScale: { borderColor: t.line, timeVisible: false },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: t.muted, width: 1, style: 3, labelBackgroundColor: t.accent },
        horzLine: { color: t.muted, width: 1, style: 3, labelBackgroundColor: t.accent },
      },
    });
    var ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(function () {
        try {
          chart.applyOptions({ width: container.clientWidth, height: container.clientHeight || 420 });
        } catch (e) { /* chart removed */ }
      });
      ro.observe(container);
    }
    registry[containerId] = { chart: chart, ro: ro };
    return chart;
  }

  function num(v) {
    var n = typeof v === "number" ? v : parseFloat(v);
    return isFinite(n) ? n : null;
  }

  function normTime(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return v > 1e10 ? Math.floor(v / 1000) : Math.floor(v);
    var s = String(v);
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : Math.floor(d.getTime() / 1000);
  }

  /* ---------------- Indicator math (pure, also used by tests) ----------------
     Every verdict on the stock page is an average-based call (Trend pillar =
     price vs the 20/50-day, weekly 10/40-week), yet the chart used to show
     candles alone, so a technical analyst could not verify what the text
     claimed. These helpers draw exactly what the services compute. */

  /** Simple moving average of closes; null until n bars exist. */
  function smaSeries(closes, n) {
    var out = new Array(closes.length).fill(null), sum = 0;
    for (var i = 0; i < closes.length; i++) {
      sum += closes[i];
      if (i >= n) sum -= closes[i - n];
      if (i >= n - 1) out[i] = sum / n;
    }
    return out;
  }

  /** ATR14 as the Guardian computes it: simple mean of the last `period` true ranges. */
  function atrSeries(bars, period) {
    var out = new Array(bars.length).fill(null), trs = [];
    for (var i = 0; i < bars.length; i++) {
      var b = bars[i], tr = b.high - b.low;
      if (i > 0) tr = Math.max(tr, Math.abs(b.high - bars[i - 1].close), Math.abs(b.low - bars[i - 1].close));
      trs.push(tr);
      if (trs.length >= Math.max(3, Math.floor(period / 2))) {
        var w = trs.slice(-period), s = 0;
        for (var k = 0; k < w.length; k++) s += w[k];
        out[i] = s / w.length;
      }
    }
    return out;
  }

  /** Relative volume per bar: volume / median of the previous `n` non-zero volumes (null < 10 prior). */
  function rvolSeries(volumes, n) {
    var out = new Array(volumes.length).fill(null);
    for (var i = 1; i < volumes.length; i++) {
      var w = [];
      for (var k = Math.max(0, i - n); k < i; k++) if (volumes[k] > 0) w.push(volumes[k]);
      if (w.length < 10 || !(volumes[i] > 0)) continue;
      w.sort(function (a, b) { return a - b; });
      var med = w[Math.floor(w.length / 2)];
      out[i] = med > 0 ? volumes[i] / med : null;
    }
    return out;
  }

  /**
   * Chandelier trail from the entry bar on: highest close since entry minus
   * mult x ATR14, never lowered (a trailing stop only rises). Returns
   * [{time, value}] for bars at/after `sinceTime` (YYYY-MM-DD).
   */
  function chandelierSeries(bars, sinceTime, mult, period) {
    var atr = atrSeries(bars, period || 14), out = [], hi = null, trail = null;
    for (var i = 0; i < bars.length; i++) {
      if (String(bars[i].time) < String(sinceTime)) continue;
      hi = hi === null ? bars[i].close : Math.max(hi, bars[i].close);
      if (atr[i] === null) continue;
      var lvl = hi - mult * atr[i];
      trail = trail === null ? lvl : Math.max(trail, lvl);
      out.push({ time: bars[i].time, value: trail });
    }
    return out;
  }

  var INDICATOR_KEY = "egxde.chart.indicators.v1";
  var INDICATOR_DEFAULTS = { sma20: true, sma50: true, sma200: true, chandelier: true, rvol: true };
  var INDICATOR_LABELS = {
    sma20: ["SMA 20", "20-day simple moving average — the Trend pillar's short average"],
    sma50: ["SMA 50", "50-day simple moving average — the Trend pillar's main line (price above a rising 50-day = uptrend)"],
    sma200: ["SMA 200", "200-day simple moving average — the long-term line the levels card also uses"],
    chandelier: ["Chandelier", "Trailing stop the Guardian uses: highest close since your entry minus 2.5 x ATR14, never lowered"],
    rvol: ["RVOL colours", "Volume bars: bright = at least 1.5x the 20-day median (heavy), faint = under 0.7x (quiet)"],
  };

  function loadIndicatorPrefs() {
    var prefs = {};
    for (var k in INDICATOR_DEFAULTS) prefs[k] = INDICATOR_DEFAULTS[k];
    try {
      var raw = localStorage.getItem(INDICATOR_KEY);
      if (raw) { var saved = JSON.parse(raw); for (var j in saved) if (j in prefs) prefs[j] = !!saved[j]; }
    } catch (e) { /* storage unavailable: defaults */ }
    return prefs;
  }

  function saveIndicatorPrefs(prefs) {
    try { localStorage.setItem(INDICATOR_KEY, JSON.stringify(prefs)); } catch (e) { /* noop */ }
  }

  /** Legend chips (one per indicator) that toggle and re-render the chart. */
  function renderLegend(legendEl, prefs, available, onToggle) {
    legendEl.innerHTML = "";
    Object.keys(INDICATOR_LABELS).forEach(function (key) {
      if (available[key] === false) return;
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chart-chip" + (prefs[key] ? " on" : "") + " chip-" + key;
      chip.textContent = INDICATOR_LABELS[key][0];
      chip.title = INDICATOR_LABELS[key][1] + (prefs[key] ? " — click to hide" : " — click to show");
      chip.setAttribute("aria-pressed", prefs[key] ? "true" : "false");
      chip.addEventListener("click", function () { prefs[key] = !prefs[key]; saveIndicatorPrefs(prefs); onToggle(); });
      legendEl.appendChild(chip);
    });
  }

  /**
   * Candlestick + volume histogram with optional horizontal price lines
   * (entry / stop / targets / fib levels) and, with `opts.indicators`, the
   * averages the verdicts rest on, RVOL-coloured volume and a chandelier trail
   * for a held stock.
   *
   * opts = {
   *   indicators: true,                       // draw SMA 20/50/200 (+ RVOL colours)
   *   legendEl: "chart-legend" | Element,     // where the toggle chips go (optional)
   *   chandelier: { since: "YYYY-MM-DD", atrMult: 2.5 } | null   // held position
   * }
   */
  function renderCandles(containerId, candles, overlays, opts) {
    var container = document.getElementById(containerId);
    if (!container) return null;
    destroyExisting(containerId);
    opts = opts || {};

    if (typeof LightweightCharts === "undefined") {
      return fail(container, "Chart library failed to load (CDN unreachable).");
    }
    if (!Array.isArray(candles) || !candles.length) {
      return fail(container, "No price history available for this symbol.");
    }

    var t = theme();
    var prefs = opts.indicators ? loadIndicatorPrefs() : {};
    var data = [];
    var volRaw = [];
    for (var i = 0; i < candles.length; i++) {
      var c = candles[i] || {};
      var time = normTime(c.time !== undefined ? c.time : (c.date !== undefined ? c.date : c.timestamp));
      var o = num(c.open), h = num(c.high), l = num(c.low), cl = num(c.close);
      if (time === null || o === null || h === null || l === null || cl === null) continue;
      data.push({ time: time, open: o, high: h, low: l, close: cl });
      var vol = num(c.volume);
      volRaw.push(vol === null ? 0 : vol);
    }
    if (!data.length) return fail(container, "Price history came back in an unreadable format.");

    // Volume bars: direction gives the hue, relative volume the intensity — a
    // breakout bar on 3x the median must be visible from across the room.
    var rvol = (opts.indicators && prefs.rvol) ? rvolSeries(volRaw, 20) : null;
    var volData = [];
    for (var v = 0; v < data.length; v++) {
      if (!(volRaw[v] > 0)) continue;
      var upBar = data[v].close >= data[v].open;
      var alpha = 0.35;
      if (rvol) {
        if (rvol[v] !== null && rvol[v] >= 1.5) alpha = 0.85;
        else if (rvol[v] !== null && rvol[v] < 0.7) alpha = 0.14;
      }
      volData.push({ time: data[v].time, value: volRaw[v],
                     color: upBar ? "rgba(52,199,123," + alpha + ")" : "rgba(229,83,75," + alpha + ")" });
    }

    container.innerHTML = "";
    var chart = baseChart(container, containerId);

    var candleSeries = chart.addCandlestickSeries({
      upColor: t.up, downColor: t.down,
      borderUpColor: t.up, borderDownColor: t.down,
      wickUpColor: t.up, wickDownColor: t.down,
      priceLineVisible: true,
    });
    candleSeries.setData(data);
    // Event markers (ex-dividend, split, rights…): a gap on one of these days is
    // not a market decision, and the eye should know it before the pattern list does.
    if (Array.isArray(opts.markers) && opts.markers.length) {
      var have = {};
      data.forEach(function (d) { have[String(d.time)] = true; });
      var marks = [];
      opts.markers.forEach(function (m) {
        if (!m) return;
        var tm = normTime(m.time);
        if (tm === null) return;
        // snap to the next bar that exists (ex-dates can fall on a holiday)
        var key = String(tm), tries = 0;
        while (!have[key] && tries < 5) { var dt = new Date(key + "T00:00:00Z"); dt.setUTCDate(dt.getUTCDate() + 1); key = dt.toISOString().slice(0, 10); tries++; }
        if (!have[key]) return;
        marks.push({ time: key, position: m.position || "aboveBar", color: m.color || t.warn, shape: m.shape || "circle", text: m.text || "" });
      });
      marks.sort(function (a, b) { return String(a.time) < String(b.time) ? -1 : 1; });
      try { candleSeries.setMarkers(marks); } catch (e) { /* older lib */ }
    }

    if (volData.length) {
      var volSeries = chart.addHistogramSeries({
        priceScaleId: "vol",
        priceFormat: { type: "volume" },
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.22 } });
      volSeries.setData(volData);
    }

    var available = { chandelier: !!(opts.chandelier && opts.chandelier.since) };
    if (opts.indicators) {
      var closes = data.map(function (d) { return d.close; });
      var SMA_STYLE = { sma20: ["#7FB3FF", 20], sma50: ["#D2A44C", 50], sma200: ["#C77DFF", 200] };
      Object.keys(SMA_STYLE).forEach(function (key) {
        if (!prefs[key]) return;
        var n = SMA_STYLE[key][1];
        if (closes.length < n) { available[key] = false; return; }
        var s = smaSeries(closes, n), pts = [];
        for (var q = 0; q < s.length; q++) if (s[q] !== null) pts.push({ time: data[q].time, value: s[q] });
        var line = chart.addLineSeries({ color: SMA_STYLE[key][0], lineWidth: 1, priceLineVisible: false,
                                         lastValueVisible: true, title: "SMA" + n, crosshairMarkerVisible: false });
        line.setData(pts);
      });
      if (available.chandelier && prefs.chandelier) {
        var mult = num(opts.chandelier.atrMult) || 2.5;
        var trail = chandelierSeries(data, String(opts.chandelier.since).slice(0, 10), mult, 14);
        if (trail.length) {
          var ch = chart.addLineSeries({ color: t.warn, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed,
                                         priceLineVisible: false, lastValueVisible: true, title: "chandelier",
                                         crosshairMarkerVisible: false });
          ch.setData(trail);
        }
      }
      var legendEl = typeof opts.legendEl === "string" ? document.getElementById(opts.legendEl) : opts.legendEl;
      if (legendEl) {
        renderLegend(legendEl, prefs, available, function () { renderCandles(containerId, candles, overlays, opts); });
      }
    }

    // Overlay horizontal price lines: entry / stop / targets / fib levels
    (overlays || []).forEach(function (ov) {
      if (!ov) return;
      var price = num(ov.price);
      if (price === null) return;
      try {
        candleSeries.createPriceLine({
          price: price,
          color: ov.color || t.warn,
          lineWidth: ov.lineWidth || 1,
          lineStyle: ov.dashed === false ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: ov.title || "",
        });
      } catch (e) { /* skip malformed overlay */ }
    });

    chart.timeScale().fitContent();
    return chart;
  }

  /** Simple line series (equity curves, score history, etc.). */
  function renderLine(containerId, points, opts) {
    var container = document.getElementById(containerId);
    if (!container) return null;
    destroyExisting(containerId);
    opts = opts || {};

    if (typeof LightweightCharts === "undefined") {
      return fail(container, "Chart library failed to load (CDN unreachable).");
    }
    if (!Array.isArray(points) || !points.length) {
      return fail(container, opts.emptyMsg || "No series data.");
    }

    var t = theme();
    var data = [];
    for (var i = 0; i < points.length; i++) {
      var p = points[i] || {};
      var time = normTime(p.time !== undefined ? p.time : (p.date !== undefined ? p.date : i + 1));
      var value = num(p.value !== undefined ? p.value : (p.equity !== undefined ? p.equity : p.close));
      if (time === null || value === null) continue;
      data.push({ time: time, value: value });
    }
    if (!data.length) return fail(container, "Series data came back in an unreadable format.");

    container.innerHTML = "";
    var chart = baseChart(container, containerId);
    var series = chart.addLineSeries({
      color: opts.color || t.accent,
      lineWidth: 2,
      priceLineVisible: false,
    });
    series.setData(data);
    if (opts.baseline !== undefined && opts.baseline !== null) {
      try {
        series.createPriceLine({
          price: opts.baseline, color: t.muted, lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true, title: opts.baselineTitle || "start",
        });
      } catch (e) { /* noop */ }
    }
    chart.timeScale().fitContent();
    return chart;
  }

  window.Charts = {
    renderCandles: renderCandles, renderLine: renderLine,
    // pure helpers, exposed for tests (tests/js/chart_indicators.test.js)
    indicators: { sma: smaSeries, atr: atrSeries, rvol: rvolSeries, chandelier: chandelierSeries,
                  defaults: INDICATOR_DEFAULTS, storageKey: INDICATOR_KEY },
  };
  // Contract-named global for other modules:
  window.renderCandles = renderCandles;
})();
