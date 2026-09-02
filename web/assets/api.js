/* ============================================================
   EGX Decision Engine — API helper (Module F)
   window.API = { get(path), post(path, body), del(path) }
   - Returns parsed JSON.
   - Throws Error(message) on network failure, non-2xx status,
     or a payload that is an object carrying an "error" key
     (core-library convention).
   ============================================================ */
(function () {
  "use strict";

  async function request(method, path, body) {
    var opts = {
      method: method,
      headers: { "Accept": "application/json" },
    };
    if (body !== undefined && body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }

    var res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      throw new Error("Network error: " + (e && e.message ? e.message : "request failed"));
    }

    var text = "";
    try { text = await res.text(); } catch (e) { text = ""; }

    var data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        if (!res.ok) throw new Error("HTTP " + res.status + " " + res.statusText);
        throw new Error("Bad JSON from " + path);
      }
    }

    if (!res.ok) {
      var msg = null;
      if (data && typeof data === "object") {
        msg = data.error || data.detail || data.message;
        if (msg && typeof msg !== "string") { try { msg = JSON.stringify(msg); } catch (e) { msg = null; } }
      }
      throw new Error(msg || ("HTTP " + res.status + " " + res.statusText));
    }

    // Core-library error convention: 200 with {"error": "..."}
    if (data && typeof data === "object" && !Array.isArray(data) &&
        data.error !== undefined && data.error !== null && data.error !== "") {
      var emsg = typeof data.error === "string" ? data.error : JSON.stringify(data.error);
      throw new Error(emsg);
    }

    _lastDataAt = Date.now();
    return data;
  }

  // Timestamp of the last successful API response — the topbar's data-age
  // chip reads this so every page shows how old its numbers are.
  var _lastDataAt = null;

  window.API = {
    get: function (path) { return request("GET", path); },
    post: function (path, body) { return request("POST", path, body); },
    del: function (path) { return request("DELETE", path); },
    lastDataAt: function () { return _lastDataAt; },
  };
})();
