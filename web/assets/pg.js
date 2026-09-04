/* ============================================================
   EGX Decision Engine — shared "PG" page framework.

   Defensive wrappers over assets/ui.js + assets/api.js used by the
   screener, backtest and portfolio pages. This file replaces three
   byte-identical ~275-line inline copies that had to be fixed in
   parallel; behaviour is unchanged except for the noted hardening:
     - numeric cells are right-aligned (class on <td> AND <th>),
     - no innerHTML anywhere (the old pctNode fallback injected strings),
     - sortable headers are focusable and expose aria-sort.
   Requires api.js and ui.js to be loaded first.
   ============================================================ */
'use strict';
window.PG = (function () {
  function mk(tag, attrs, children) {
    attrs = attrs || {}; children = children || [];
    if (!Array.isArray(children)) children = [children];
    var handlers = {}, plain = {}, k;
    for (k in attrs) {
      if (typeof attrs[k] === 'function' && k.indexOf('on') === 0) handlers[k.slice(2).toLowerCase()] = attrs[k];
      else if (k !== 'html') plain[k] = attrs[k];   // never expose an innerHTML path
    }
    var node = null;
    try { if (typeof window.el === 'function') node = window.el(tag, plain, children); } catch (e) { node = null; }
    if (!(node && node.nodeType === 1)) {
      node = document.createElement(tag);
      for (k in plain) {
        if (k === 'class' || k === 'className') node.className = plain[k];
        else node.setAttribute(k, plain[k]);   // no `html`/innerHTML path
      }
      for (var i = 0; i < children.length; i++) {
        var c = children[i];
        if (c === null || c === undefined) continue;
        node.appendChild(c && c.nodeType ? c : document.createTextNode(String(c)));
      }
    }
    for (k in handlers) node.addEventListener(k, handlers[k]);
    return node;
  }

  function num(v, d) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    if (!isFinite(n)) return typeof v === 'string' ? v : '—';
    try {
      if (typeof window.fmtNum === 'function') {
        var r = window.fmtNum(v, d);
        if (r !== undefined && r !== null && typeof r !== 'object') return String(r);
      }
    } catch (e) {}
    return n.toLocaleString('en-US', { maximumFractionDigits: d === undefined ? 2 : d });
  }

  function pctNode(v) {
    var span, n = Number(v);
    try {
      if (typeof window.fmtPct === 'function') {
        var r = window.fmtPct(v);
        if (r && r.nodeType) return r;
        if (r !== undefined && r !== null) {
          span = document.createElement('span');
          span.textContent = String(r);   // was innerHTML
          return span;
        }
      }
    } catch (e) {}
    span = document.createElement('span');
    if (!isFinite(n)) { span.textContent = '—'; return span; }
    span.className = n > 0 ? 'up' : (n < 0 ? 'down' : 'pg-muted');
    span.textContent = (n > 0 ? '+' : '') + n.toFixed(2) + '%';
    return span;
  }

  function signedNode(v, suffix) {
    var span = document.createElement('span'), n = Number(v);
    if (v === null || v === undefined || !isFinite(n)) { span.textContent = '—'; return span; }
    span.className = n > 0 ? 'up' : (n < 0 ? 'down' : '');
    span.textContent = (n > 0 ? '+' : '') + num(n) + (suffix || '');
    return span;
  }

  function notify(msg, kind) {
    try { if (typeof window.toast === 'function') { window.toast(msg, kind); return; } } catch (e) {}
    try { console.log('[' + (kind || 'info') + '] ' + msg); } catch (e2) {}
  }

  function api(method, path, body) {
    if (!window.API || typeof window.API[method] !== 'function') {
      return Promise.reject(new Error('API helper (assets/api.js) not loaded'));
    }
    return (method === 'post') ? window.API.post(path, body) : window.API[method](path);
  }

  // Keys that must NEVER be treated as numeric columns even when their values
  // are numbers: dates/timestamps ("closed_at" would otherwise match "close"),
  // and 0/1 flags that render as badges (enabled, delivered, plan_followed).
  function isNonNumericKey(key) {
    return /(_at$|_date$|^date$|^time$|_time$|enabled|delivered|plan_followed|status|note)/i.test(key || '');
  }

  function isNumericKey(key) {
    if (isNonNumericKey(key)) return false;
    return /(_pct$|_percent$|^change(_pct)?$|percent_change|price|close|last|entry|stop|target|qty|volume|score|rsi|bbw|pnl|capital|value|ratio|count|risk)/i.test(key || '');
  }

  function cellNode(key, v) {
    if (v === null || v === undefined || v === '') return document.createTextNode('—');
    if (typeof v === 'object') {
      var t = document.createElement('span'), j = '';
      try { j = JSON.stringify(v); } catch (e) { j = String(v); }
      t.title = j;
      t.textContent = Array.isArray(v) ? v.length + ' item' + (v.length === 1 ? '' : 's') : (j.length > 60 ? j.slice(0, 57) + '…' : j);
      t.className = 'pg-muted';
      return t;
    }
    if (typeof v === 'number') {
      if (/(_pct$|_percent$|^change(_pct)?$|percent_change)/i.test(key)) return pctNode(v);
      return document.createTextNode(num(v));
    }
    if (typeof v === 'boolean') return document.createTextNode(v ? 'yes' : 'no');
    return document.createTextNode(String(v));
  }

  var PRIORITY = ['symbol','ticker','name','strategy','price','close','last','entry','stop','target1','target2','exit_price','qty','change_pct','change','signal','score','rating','hit_count','family_count','volume','rsi','bbw','pnl','pnl_pct','r_multiple'];

  function table(rows, opts) {
    opts = opts || {};
    rows = (rows || []).map(function (r) { return (r !== null && typeof r === 'object') ? r : { value: r }; });
    var exclude = opts.exclude || [], cols = opts.columns;
    if (!cols) {
      var keys = [];
      rows.forEach(function (r) { Object.keys(r).forEach(function (k) { if (keys.indexOf(k) === -1 && exclude.indexOf(k) === -1) keys.push(k); }); });
      keys.sort(function (a, b) {
        var ia = PRIORITY.indexOf(a), ib = PRIORITY.indexOf(b);
        ia = ia === -1 ? 999 : ia; ib = ib === -1 ? 999 : ib;
        return (ia - ib) || a.localeCompare(b);
      });
      var cap = opts.maxCols || 12;
      if (keys.length > cap) keys = keys.slice(0, cap);
      cols = keys.map(function (k) { return { key: k, label: k.replace(/_/g, ' ') }; });
    } else { cols = cols.slice(); }
    if (opts.renderers) cols.forEach(function (c) {
      if (!c.render && opts.renderers[c.key]) {
        c.render = (function (fn, key) { return function (row) { return fn(row[key], row); }; })(opts.renderers[c.key], c.key);
      }
    });
    if (opts.trailing) cols = cols.concat(opts.trailing);

    // A column counts as numeric when its name looks numeric or the first
    // non-empty value is a number — used to right-align header AND cells.
    cols.forEach(function (c) {
      if (c.numeric !== undefined || !c.key) return;
      if (isNonNumericKey(c.key)) { c.numeric = false; return; }
      var numeric = isNumericKey(c.key);
      if (!numeric) {
        for (var i = 0; i < rows.length; i++) {
          var v = rows[i][c.key];
          if (v === null || v === undefined || v === '') continue;
          numeric = typeof v === 'number';
          break;
        }
      }
      c.numeric = numeric;
    });

    var sortKey = null, sortDir = 1;
    var tbl = mk('table', { class: 'pg-table' });
    var thead = mk('thead'), trh = mk('tr');
    cols.forEach(function (c) {
      var th = mk('th', {}, [c.label === undefined ? (c.key || '') : c.label]);
      if (c.numeric) th.className = 'pg-num';
      if (c.key) {
        th.setAttribute('tabindex', '0');
        th.setAttribute('role', 'columnheader');
        th.setAttribute('aria-sort', 'none');
        var doSort = function () {
          if (sortKey === c.key) sortDir = -sortDir; else { sortKey = c.key; sortDir = 1; }
          drawBody();
          var ths = trh.querySelectorAll('th');
          for (var i = 0; i < ths.length; i++) {
            ths[i].removeAttribute('data-sort');
            if (ths[i].hasAttribute('aria-sort')) ths[i].setAttribute('aria-sort', 'none');
          }
          th.setAttribute('data-sort', sortDir === 1 ? 'asc' : 'desc');
          th.setAttribute('aria-sort', sortDir === 1 ? 'ascending' : 'descending');
        };
        th.addEventListener('click', doSort);
        th.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); doSort(); }
        });
      }
      trh.appendChild(th);
    });
    thead.appendChild(trh); tbl.appendChild(thead);
    var tbody = mk('tbody'); tbl.appendChild(tbody);

    function drawBody() {
      var data = rows.slice();
      if (sortKey) data.sort(function (a, b) {
        var av = a[sortKey], bv = b[sortKey];
        if (av === bv) return 0;
        if (av === null || av === undefined || av === '') return 1;
        if (bv === null || bv === undefined || bv === '') return -1;
        var an = Number(av), bn = Number(bv);
        if (isFinite(an) && isFinite(bn)) return (an - bn) * sortDir;
        return String(av).localeCompare(String(bv)) * sortDir;
      });
      tbody.textContent = '';
      if (!data.length) {
        var tdE = mk('td', { class: 'pg-empty' }, ['No rows']);
        tdE.colSpan = cols.length;
        tbody.appendChild(mk('tr', {}, [tdE]));
        return;
      }
      data.forEach(function (r) {
        var tr = mk('tr');
        cols.forEach(function (c) {
          var td = mk('td'), custom = null;
          if (c.render) { try { custom = c.render(r); } catch (e) { custom = null; } }
          td.appendChild(custom && custom.nodeType ? custom : cellNode(c.key || '', c.key ? r[c.key] : null));
          // Alignment follows the COLUMN decision, not the cell value —
          // otherwise a 0/1 flag cell (enabled/delivered) right-aligns while
          // its header stays left, and dates jump around per row.
          if (c.numeric) td.className = 'pg-num';
          tr.appendChild(td);
        });
        if (opts.onRow) {
          tr.style.cursor = 'pointer';
          tr.addEventListener('click', function (ev) {
            var t = ev.target;
            while (t && t !== tr) { if (/^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(t.tagName || '')) return; t = t.parentNode; }
            opts.onRow(r);
          });
        }
        tbody.appendChild(tr);
      });
    }
    drawBody();
    return mk('div', { class: 'pg-tablewrap' }, [tbl]);
  }

  function extractRows(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && typeof payload === 'object') {
      var pref = ['results','candidates','rows','stocks','matches','hits','data','items','positions','rules','alerts','trades'];
      for (var i = 0; i < pref.length; i++) if (Array.isArray(payload[pref[i]])) return payload[pref[i]];
      var ks = Object.keys(payload);
      for (var j = 0; j < ks.length; j++) {
        var v = payload[ks[j]];
        if (Array.isArray(v) && v.length && v[0] !== null && typeof v[0] === 'object') return v;
      }
    }
    return [];
  }

  function findVal(obj, names) {
    if (!obj || typeof obj !== 'object') return undefined;
    var i, k;
    for (i = 0; i < names.length; i++) if (obj[names[i]] !== undefined && obj[names[i]] !== null) return obj[names[i]];
    for (k in obj) {
      var v = obj[k];
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        for (i = 0; i < names.length; i++) if (v[names[i]] !== undefined && v[names[i]] !== null) return v[names[i]];
      }
    }
    return undefined;
  }

  function renderAny(data, depth) {
    depth = depth || 0;
    if (data === null || data === undefined) return mk('span', { class: 'pg-muted' }, ['—']);
    if (Array.isArray(data)) {
      if (!data.length) return mk('span', { class: 'pg-muted' }, ['empty list']);
      if (data[0] !== null && typeof data[0] === 'object') return table(data, { maxCols: 10 });
      return mk('div', { class: 'pg-num' }, [data.map(String).join(', ')]);
    }
    if (typeof data === 'object') {
      var grid = mk('div', { class: 'pg-kv' });
      Object.keys(data).forEach(function (k) {
        grid.appendChild(mk('div', { class: 'pg-kv-k' }, [k.replace(/_/g, ' ')]));
        var vd = mk('div', { class: 'pg-kv-v pg-num' }), v = data[k];
        if (v !== null && typeof v === 'object' && depth < 2) vd.appendChild(renderAny(v, depth + 1));
        else vd.appendChild(cellNode(k, v));
        grid.appendChild(vd);
      });
      return grid;
    }
    return document.createTextNode(String(data));
  }

  function slim(data, maxItems) {
    maxItems = maxItems || 15;
    if (Array.isArray(data)) return data.length > maxItems ? '[' + data.length + ' items]' : data.map(function (x) { return slim(x, maxItems); });
    if (data && typeof data === 'object') {
      var out = {};
      Object.keys(data).forEach(function (k) { out[k] = slim(data[k], maxItems); });
      return out;
    }
    return data;
  }

  function loading(target, label) { target.textContent = ''; target.appendChild(mk('div', { class: 'pg-loading' }, [label || 'Loading…'])); }
  function errBox(target, msg) {
    var s = String(msg || 'Request failed');
    var friendly = s;
    if (/Upstream TradingView|transient errors|empty-body outage|scanner\.tradingview/i.test(s)) {
      friendly = 'TradingView is pausing this app for a minute or two (rate limit). Try again shortly — stored results and Yahoo-based tabs (Leaders, Patterns) still work.';
    } else if (/rate limit|429|backing off/i.test(s)) {
      friendly = 'Yahoo is rate-limiting requests for a short while. Try again in a minute.';
    } else if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(s)) {
      friendly = "The app's server is not responding. Is it running?";
    }
    target.textContent = '';
    var box = mk('div', { class: 'pg-error' }, [friendly]);
    if (friendly !== s) box.title = s;
    target.appendChild(box);
  }

  function metricCard(label, valueNode) {
    var v = mk('div', { class: 'pg-card-value' });
    v.appendChild(valueNode && valueNode.nodeType ? valueNode : document.createTextNode(String(valueNode === undefined || valueNode === null ? '—' : valueNode)));
    return mk('div', { class: 'pg-card' }, [mk('div', { class: 'pg-card-label' }, [label]), v]);
  }

  function detailsBlock(title, data) {
    var d = mk('details', { class: 'pg-details' }, [mk('summary', {}, [title])]);
    d.appendChild(renderAny(slim(data), 0));
    return d;
  }

  function openStock(row) {
    var s = row && (row.symbol || row.ticker || row.name);
    if (!s || typeof s !== 'string') return;
    window.location.href = '/stock.html?symbol=' + encodeURIComponent(s.replace(/^EGX:/i, '').trim().toUpperCase());
  }

  function collectSymbols(o) {
    var acc = [];
    (function walk(x, depth) {
      if (!x || depth > 5) return;
      if (Array.isArray(x)) { for (var i = 0; i < x.length; i++) walk(x[i], depth + 1); return; }
      if (typeof x === 'object') {
        if (typeof x.symbol === 'string') {
          var s = x.symbol.replace(/^EGX:/i, '').toUpperCase();
          if (s && acc.indexOf(s) === -1) acc.push(s);
        }
        for (var k in x) walk(x[k], depth + 1);
      }
    })(o, 0);
    return acc;
  }

  function fallbackSidebar(active) {
    var sb = document.getElementById('sidebar');
    if (!sb || sb.childElementCount) return;
    var nav = mk('nav', { class: 'pg-fallback-nav' }, [mk('div', { class: 'pg-brand' }, ['EGX Engine'])]);
    [['Dashboard','/index.html','dashboard'],['Screener','/screener.html','screener'],['Backtest','/backtest.html','backtest'],['Portfolio','/portfolio.html','portfolio']].forEach(function (l) {
      nav.appendChild(mk('a', { href: l[1], class: l[2] === active ? 'active' : '' }, [l[0]]));
    });
    sb.appendChild(nav);
  }

  function boot(active) {
    var ok = false;
    try { if (typeof window.renderSidebar === 'function') { window.renderSidebar(active); ok = true; } } catch (e) { ok = false; }
    if (!ok) fallbackSidebar(active);
    try { if (typeof window.renderTopbar === 'function') window.renderTopbar(); } catch (e2) {}
    try { if (typeof window.renderMobileNav === 'function') window.renderMobileNav(active); } catch (e3) {}
  }

  return { mk: mk, num: num, pctNode: pctNode, signedNode: signedNode, notify: notify, api: api, cellNode: cellNode,
           table: table, extractRows: extractRows, findVal: findVal, renderAny: renderAny, slim: slim, loading: loading,
           errBox: errBox, metricCard: metricCard, detailsBlock: detailsBlock, openStock: openStock,
           collectSymbols: collectSymbols, boot: boot };
})();
