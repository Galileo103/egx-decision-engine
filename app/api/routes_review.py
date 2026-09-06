"""Weekly review routes: the review payload, the week's lesson note, and the digest."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import review

router = APIRouter(prefix="/api/review", tags=["review"])


class NoteBody(BaseModel):
    week_start: str
    text: str = ""


class DigestBody(BaseModel):
    send: bool = True
    week: Optional[str] = None


@router.get("")
async def review_get(week: Optional[str] = Query(None)) -> dict[str, Any]:
    """The weekly review for the week containing ``week`` (default: last completed session's week)."""
    try:
        return await asyncio.to_thread(review.compute, week)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/note")
async def review_note(body: NoteBody) -> dict[str, Any]:
    """Save the week's lesson (free text)."""
    try:
        return await asyncio.to_thread(review.save_note, body.week_start, body.text)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/notes")
async def review_notes(limit: int = Query(12, ge=1, le=100)) -> dict[str, Any]:
    try:
        return {"notes": await asyncio.to_thread(review.notes, limit)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/digest")
async def review_digest(body: DigestBody) -> dict[str, Any]:
    """Build the Telegram digest (and send it when ``send`` is true)."""
    try:
        return await asyncio.to_thread(review.digest, body.send, body.week)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
