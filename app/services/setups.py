"""Best setups today — the six-pillar checklist run across every stock the app
already has a reason to look at: the latest Candidates, the Leaders ranking,
the watchlist and the open positions. Results are stored per session so the
dashboard answers "which stocks are setups right now" instantly.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

_VERDICT_RANK = {"setup": 0, "watch": 1, "no_setup": 2}
_FETCH_PAUSE = 0.05


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def candidate_symbols(limit_candidates: int = 40, limit_leaders: int = 25) -> dict[str, list[str]]:
    """Symbol -> the reasons it is on the list (candidates / leaders / watchlist / held)."""
    out: dict[str, list[str]] = {}

    def add(sym: Any, tag: str) -> None:
        s = str(sym or "").upper().strip().split(":")[-1]
        if s:
            out.setdefault(s, [])
            if tag not in out[s]:
                out[s].append(tag)

    try:
        from app.services import screeners

        for c in (screeners.latest_candidates(limit_candidates).get("candidates") or []):
            add(c.get("symbol"), "candidates")
    except Exception as exc:  # noqa: BLE001
        logger.warning("setups: candidates unavailable: %s", exc)
    try:
        from app.services import leaders

        for r in (leaders.latest("EGX100", limit_leaders).get("rows") or []):
            add(r.get("symbol"), "leaders")
    except Exception as exc:  # noqa: BLE001
        logger.warning("setups: leaders unavailable: %s", exc)
    try:
        for w in db.query("SELECT symbol FROM watchlist"):
            add(w.get("symbol"), "watchlist")
    except Exception as exc:  # noqa: BLE001
        logger.warning("setups: watchlist unavailable: %s", exc)
    try:
        for p in db.query("SELECT DISTINCT symbol FROM positions WHERE status = 'open'"):
            add(p.get("symbol"), "held")
    except Exception as exc:  # noqa: BLE001
        logger.warning("setups: positions unavailable: %s", exc)
    return out


def compute(persist: bool = True, limit: int = 80, symbols: Optional[list[str]] = None) -> dict:
    """Run the checklist across the candidate set. Never raises."""
    try:
        from app.services import checklist

        started = time.monotonic()
        sources = candidate_symbols()
        if symbols:
            for s in symbols:
                sources.setdefault(str(s).upper(), []).append("manual")
        syms = list(sources)[: max(1, int(limit))]
        rows: list[dict] = []
        errors = 0
        for sym in syms:
            ck = checklist.checklist(sym)
            if not isinstance(ck, dict) or "error" in ck:
                errors += 1
                continue
            rows.append({
                "symbol": sym, "score": ck["score"], "verdict": ck["verdict"], "headline": ck["headline"],
                "missing": ck.get("missing") or [], "price": ck.get("price"),
                "pillars": {p["key"]: p["status"] for p in ck.get("pillars") or []},
                "pillar_text": {p["key"]: p["text"] for p in ck.get("pillars") or []},
                "risk_plan": ck.get("risk_plan"), "levels_position": ck.get("levels_position"),
                "sources": sources.get(sym, []), "as_of": ck.get("as_of"),
                "rvol": ck.get("rvol"), "market": (ck.get("market") or {}).get("state"),
            })
            time.sleep(_FETCH_PAUSE)
        rows.sort(key=lambda r: (_VERDICT_RANK.get(r["verdict"], 9), -r["score"], r["symbol"]))
        date = datetime.now(CAIRO).strftime("%Y-%m-%d")
        if persist and rows:
            _persist(date, rows)
        counts = {"setup": 0, "watch": 0, "no_setup": 0}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        return {
            "rows": rows, "date": date, "as_of": _now_iso(), "scanned": len(syms), "errors": errors,
            "counts": counts, "elapsed_s": round(time.monotonic() - started, 1),
            "basis": ("Six-pillar checklist (trend, support/resistance, volume, price action, patterns, risk "
                      "plan) on Yahoo daily closes, run over the latest Candidates, the Leaders ranking, your "
                      "watchlist and your open positions. SETUP = 5-6 pillars and nothing against it."),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("setups.compute failed")
        return {"error": str(exc)}


def _persist(date: str, rows: list[dict]) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO setups (date, symbol, score, verdict, headline, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(date, r["symbol"], r["score"], r["verdict"], r["headline"], json.dumps(r), _now_iso()) for r in rows],
    )
    # Journal each verdict for the Scorecard (checklist_setup / _watch / _no_setup)
    # so the live record of "what did a SETUP do next" grows alongside the replay.
    # Excluded from Candidates by name; graded like any bullish signal.
    session = str((rows[0].get("as_of") if rows else None) or date)[:10]
    db.executemany(
        "INSERT OR IGNORE INTO scanner_hits (date, scanner, symbol, payload_json, created_at, source) "
        "VALUES (?, ?, ?, ?, ?, 'live')",
        [(session, f"checklist_{r['verdict']}", r["symbol"],
          json.dumps({"verdict": r["verdict"], "score": r["score"], "missing": r.get("missing"),
                      "direction": "bullish"}), _now_iso()) for r in rows if r.get("verdict")],
    )


def latest(limit: int = 80, min_score: int = 0) -> dict:
    """Most recently stored run (fast path for the dashboard)."""
    try:
        d = db.query("SELECT MAX(date) AS d FROM setups")
        date = d[0].get("d") if d else None
        if not date:
            return {"rows": [], "date": None, "stored": False, "counts": {}}
        rows = []
        for r in db.query("SELECT payload_json FROM setups WHERE date = ? AND score >= ?", (date, int(min_score))):
            try:
                rows.append(json.loads(r["payload_json"]))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda r: (_VERDICT_RANK.get(r.get("verdict"), 9), -int(r.get("score") or 0), r.get("symbol") or ""))
        counts: dict[str, int] = {}
        for r in rows:
            counts[r.get("verdict") or "?"] = counts.get(r.get("verdict") or "?", 0) + 1
        return {"rows": rows[: max(1, int(limit))], "date": date, "stored": True, "counts": counts, "total": len(rows)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
