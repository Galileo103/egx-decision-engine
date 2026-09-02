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

  /**
   * Candlestick + volume histogram with optional horizontal price lines
   * (entry / stop / targets / fib levels).
   */
  function renderCandles(containerId, candles, overlays) {
    var container = document.getElementById(containerId);
    if (!container) return null;
    destroyExisting(containerId);

    if (typeof LightweightCharts === "undefined") {
      return fail(container, "Chart library failed to load (CDN unreachable).");
    }
    if (!Array.isArray(candles) || !candles.length) {
      return fail(container, "No price history available for this symbol.");
    }

    var t = theme();
    var data = [];
    var volData = [];
    for (var i = 0; i < candles.length; i++) {
      var c = candles[i] || {};
      var time = normTime(c.time !== undefined ? c.time : (c.date !== undefined ? c.date : c.timestamp));
      var o = num(c.open), h = num(c.high), l = num(c.low), cl = num(c.close);
      if (time === null || o === null || h === null || l === null || cl === null) continue;
      data.push({ time: time, open: o, high: h, low: l, close: cl });
      var vol = num(c.volume);
      if (vol !== null) {
        volData.push({
          time: time, value: vol,
          color: cl >= o ? "rgba(52,199,123,0.35)" : "rgba(229,83,75,0.35)",
        });
      }
    }
    if (!data.length) return fail(container, "Price history came back in an unreadable format.");

    container.innerHTML = "";
    var chart = baseChart(container, containerId);

    var candleSeries = chart.addCandlestickSeries({
      upColor: t.up, downColor: t.down,
      borderUpColor: t.up, borderDownColor: t.down,
      wickUpColor: t.up, wickDownColor: t.down,
      priceLineVisible: true,
    });
    candleSeries.setData(data);

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

  window.Charts = { renderCandles: renderCandles, renderLine: renderLine };
  // Contract-named global for other modules:
  window.renderCandles = renderCandles;
})();
