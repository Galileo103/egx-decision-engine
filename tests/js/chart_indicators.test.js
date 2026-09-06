/* Pure-math checks for web/assets/charts.js indicator helpers (TA roadmap Task 5).
   Run with:  node tests/js/chart_indicators.test.js
   No browser: LightweightCharts, window and document are stubbed just enough
   for the module to load; only the exported `Charts.indicators` helpers run. */
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.window = {};
global.document = { documentElement: {}, getElementById: () => null, createElement: () => ({}) };
global.getComputedStyle = () => ({ getPropertyValue: () => "" });
global.localStorage = { getItem: () => null, setItem: () => {} };
global.LightweightCharts = { LineStyle: { Solid: 0, Dashed: 2 }, CrosshairMode: { Normal: 0 } };
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(__dirname, "..", "..", "web", "assets", "charts.js"), "utf8"));
const I = global.window.Charts.indicators;

function bars(closes, spread, vols) {
  return closes.map((c, i) => ({ time: "2026-01-" + String(i + 1).padStart(2, "0"), open: c, high: c + spread / 2, low: c - spread / 2, close: c, volume: vols ? vols[i] : 1000 }));
}

// SMA: null until n bars, then the mean of the last n closes
const sma = I.sma([1, 2, 3, 4, 5, 6], 3);
assert.deepStrictEqual(sma, [null, null, 2, 3, 4, 5]);

// ATR: constant range -> ATR equals the range (matches guardian._atr, a simple mean)
const b = bars(Array(30).fill(100), 2);
const atr = I.atr(b, 14);
assert.strictEqual(atr[0], null);
assert.ok(Math.abs(atr[29] - 2) < 1e-9, "flat range gives ATR = range");
assert.strictEqual(atr[6], 2, "ATR appears once period/2 true ranges exist");

// RVOL: volume / median of previous 20 (needs 10 prior); a block trade barely moves the median
const vols = Array(20).fill(100).concat([300]);
const rv = I.rvol(vols, 20);
assert.strictEqual(rv[20], 3);
assert.strictEqual(rv[5], null);
const vols2 = Array(10).fill(100).concat([2000], Array(9).fill(100), [300]);
assert.strictEqual(I.rvol(vols2, 20)[20], 3);

// Chandelier: highest close since entry - mult x ATR, never lowered
const closes = Array(20).fill(100).concat([104, 108, 110, 106, 102]);
const cb = bars(closes, 2);
const trail = I.chandelier(cb, cb[20].time, 2.5, 14);
assert.strictEqual(trail.length, 5);
assert.strictEqual(trail[0].time, cb[20].time);
// bar 22 (close 110): hi 110, ATR ~ (mean TR) -> trail = 110 - 2.5*ATR; later bars must not lower it
for (let i = 1; i < trail.length; i++) assert.ok(trail[i].value >= trail[i - 1].value - 1e-9, "trail never lowered");
assert.ok(trail[2].value > trail[0].value, "trail rises with new highs");
// before the entry date nothing is drawn
assert.strictEqual(I.chandelier(cb, "2099-01-01", 2.5, 14).length, 0);

// defaults + storage key are exposed for the legend
assert.deepStrictEqual(Object.keys(I.defaults).sort(), ["chandelier", "rvol", "sma20", "sma200", "sma50"]);
assert.strictEqual(typeof I.storageKey, "string");

console.log("chart_indicators: all checks passed");
