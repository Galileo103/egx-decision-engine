"""Symbol catalog — the searchable list of every EGX ticker with its company name.

Backs the top-bar autocomplete. Reads a bundled JSON snapshot of company names
(``app/data/egx_names.json``) so the endpoint answers instantly and offline, and
merges in index membership from :mod:`app.symbols`.

``refresh()`` re-queries TradingView and rewrites the JSON; it is the only
function here that touches the network.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import symbols as sym_mod

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "egx_names.json"

_lock = threading.Lock()
_cache: Optional[List[Dict[str, Any]]] = None

# Index membership is shown as a badge in the autocomplete; order matters
# (most significant index wins when a symbol belongs to several).
_INDEX_ORDER = ("EGX30", "EGX70", "SHARIAH33", "EGX35LV", "TAMAYUZ")


def _load_names() -> Dict[str, Dict[str, Any]]:
    """Read the bundled company-name map. Returns {} when it is missing/corrupt."""
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _index_map() -> Dict[str, str]:
    """Map each symbol to the most significant index it belongs to."""
    out: Dict[str, str] = {}
    for name in _INDEX_ORDER:
        try:
            members = sym_mod.universe(name)
        except Exception:
            continue
        for raw in members or []:
            bare = str(raw).split(":")[-1].strip().upper()
            if bare and bare not in out:
                out[bare] = name
    return out


def _build() -> List[Dict[str, Any]]:
    names = _load_names()
    indices = _index_map()

    tickers = set(names)
    try:
        for raw in sym_mod.universe("ALL") or []:
            bare = str(raw).split(":")[-1].strip().upper()
            if bare:
                tickers.add(bare)
    except Exception:
        pass
    tickers.update(indices)

    rows: List[Dict[str, Any]] = []
    for ticker in tickers:
        meta = names.get(ticker) or {}
        rows.append(
            {
                "symbol": ticker,
                "name": meta.get("name") or "",
                "sector": meta.get("sector") or "",
                "index": indices.get(ticker, ""),
                "mcap": meta.get("mcap"),
            }
        )

    # Rank: index members first (EGX30 before EGX70...), then by market cap,
    # then alphabetically — so the most tradable names surface first.
    def sort_key(row: Dict[str, Any]):
        idx = row["index"]
        rank = _INDEX_ORDER.index(idx) if idx in _INDEX_ORDER else len(_INDEX_ORDER)
        mcap = row.get("mcap")
        return (rank, -(mcap or 0.0), row["symbol"])

    rows.sort(key=sort_key)
    return rows


def list_symbols(force: bool = False) -> Dict[str, Any]:
    """Return the full searchable catalog.

    Args:
        force: rebuild even when a cached copy exists.

    Returns:
        ``{"symbols": [{symbol, name, sector, index, mcap}, ...], "count": n,
        "named": n_with_names}``
    """
    global _cache
    try:
        with _lock:
            if _cache is None or force:
                _cache = _build()
            rows = _cache
        return {
            "symbols": rows,
            "count": len(rows),
            "named": sum(1 for r in rows if r["name"]),
            "source": str(_DATA_FILE.name),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": str(exc), "symbols": [], "count": 0}


def refresh() -> Dict[str, Any]:
    """Re-fetch company names from TradingView and rewrite the bundled JSON.

    Network call. Falls back to the existing file untouched on any failure.
    """
    try:
        from tradingview_screener import Query

        _, df = (
            Query()
            .select("name", "description", "sector", "market_cap_basic")
            .set_markets("egypt")
            .limit(600)
            .get_scanner_data()
        )
        out: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).split(":")[-1].strip().upper()
            if not ticker:
                continue
            mcap = row.get("market_cap_basic")
            try:
                mcap = float(mcap) if mcap is not None and mcap == mcap else None
            except Exception:
                mcap = None
            out[ticker] = {
                "name": str(row.get("description") or row.get("name") or "").strip(),
                "sector": str(row.get("sector") or "").strip(),
                "mcap": mcap,
            }
        if not out:
            return {"error": "TradingView returned no EGX rows; kept existing catalog."}

        _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DATA_FILE.write_text(
            json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8"
        )
        result = list_symbols(force=True)
        return {"refreshed": len(out), "count": result.get("count", 0)}
    except Exception as exc:
        return {"error": str(exc)}
