"""Background job scheduling (APScheduler) on Cairo time.

Jobs (all wrapped: every run is recorded in ``job_runs`` and exceptions are
swallowed so the scheduler thread never dies):

    intraday           Sun-Thu 10:00-14:29 every 10 min  -> alerts.evaluate_all
    post_close         Sun-Thu 15:00                     -> snapshot + candidates + alerts
    morning_brief      Sun-Thu 09:30                     -> briefs.morning_brief (needs API key)
    weekly_maintenance Sat 12:00                         -> EGX symbol-list health probe

Service modules (market, screeners, alerts, briefs) are imported lazily inside
the job functions so this module never hard-depends on them at import time.
"""
from __future__ import annotations

import json
import logging
import threading
import traceback
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger

from app import db
from app.config import settings

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")
_DETAIL_MAX = 600

_scheduler: Optional[BackgroundScheduler] = None


# ── run wrapper ──────────────────────────────────────────────────────────────


def _summarize(result: Any) -> str:
    """Compact, truncated string form of a job result for job_runs.detail."""
    try:
        text = json.dumps(result, default=str)
    except (TypeError, ValueError):
        text = str(result)
    return text if len(text) <= _DETAIL_MAX else text[: _DETAIL_MAX - 3] + "..."


def _result_failed(result: Any) -> bool:
    """True when a job result carries an error at the top level or one level
    down (composite jobs like post_close nest per-stage results)."""
    if not isinstance(result, dict):
        return False
    if "error" in result:
        return True
    return any(isinstance(v, dict) and "error" in v for v in result.values())


def _notify_failure(job_name: str, detail: str) -> None:
    """Push a failed job to Telegram. A silent failure is an invisible one —
    the user would otherwise have to poll /api/status to notice.

    Deduped: when the job's PREVIOUS run also failed, no message is sent —
    a day-long outage otherwise produces 27 intraday pings; the transition
    into the failed state is the information, not every repetition.
    """
    try:
        prev = db.query(
            "SELECT ok FROM job_runs WHERE job = ? ORDER BY id DESC LIMIT 1 OFFSET 1",
            (job_name,),
        )
        if prev and not prev[0].get("ok"):
            logger.info("job %s still failing — Telegram ping suppressed (already notified)",
                        job_name)
            return
    except Exception:  # noqa: BLE001 — dedupe is best-effort, never block the ping
        pass
    try:
        from app.services.alerts import send_telegram

        send_telegram(f"[EGX scheduler] job '{job_name}' FAILED\n{detail[:600]}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not deliver failure notification: %s", exc)


def _run_job(job_name: str, fn: Callable[[], Any]) -> None:
    """Execute a job, record it in job_runs, and never raise."""
    started_at = datetime.now(CAIRO).isoformat()
    ok = 1
    detail = ""
    try:
        result = fn()
        if _result_failed(result):
            ok = 0
        detail = _summarize(result)
    except Exception as exc:
        ok = 0
        # Keep a real traceback: `str(exc)` alone rarely explains a failure
        # a week later, and job_runs.detail is the only forensic record.
        detail = f"exception: {exc}\n{traceback.format_exc()}"
        logger.exception("job %s failed", job_name)
    finished_at = datetime.now(CAIRO).isoformat()
    try:
        db.execute(
            "INSERT INTO job_runs (job, started_at, finished_at, ok, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_name, started_at, finished_at, ok, detail),
        )
    except Exception as exc:
        logger.error("could not record job_runs row for %s: %s", job_name, exc)
    if not ok:
        _notify_failure(job_name, detail)


def _wrap(job_name: str, fn: Callable[[], Any]) -> Callable[[], None]:
    def runner() -> None:
        _run_job(job_name, fn)

    runner.__name__ = f"job_{job_name}"
    return runner


# ── job bodies (lazy imports; each returns a summary dict) ───────────────────


def _skip_non_trading() -> Optional[dict]:
    """Skip marker when today is a weekend/holiday; None on trading days.

    The cron triggers only know weekdays — without this gate the jobs run on
    Eid and re-stamp stale data under the holiday's date, burn an LLM call
    narrating a closed market, and evaluate alerts against frozen prices.
    """
    from app import calendar_egx

    if not calendar_egx.is_trading_day():
        return {"skipped": "non-trading day (weekend/holiday)"}
    return None


def _job_intraday() -> dict:
    skip = _skip_non_trading()
    if skip:
        return skip
    from app.services import alerts

    return alerts.evaluate_all()


#: Serializes the post-close pipeline. max_instances=1 only guards a job
#: against ITSELF; the hourly catchup is a different job id on the same
#: thread pool, and after a laptop wake APScheduler can fire both misfires
#: in parallel — two full pipelines, racing alert evaluation into duplicate
#: Telegram sends.
_post_close_lock = threading.Lock()


def _job_post_close() -> dict:
    skip = _skip_non_trading()
    if skip:
        return skip
    if not _post_close_lock.acquire(blocking=False):
        return {"skipped": "post_close already running in another job"}
    try:
        return _post_close_body()
    finally:
        _post_close_lock.release()


def _post_close_body() -> dict:
    out: dict[str, Any] = {}
    try:
        from app.services import market

        out["snapshot"] = market.snapshot_universe("EGX100")
    except Exception as exc:
        out["snapshot"] = {"error": str(exc)}
    try:
        from app.services import market

        out["index"] = market.snapshot_egx30_index()
    except Exception as exc:
        out["index"] = {"error": str(exc)}
    try:
        from app.services import screeners

        candidates = screeners.candidates(persist=True)
        if isinstance(candidates, dict) and "candidates" in candidates:
            out["candidates"] = {"count": len(candidates.get("candidates") or [])}
        else:
            out["candidates"] = candidates
    except Exception as exc:
        out["candidates"] = {"error": str(exc)}
    try:
        from app.services import alerts

        out["alerts"] = alerts.evaluate_all()
    except Exception as exc:
        out["alerts"] = {"error": str(exc)}
    return out


def _job_morning_brief() -> dict:
    skip = _skip_non_trading()
    if skip:
        return skip
    if not settings.anthropic_api_key:
        return {"skipped": "ANTHROPIC_API_KEY not configured"}
    from app.services import briefs

    return briefs.morning_brief()


def _job_weekly_maintenance() -> dict:
    """Symbol-list health probe, table retention, and a database backup."""
    out: dict[str, Any] = {}

    # 1. Retention — these tables are append-only and otherwise grow forever.
    try:
        out["pruned"] = {
            "job_runs": db.prune("job_runs", "started_at", 90),
            "alerts_fired": db.prune("alerts_fired", "fired_at", 180),
            "scanner_hits": db.prune("scanner_hits", "created_at", 180),
            "backtest_runs": db.prune("backtest_runs", "ts", 365),
        }
    except Exception as exc:
        out["pruned"] = {"error": str(exc)}

    # 2. Backup (VACUUM INTO is safe against a live database).
    try:
        out["backup"] = db.backup()
    except Exception as exc:
        out["backup"] = {"error": str(exc)}

    # 3. Symbol-list health probe.
    try:
        from tradingview_mcp.core.services.coinlist import load_symbols
        from tradingview_mcp.core.services.screener_provider import (
            resilient_get_multiple_analysis,
        )

        symbols = load_symbols("egx")
        probe = symbols[:200]  # single screener batch
        if not probe:
            out["symbols"] = {"error": "load_symbols('egx') returned no symbols"}
        else:
            analysis = resilient_get_multiple_analysis(
                screener="egypt", interval="1D", symbols=probe
            )
            by_key = {str(k).upper(): v for k, v in (analysis or {}).items()}
            dead = [s for s in probe if by_key.get(str(s).upper()) is None]
            out["symbols"] = {
                "total_symbols": len(symbols),
                "probed": len(probe),
                "no_data": len(dead),
                "dead_symbols": dead[:30],
            }
    except Exception as exc:
        out["symbols"] = {"error": str(exc)}

    return out


def _job_catchup() -> dict:
    """Hourly sentinel: run the post-close work if today's session was missed.

    APScheduler SKIPS a run entirely once misfire_grace_time passes and records
    nothing at all — so a laptop asleep at 15:00 silently loses that whole
    trading day's snapshot. This notices the gap and fills it.
    """
    from app import calendar_egx

    now = datetime.now(CAIRO)
    if not calendar_egx.is_trading_day(now.date()):
        return {"skipped": "non-trading day"}
    # Only after the post-close job's own slot has passed.
    if (now.hour, now.minute) < (15, 5):
        return {"skipped": "before post-close window"}

    session = calendar_egx.last_trading_day(now.date()).strftime("%Y-%m-%d")
    try:
        # Exclude the EGX30 index row (written by a different stage from a
        # different source): with it counted, a day where TradingView failed
        # but Yahoo succeeded would look "already present (1 rows)" and the
        # universe snapshot would never be backfilled. Require a real
        # universe-sized result, not a stray row or two.
        rows = db.query(
            "SELECT COUNT(*) AS n FROM snapshots "
            "WHERE date = ? AND timeframe = '1D' AND symbol != 'EGX30'",
            (session,),
        )
        count = rows[0]["n"] if rows else 0
        if count >= 20:
            return {"skipped": f"snapshot for {session} already present ({count} rows)"}
    except Exception as exc:
        return {"error": f"catch-up check failed: {exc}"}

    logger.warning("catch-up: no usable snapshot for %s — running post_close now", session)
    result = _job_post_close()
    out: dict[str, Any] = {"caught_up_session": session, "post_close": result}
    # Stage errors inside the nested post_close result sit one level too deep
    # for _run_job's failure scan — lift them so the run records ok=0 and the
    # Telegram notification actually fires.
    if _result_failed(result):
        out["error"] = "catch-up post_close had failing stages"
    return out


# ── public API ───────────────────────────────────────────────────────────────


def start_scheduler(app: Any) -> None:
    """Create and start the BackgroundScheduler; safe to call more than once."""
    global _scheduler
    try:
        if _scheduler is not None and _scheduler.running:
            logger.info("scheduler already running")
            return
        sched = BackgroundScheduler(timezone=CAIRO)

        # 10:00-14:29, every 10 minutes, Sun-Thu (14:30+ excluded).
        # NOTE: APScheduler weekdays run mon=0..sun=6, so "sun-thu" is an
        # inverted range that raises ValueError — spell the days out instead.
        trading_days = "sun,mon,tue,wed,thu"
        intraday_trigger = OrTrigger([
            CronTrigger(day_of_week=trading_days, hour="10-13", minute="*/10", timezone=CAIRO),
            CronTrigger(day_of_week=trading_days, hour=14, minute="0,10,20", timezone=CAIRO),
        ])
        sched.add_job(
            _wrap("intraday", _job_intraday),
            trigger=intraday_trigger,
            id="intraday",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        sched.add_job(
            _wrap("post_close", _job_post_close),
            trigger=CronTrigger(day_of_week=trading_days, hour=15, minute=0, timezone=CAIRO),
            id="post_close",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        sched.add_job(
            _wrap("morning_brief", _job_morning_brief),
            trigger=CronTrigger(day_of_week=trading_days, hour=9, minute=30, timezone=CAIRO),
            id="morning_brief",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )
        sched.add_job(
            _wrap("weekly_maintenance", _job_weekly_maintenance),
            trigger=CronTrigger(day_of_week="sat", hour=12, minute=0, timezone=CAIRO),
            id="weekly_maintenance",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        # Hourly sentinel so a sleeping/offline machine doesn't silently lose a
        # session's snapshot (APScheduler records nothing for a skipped run).
        # Small grace on purpose: after a wake-up, post_close's own misfire
        # (grace 3600) should be the one that fires — a stale catchup misfire
        # firing alongside it in a parallel thread would duplicate the whole
        # pipeline. The next on-time :07 slot covers the gap instead, and the
        # _post_close_lock is the backstop if both ever do run.
        sched.add_job(
            _wrap("catchup", _job_catchup),
            trigger=CronTrigger(hour="*", minute=7, timezone=CAIRO),
            id="catchup",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

        sched.start()
        _scheduler = sched
        try:
            if hasattr(app, "state"):
                app.state.scheduler = sched
        except Exception:  # app may be anything; state attach is best-effort
            pass
        logger.info("scheduler started with %d jobs (Africa/Cairo)", len(sched.get_jobs()))
    except Exception as exc:
        # A dead scheduler silently kills every automated job — shout about it.
        logger.critical("start_scheduler failed — NO scheduled jobs will run: %s", exc)


def stop_scheduler() -> None:
    """Shut the scheduler down (used by tests / app shutdown); never raises."""
    global _scheduler
    try:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.warning("stop_scheduler failed: %s", exc)
    finally:
        _scheduler = None


def job_status() -> dict:
    """Last recorded run per job (from job_runs) plus next scheduled fire times."""
    try:
        rows = db.query(
            "SELECT job, started_at, finished_at, ok, detail FROM job_runs "
            "WHERE id IN (SELECT MAX(id) FROM job_runs GROUP BY job)"
        )
        last_runs = {
            row["job"]: {
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "ok": bool(row["ok"]),
                "detail": row["detail"],
            }
            for row in rows
        }
        next_fires: dict[str, Optional[str]] = {}
        running = bool(_scheduler is not None and _scheduler.running)
        if running:
            for job in _scheduler.get_jobs():  # type: ignore[union-attr]
                fire_time = getattr(job, "next_run_time", None)
                next_fires[job.id] = fire_time.isoformat() if fire_time else None
        return {
            "scheduler_enabled": settings.scheduler_enabled,
            "scheduler_running": running,
            "last_runs": last_runs,
            "next_fires": next_fires,
            "as_of": datetime.now(CAIRO).isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc)}
