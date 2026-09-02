"""LLM-generated briefs (Module H).

Produces the daily morning market brief and per-stock investment theses using
the Anthropic API (model ``claude-opus-5``), persists results into the
``briefs`` table, and serves the latest stored brief.

Service functions never raise: every public function returns a dict, and any
failure is reported as ``{"error": "..."}``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app import db
from app.calendar_egx import now_cairo
from app.config import settings

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_CONTEXT_CHARS = 30_000

SYSTEM = (
    "You are a senior equity analyst covering the Egyptian Exchange (EGX). "
    "You are Arabic-aware (you recognize Arabic company names and Egyptian market "
    "conventions) but you always write your analysis in clear English. "
    "Base every claim strictly on the JSON context provided in the user message: "
    "cite only numbers that appear in that JSON, and never invent prices, "
    "percentages, or indicator values. If a data section contains an \"error\" "
    "key or is missing, say so briefly and move on. "
    "IMPORTANT data humility: every price in the context is delayed at least "
    "~15 minutes, and for EGX symbols is often a daily candle close or a "
    "prior-session snapshot — state the as_of/date of anything you cite and "
    "never present a delayed level as the current price. News coverage of EGX "
    "is sparse: absence of articles is NOT evidence of no news — when coverage "
    "is thin, say so explicitly rather than inferring calm. Never express more "
    "conviction than one day's delayed technical snapshot can support. "
    "Be concrete and decision oriented: highlight what matters, what changed, "
    "and what to watch. "
    "Always end your response with the exact sentence: \"Not financial advice.\""
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    """Cairo local date string YYYY-MM-DD."""
    return now_cairo().strftime("%Y-%m-%d")


def _now_iso() -> str:
    return now_cairo().isoformat()


def _to_json(data: Any, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Serialize gathered context to JSON, truncated to ``limit`` chars."""
    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001 - context must never break a brief
        text = json.dumps({"error": f"context serialization failed: {exc}"})
    if len(text) > limit:
        text = text[:limit] + "\n...[context truncated]"
    return text


def _safe(label: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a data-gathering function; on any failure return an error dict."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("briefs: gathering %s failed: %s", label, exc)
        return {"error": f"{label} unavailable: {exc}"}


def _call_claude(prompt: str) -> dict[str, Any]:
    """Run one brief-generation call against the Anthropic API.

    Returns ``{"content": text}`` on success or ``{"error": "..."}``.
    """
    if not settings.anthropic_api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    try:
        from anthropic import Anthropic
    except Exception as exc:  # noqa: BLE001 - SDK missing / broken install
        return {"error": f"anthropic SDK unavailable: {exc}"}

    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"failed to construct Anthropic client: {exc}"}

    msg = None
    try:
        # Primary path: current (2026) beta streaming API with adaptive
        # thinking and server-side refusal fallbacks.
        with client.beta.messages.stream(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=SYSTEM, messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
    except TypeError:
        # Installed SDK predates the fallbacks/betas kwargs — retry once with
        # the plain streaming surface.
        try:
            with client.messages.stream(
                model=MODEL, max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=SYSTEM, messages=[{"role": "user", "content": prompt}],
            ) as stream:
                msg = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"anthropic call failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"anthropic call failed: {exc}"}

    if msg is None:
        return {"error": "anthropic call returned no message"}

    if getattr(msg, "stop_reason", None) == "refusal":
        return {"error": "brief refused"}

    text = "".join(
        b.text for b in msg.content if getattr(b, "type", "") == "text"
    )
    if not text.strip():
        return {"error": "empty response from model"}
    return {"content": text}


def _save_brief(kind: str, content: str, symbol: str | None = None) -> str:
    """Insert a brief row; returns the Cairo date used."""
    date = _today()
    db.execute(
        "INSERT INTO briefs (date, kind, symbol, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (date, kind, symbol, content, _now_iso()),
    )
    return date


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def morning_brief() -> dict[str, Any]:
    """Generate and store today's morning market brief.

    Gathers market overview, screener candidates, alerts fired since
    yesterday, and open positions; builds one prompt; stores the result in
    ``briefs`` with kind ``morning``.
    """
    try:
        if not settings.anthropic_api_key:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        # Lazy imports to avoid import cycles with sibling services.
        from app.services import market, screeners

        # Context is serialized in insertion order and _to_json truncates from
        # the END — so risk-relevant sections (open positions, alerts) go
        # FIRST, and on a busy day it's the candidate list that gets cut,
        # never the user's own risk context.
        context: dict[str, Any] = {"generated_at": _now_iso()}

        try:
            from app.services import portfolio

            context["open_positions"] = _safe(
                "open positions", portfolio.list_positions, "open"
            )
        except Exception as exc:  # noqa: BLE001
            context["open_positions"] = {"error": f"positions unavailable: {exc}"}

        try:
            from datetime import timedelta

            cutoff = (now_cairo() - timedelta(days=1)).isoformat()
            context["alerts_fired_since_yesterday"] = db.query(
                "SELECT rule_id, symbol, message, fired_at, delivered "
                "FROM alerts_fired WHERE fired_at >= ? "
                "ORDER BY fired_at DESC LIMIT 50",
                (cutoff,),
            )
        except Exception as exc:  # noqa: BLE001
            context["alerts_fired_since_yesterday"] = {
                "error": f"alerts unavailable: {exc}"
            }

        context["market_overview"] = _safe("market overview", market.overview)
        context["screener_candidates"] = _safe(
            "screener candidates", screeners.candidates
        )

        prompt = (
            f"Today is {_today()} (Africa/Cairo). Write the EGX morning brief "
            "for a single active trader. Structure it as:\n"
            "1. Market pulse — index and breadth read, session context.\n"
            "2. Sector and leadership notes — where the strength/weakness is.\n"
            "3. Top screener candidates — for each notable candidate: why it "
            "fired, its score/signal, and a one-line WATCH CONDITION (what "
            "would have to happen before acting — never a buy/sell "
            "instruction; a day with no qualifying candidates is itself a "
            "valid, useful answer).\n"
            "4. Alerts and open positions — what fired since yesterday and "
            "how open positions look; flag any position near its stop or "
            "target.\n"
            "5. Plan for today — 3-5 bullet watch items.\n\n"
            "Use only the data in this JSON context:\n\n"
            f"{_to_json(context)}"
        )

        result = _call_claude(prompt)
        if "error" in result:
            return result

        content = result["content"]
        date = _save_brief("morning", content)
        return {"content": content, "date": date}
    except Exception as exc:  # noqa: BLE001
        logger.exception("morning_brief failed")
        return {"error": str(exc)}


def stock_thesis(symbol: str) -> dict[str, Any]:
    """Generate and store an investment thesis for one EGX symbol.

    Gathers full technical detail, multi-timeframe analysis, smart-money
    read, and news; stores the result in ``briefs`` with kind ``thesis``.
    """
    try:
        if not settings.anthropic_api_key:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return {"error": "symbol is required"}

        # Lazy import to avoid import cycles with sibling services.
        from app.services import stocks

        context: dict[str, Any] = {
            "generated_at": _now_iso(),
            "symbol": symbol,
            "detail": _safe("stock detail", stocks.detail, symbol),
            "multi_timeframe": _safe("multi-timeframe analysis", stocks.mtf, symbol),
            "smart_money": _safe("smart money analysis", stocks.smart_money, symbol),
            "news": _safe("news", stocks.news, symbol),
        }

        prompt = (
            f"Today is {_today()} (Africa/Cairo). Write a concise trading "
            f"thesis for EGX-listed stock {symbol}. Structure it as:\n"
            "1. Verdict — bullish / bearish / neutral, the two or three "
            "strongest reasons, and — explicitly — what evidence is MISSING "
            "that would firm this up (do NOT attach a conviction level; one "
            "day's delayed snapshot cannot support one).\n"
            "2. Technical picture — trend, momentum, key indicator readings, "
            "and multi-timeframe alignment or conflict.\n"
            "3. Trade plan assessment — entry, stop, targets and "
            "risk/reward if a plan is present; say whether the setup is "
            "worth taking and under what watch condition.\n"
            "4. Smart money and news — institutional footprints and any "
            "relevant headlines or sentiment; if news coverage is thin, say "
            "so rather than treating silence as calm.\n"
            "5. Risks and invalidation — what would flip the thesis.\n\n"
            "Use only the data in this JSON context:\n\n"
            f"{_to_json(context)}"
        )

        result = _call_claude(prompt)
        if "error" in result:
            return result

        content = result["content"]
        date = _save_brief("thesis", content, symbol=symbol)
        return {"content": content, "date": date, "symbol": symbol}
    except Exception as exc:  # noqa: BLE001
        logger.exception("stock_thesis failed for %s", symbol)
        return {"error": str(exc)}


def llm_debate(symbol: str) -> dict[str, Any]:
    """Generate and store a genuinely adversarial bull/bear debate for one symbol.

    Unlike ``stocks.debate`` (a deterministic rule checklist), this runs a real
    LLM debate grounded in the app's own data: a bull case, an independent bear
    case instructed to attack the bull case, and a judge's weighing. Stored in
    ``briefs`` with kind ``debate``.
    """
    try:
        if not settings.anthropic_api_key:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return {"error": "symbol is required"}

        # Lazy import to avoid import cycles with sibling services.
        from app.services import stocks

        context: dict[str, Any] = {
            "generated_at": _now_iso(),
            "symbol": symbol,
            "detail": _safe("stock detail", stocks.detail, symbol),
            "multi_timeframe": _safe("multi-timeframe analysis", stocks.mtf, symbol),
            "smart_money": _safe("smart money analysis", stocks.smart_money, symbol),
            "news": _safe("news", stocks.news, symbol),
        }

        prompt = (
            f"Today is {_today()} (Africa/Cairo). Stage a genuinely adversarial "
            f"debate about EGX-listed stock {symbol}. All prices in the context "
            "are delayed at least ~15 minutes and snapshot data may be from the "
            "prior close — state the as_of time of anything you cite and never "
            "present a delayed level as current. Structure:\n"
            "1. BULL CASE — the strongest honest case for buying, grounded in "
            "the data. Cite the specific numbers that support it.\n"
            "2. BEAR CASE — written as an independent skeptic whose job is to "
            "dismantle the bull case: attack its weakest assumptions, cite the "
            "data that contradicts it, and add risks the bull ignored "
            "(liquidity, staleness, one-day-signal fragility). Do NOT soften "
            "this section.\n"
            "3. JUDGE — weigh both cases. State which is stronger and why, "
            "what evidence is MISSING that would settle it, and a watch "
            "condition (what would have to happen before acting). Do not give "
            "a conviction level the data cannot support.\n\n"
            "Use only the data in this JSON context:\n\n"
            f"{_to_json(context)}"
        )

        result = _call_claude(prompt)
        if "error" in result:
            return result

        content = result["content"]
        date = _save_brief("debate", content, symbol=symbol)
        return {"content": content, "date": date, "symbol": symbol}
    except Exception as exc:  # noqa: BLE001
        logger.exception("llm_debate failed for %s", symbol)
        return {"error": str(exc)}


def latest(kind: str = "morning", symbol: str | None = None) -> dict[str, Any]:
    """Return the most recent stored brief of the given kind (and symbol)."""
    try:
        sql = (
            "SELECT id, date, kind, symbol, content, created_at "
            "FROM briefs WHERE kind = ?"
        )
        params: list[Any] = [kind]
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol.strip().upper())
        sql += " ORDER BY id DESC LIMIT 1"

        rows = db.query(sql, tuple(params))
        if not rows:
            return {"error": f"no {kind} brief found"}
        return rows[0]
    except Exception as exc:  # noqa: BLE001
        logger.exception("latest brief lookup failed")
        return {"error": str(exc)}
