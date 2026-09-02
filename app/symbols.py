"""Symbol utilities: TradingView<->Yahoo mapping and EGX universes.

Universe membership comes from the locally installed tradingview_mcp package:
`core.data.egx_indices` (index constituent lists) and
`core.services.coinlist.load_symbols("egx")` (full EGX listing, entries like
"EGX:COMI").
"""
from __future__ import annotations

from functools import lru_cache

from tradingview_mcp.core.data.egx_indices import (
    EGX30_CONSTITUENTS,
    EGX35LV_CONSTITUENTS,
    EGX70_CONSTITUENTS,
    SHARIAH33_CONSTITUENTS,
    TAMAYUZ_CONSTITUENTS,
)
from tradingview_mcp.core.services.coinlist import load_symbols


def _clean(symbol: str) -> str:
    """Uppercase and strip any 'EGX:' exchange prefix."""
    return symbol.strip().upper().removeprefix("EGX:")


def tv_to_yahoo(symbol: str) -> str:
    """Map a TradingView EGX symbol to its Yahoo Finance ticker.

    "COMI" or "EGX:COMI" -> "COMI.CA". Symbols already carrying a Yahoo
    suffix are returned unchanged.
    """
    clean = _clean(symbol)
    if "." in clean:
        return clean
    return f"{clean}.CA"


@lru_cache(maxsize=1)
def _all_symbols() -> tuple[str, ...]:
    """Full EGX symbol list (bare tickers, no prefix), from coinlist."""
    try:
        return tuple(_clean(s) for s in load_symbols("egx") if s.strip())
    except Exception:
        # Degrade to index constituents if the coinlist file is unavailable.
        return tuple(dict.fromkeys(EGX30_CONSTITUENTS + EGX70_CONSTITUENTS))


_UNIVERSES: dict[str, list[str]] = {
    "EGX30": list(EGX30_CONSTITUENTS),
    "EGX70": list(EGX70_CONSTITUENTS),
    "EGX100": list(dict.fromkeys(EGX30_CONSTITUENTS + EGX70_CONSTITUENTS)),
    "SHARIAH33": list(SHARIAH33_CONSTITUENTS),
    "EGX35LV": list(EGX35LV_CONSTITUENTS),
    "TAMAYUZ": list(TAMAYUZ_CONSTITUENTS),
}


def universes() -> list[str]:
    """Names of the available symbol universes."""
    return [*_UNIVERSES.keys(), "ALL"]


def universe(name: str) -> list[str]:
    """Return the symbols of a named universe (bare tickers, no prefix).

    Accepts "EGX30", "EGX70", "EGX100", "SHARIAH33", "EGX35LV", "TAMAYUZ",
    or "ALL" (full EGX listing). Unknown names fall back to EGX30.
    """
    key = (name or "").strip().upper().replace("-", "").replace("_", "")
    if key == "ALL":
        return list(_all_symbols())
    if key == "EGX35LV" or key == "EGX35":
        return list(_UNIVERSES["EGX35LV"])
    return list(_UNIVERSES.get(key, _UNIVERSES["EGX30"]))


def is_valid_symbol(symbol: str) -> bool:
    """True if `symbol` is a listed EGX ticker (per coinlist egx list)."""
    return _clean(symbol) in set(_all_symbols())
