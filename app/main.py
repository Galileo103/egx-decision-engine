"""FastAPI application: routers, lifespan (DB init + scheduler), static frontend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import calendar_egx, db, logging_setup
from app.config import settings

logger = logging.getLogger("egx.main")

# Router imports pull in every service module, which import tradingview_mcp at
# module level — and that package is an editable install inside OneDrive that
# sync can move. A failed import here must NOT kill the whole server: boot into
# a degraded mode where /api/health still serves and explains the problem.
_ROUTERS: list[Any] = []
_router_error: str | None = None
try:
    from app.api import (
        routes_alerts,
        routes_backtest,
        routes_brief,
        routes_market,
        routes_portfolio,
        routes_screener,
        routes_stocks,
        routes_symbols,
    )

    _ROUTERS = [
        routes_market.router,
        routes_stocks.router,
        routes_stocks.watchlist_router,
        routes_screener.router,
        routes_backtest.router,
        routes_portfolio.router,
        routes_alerts.router,
        routes_brief.router,
        routes_symbols.router,
    ]
except Exception as exc:  # noqa: BLE001
    _router_error = str(exc)
    logging.basicConfig(level=logging.INFO)  # logging_setup runs later, in lifespan
    logger.critical(
        "API routers failed to import — serving DEGRADED (health + static only). "
        "Likely the tradingview_mcp editable install moved (OneDrive?). Error: %s",
        exc,
    )

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


#: Dependency probe result, surfaced by /api/health.
_core_status: dict[str, Any] = {"state": "unknown"}


def _probe_core_library() -> dict[str, Any]:
    """Check the tradingview_mcp editable install once at startup.

    The package lives in a OneDrive folder; sync/hydration can move it. Every
    service imports it at module level, so a failure is fatal — at least log
    WHERE it resolved from and expose it in /api/health for diagnosis.
    """
    try:
        import tradingview_mcp

        path = getattr(tradingview_mcp, "__file__", None) or "unknown"
        version = getattr(tradingview_mcp, "__version__", "unknown")
        logger.info("tradingview_mcp resolved: %s (version %s)", path, version)
        return {"state": "ok", "path": path, "version": version}
    except Exception as exc:  # noqa: BLE001
        logger.critical("tradingview_mcp UNAVAILABLE — analytics endpoints will fail: %s", exc)
        return {"state": "missing", "error": str(exc)}


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize logging + database and (optionally) start the scheduler."""
    global _core_status
    logging_setup.configure_logging()
    _core_status = _probe_core_library()
    try:
        db.init_db()
    except Exception:  # noqa: BLE001
        logger.exception("init_db failed at startup")
    if settings.scheduler_enabled:
        try:
            from app import scheduler

            scheduler.start_scheduler(application)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler failed to start")
    else:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=0)")
    yield
    # Shutdown: stop the scheduler thread before the interpreter tears down,
    # otherwise a mid-flight job keeps writing to a closing SQLite connection.
    try:
        from app import scheduler

        scheduler.stop_scheduler()
    except Exception:  # noqa: BLE001
        logger.warning("scheduler shutdown failed", exc_info=True)
    try:
        db.close_conn()
    except Exception:  # noqa: BLE001
        logger.warning("db close failed", exc_info=True)


app = FastAPI(
    title="EGX Decision Engine",
    description="Local-first decision support for the Egyptian Exchange. "
    "Analysis tooling — not financial advice.",
    version="1.0.0",
    lifespan=lifespan,
)


#: Hosts allowed to issue state-changing requests (the app itself).
_ALLOWED_HOSTS = {
    f"127.0.0.1:{settings.port}", f"localhost:{settings.port}",
    f"{settings.host}:{settings.port}",
}


@app.middleware("http")
async def block_cross_origin_writes(request: Request, call_next: Any) -> Any:
    """Reject state-changing requests that originate from another site.

    Several POSTs take no JSON body (brief/morning, alerts/evaluate,
    market/snapshot, symbols/refresh), which makes them "simple requests":
    any page the user visits could submit a cross-origin form to
    127.0.0.1 and silently burn Anthropic credits or hammer TradingView.
    Same-origin requests send Origin matching the app, or no Origin at all
    (curl, the browser address bar) — both are allowed.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            netloc = urlparse(origin).netloc.lower()
            # Standard same-origin test first: the Origin matching the Host
            # the request arrived on covers HOST=0.0.0.0 setups where the UI
            # is loaded via a LAN IP or [::1] that no static list predicts.
            request_host = (request.headers.get("host") or "").lower()
            if netloc != request_host and netloc not in _ALLOWED_HOSTS:
                logger.warning("blocked cross-origin %s %s from %s",
                               request.method, request.url.path, origin)
                return JSONResponse(
                    status_code=403,
                    content={"error": f"cross-origin {request.method} from {origin} refused"},
                )
    return await call_next(request)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Liveness, EGX session state, core-library status and data freshness."""
    try:
        session = calendar_egx.session_state()
    except Exception as exc:  # noqa: BLE001
        session = {"error": str(exc)}

    freshness: dict[str, Any] = {}
    try:
        rows = await asyncio.to_thread(
            db.query,
            # Exclude the EGX30 index row — it comes from a different source
            # (Yahoo) than the universe snapshot (TradingView), and one index
            # row must not make a failed universe snapshot look "current".
            "SELECT MAX(date) AS d FROM snapshots "
            "WHERE timeframe = '1D' AND symbol != 'EGX30'",
        )
        last_snapshot = rows[0].get("d") if rows else None
        brief_rows = await asyncio.to_thread(
            db.query, "SELECT MAX(date) AS d FROM briefs WHERE kind = 'morning'"
        )
        # "Current" means: we hold the snapshot for the last session whose
        # post-close job has had a chance to run. Before ~15:05 on a trading
        # day, today's snapshot cannot exist yet — expecting it would leave
        # the flag red every morning, training the user to ignore it.
        from datetime import timedelta as _td

        now = calendar_egx.now_cairo()
        ref = now.date()
        if calendar_egx.is_trading_day(ref) and (now.hour, now.minute) < (15, 5):
            ref = ref - _td(days=1)
        expected = calendar_egx.last_trading_day(ref).strftime("%Y-%m-%d")
        freshness = {
            "last_snapshot_date": last_snapshot,
            "last_morning_brief_date": brief_rows[0].get("d") if brief_rows else None,
            "expected_session": expected,
            "snapshots_current": last_snapshot == expected,
        }
    except Exception as exc:  # noqa: BLE001
        freshness = {"error": str(exc)}

    return {
        "ok": True,
        "session": session,
        "core_library": _core_status,
        "degraded": _router_error is not None,
        "router_error": _router_error,
        "data_freshness": freshness,
    }


@app.get("/api/status")
async def status() -> dict[str, Any]:
    """Scheduler job status: last runs and next fire times."""
    try:
        from app import scheduler

        return await asyncio.to_thread(scheduler.job_status)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


for _router in _ROUTERS:
    app.include_router(_router)

# Static frontend LAST so /api/* wins over the catch-all mount.
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
