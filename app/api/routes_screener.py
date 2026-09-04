"""Screener routes: scanner registry, single-scanner runs, merged candidates."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.services import leaders, patterns, scorecard, screeners

router = APIRouter(prefix="/api/screener", tags=["screener"])


def _coerce(value: str) -> Any:
    """Coerce a query-string value to int/float/bool where it obviously is one."""
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


@router.get("/list")
async def screener_list() -> dict[str, Any]:
    """Scanner registry: key -> {label, description, params}."""
    try:
        return screeners.SCANNERS
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/run/{key}")
async def screener_run(key: str, request: Request) -> dict[str, Any]:
    """Run one scanner; all query params are passed through as its params dict."""
    try:
        params = {k: _coerce(v) for k, v in request.query_params.items()}
        return await asyncio.to_thread(screeners.run_scanner, key, params)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/candidates")
async def screener_candidates(
    timeframe: str = Query("1D"),
    persist: bool = Query(False),
) -> dict[str, Any]:
    """Flagship merged candidate list across the core scanners."""
    try:
        return await asyncio.to_thread(screeners.candidates, timeframe, persist)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/candidates/latest")
async def screener_candidates_latest(limit: int = Query(20)) -> dict[str, Any]:
    """Candidates from the last persisted scan — instant, no upstream calls."""
    try:
        return await asyncio.to_thread(screeners.latest_candidates, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Signal Scorecard ─────────────────────────────────────────────────────────


class GradeBody(BaseModel):
    """Body for an explicit grading run (a body keeps the POST non-CSRF-able)."""

    limit: int = scorecard.MAX_PER_RUN


@router.get("/scorecard")
async def screener_scorecard() -> dict[str, Any]:
    """Per-scanner track record (5/10/20-day returns vs EGX30) and ranking weights."""
    try:
        return await asyncio.to_thread(scorecard.scorecard)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/scorecard/grade")
async def screener_scorecard_grade(body: GradeBody) -> dict[str, Any]:
    """Grade pending scanner hits now (also runs in the post-close job)."""
    try:
        return await asyncio.to_thread(scorecard.grade, body.limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/scorecard/outcomes")
async def screener_scorecard_outcomes(
    scanner: str | None = Query(None), symbol: str | None = Query(None), limit: int = Query(100)
) -> Any:
    """Individual graded hits, newest first."""
    try:
        return await asyncio.to_thread(scorecard.outcomes, scanner, symbol, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Chart patterns ───────────────────────────────────────────────────────────


class PatternsBody(BaseModel):
    """Body for a live pattern scan."""

    universe: str = "EGX100"
    min_quality: int = 0


@router.get("/patterns")
async def screener_patterns(
    universe: str = Query("EGX100"), status: str | None = Query(None),
    category: str | None = Query(None),
) -> dict[str, Any]:
    """Latest stored pattern scan (post-close job); empty until the first run."""
    try:
        return await asyncio.to_thread(patterns.latest, universe, status, category)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/patterns/catalog")
async def screener_patterns_catalog() -> dict[str, Any]:
    """Every pattern the app knows: category, direction, kind, reliability/frequency tiers, EGX stats."""
    try:
        return await asyncio.to_thread(patterns.catalog)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/patterns/refresh")
async def screener_patterns_refresh(body: PatternsBody) -> dict[str, Any]:
    """Scan a universe for patterns now from Yahoo daily candles (~1 minute)."""
    try:
        return await asyncio.to_thread(patterns.compute, body.universe, True, body.min_quality)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Best setups (six-pillar checklist across the candidate set) ──────────────


class SetupsBody(BaseModel):
    """Body for a live setups run."""

    limit: int = 80
    symbols: list[str] | None = None


@router.get("/setups")
async def screener_setups(limit: int = Query(80), min_score: int = Query(0)) -> dict[str, Any]:
    """Latest stored checklist run across candidates/leaders/watchlist/holdings."""
    try:
        from app.services import setups

        return await asyncio.to_thread(setups.latest, limit, min_score)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/setups/refresh")
async def screener_setups_refresh(body: SetupsBody) -> dict[str, Any]:
    """Run the checklist across the candidate set now (~1 minute)."""
    try:
        from app.services import setups

        return await asyncio.to_thread(setups.compute, True, body.limit, body.symbols)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Relative-strength leaders ────────────────────────────────────────────────


class LeadersBody(BaseModel):
    """Body for a live leaders recompute."""

    universe: str = "EGX100"
    limit: int = 40
    include_illiquid: bool = False


@router.get("/leaders")
async def screener_leaders(
    universe: str = Query("EGX100"), limit: int = Query(40)
) -> dict[str, Any]:
    """Latest stored relative-strength ranking (post-close job); empty until the first run."""
    try:
        return await asyncio.to_thread(leaders.latest, universe, limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/leaders/refresh")
async def screener_leaders_refresh(body: LeadersBody) -> dict[str, Any]:
    """Recompute the ranking now from Yahoo history (~100 symbols; takes a minute)."""
    try:
        return await asyncio.to_thread(
            leaders.compute, body.universe, body.limit, True, body.include_illiquid
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
