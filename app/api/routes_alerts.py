"""Alert routes: rule CRUD, fired-alert feed, on-demand evaluation."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import db
from app.services import alerts

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class RuleBody(BaseModel):
    """Body for creating an alert rule."""

    name: str
    rule_type: str
    params: dict[str, Any] = {}


class ToggleBody(BaseModel):
    """Body for enabling/disabling a rule."""

    enabled: bool


@router.get("/rules")
async def alerts_rules() -> Any:
    """List all alert rules."""
    try:
        return await asyncio.to_thread(alerts.list_rules)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/rules")
async def alerts_create_rule(body: RuleBody) -> dict[str, Any]:
    """Create a new alert rule."""
    try:
        return await asyncio.to_thread(
            alerts.create_rule, body.name, body.rule_type, body.params
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.delete("/rules/{rule_id}")
async def alerts_delete_rule(rule_id: int) -> dict[str, Any]:
    """Delete an alert rule; ok reflects whether a row was actually removed."""
    try:
        return await asyncio.to_thread(alerts.delete_rule, rule_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@router.post("/rules/{rule_id}/toggle")
async def alerts_toggle_rule(rule_id: int, body: ToggleBody) -> dict[str, Any]:
    """Enable or disable an alert rule; ok reflects whether a row was updated."""
    try:
        return await asyncio.to_thread(alerts.toggle_rule, rule_id, body.enabled)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@router.get("/fired")
async def alerts_fired(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """Most recently fired alerts."""
    try:
        rows = await asyncio.to_thread(
            db.query,
            "SELECT * FROM alerts_fired ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return {"fired": rows}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/evaluate")
async def alerts_evaluate() -> dict[str, Any]:
    """Evaluate every enabled rule now."""
    try:
        return await asyncio.to_thread(alerts.evaluate_all)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
