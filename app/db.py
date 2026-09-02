"""SQLite persistence layer (stdlib sqlite3, no ORM).

A single module-level connection in WAL mode, guarded by a threading.Lock so
sync service code called from worker threads can share it safely.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from app.config import settings

logger = logging.getLogger(__name__)

_CAIRO = ZoneInfo("Africa/Cairo")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
#: Set by close_conn(); get_conn refuses to resurrect the connection after an
#: intentional close, so a scheduler thread still running during shutdown
#: fails loudly instead of silently writing to a "closed" database.
_closed = False

_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, date TEXT, timeframe TEXT,
        price REAL, change_pct REAL, volume REAL, rsi REAL, bbw REAL,
        rating INTEGER, signal TEXT, score REAL, score_json TEXT, created_at TEXT,
        UNIQUE(symbol, date, timeframe)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scanner_hits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, scanner TEXT, symbol TEXT, payload_json TEXT, created_at TEXT,
        UNIQUE(date, scanner, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist(
        symbol TEXT PRIMARY KEY, note TEXT, added_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, rule_type TEXT, params_json TEXT,
        enabled INTEGER DEFAULT 1, created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts_fired(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id INTEGER, symbol TEXT, message TEXT, fired_at TEXT,
        delivered INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT DEFAULT 'long', qty REAL, entry REAL, stop REAL,
        target1 REAL, target2 REAL, opened_at TEXT, closed_at TEXT, exit_price REAL,
        plan_json TEXT, note TEXT, status TEXT DEFAULT 'open'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS briefs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, kind TEXT, symbol TEXT, content TEXT, created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job TEXT, started_at TEXT, finished_at TEXT, ok INTEGER, detail TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, kind TEXT, symbol TEXT, strategy TEXT,
        period TEXT, interval TEXT, params_json TEXT, result_json TEXT
    )
    """,
)


def get_conn() -> sqlite3.Connection:
    """Return the shared SQLite connection, creating it on first use.

    The connection uses ``sqlite3.Row`` as row factory, allows cross-thread
    use (``check_same_thread=False`` — all access is serialized through the
    module lock), and runs in WAL journal mode.
    """
    global _conn
    with _lock:
        if _conn is None:
            if _closed:
                raise RuntimeError("database connection was closed at shutdown")
            conn = sqlite3.connect(
                settings.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            # WAL already gives durability across app crashes; NORMAL avoids an
            # fsync per commit, which matters for the ~380 row snapshot loop.
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            _conn = conn
        return _conn


def close_conn() -> None:
    """Close the shared connection (app shutdown / tests). Never raises.

    After this, get_conn() raises instead of silently reopening — a late
    scheduler write surfaces as a logged failure, not an invisible one.
    init_db() lifts the latch for the next deliberate startup.
    """
    global _conn, _closed
    with _lock:
        _closed = True
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
            _conn = None


# Additive column migrations for tables created by earlier versions.
# SQLite has no "ADD COLUMN IF NOT EXISTS", so each ALTER is tried and the
# "duplicate column" error is swallowed.
_MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE positions ADD COLUMN fees REAL",
    "ALTER TABLE positions ADD COLUMN plan_followed INTEGER",
)

# Indexes on the hot query paths. Without these the 10-minute alert cycle
# full-scans alerts_fired for every rule hit and snapshots for every
# squeeze/score rule — both tables grow forever.
_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_snapshots_tf_date ON snapshots(timeframe, date)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_date ON snapshots(symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_fired_dedupe "
    "ON alerts_fired(rule_id, symbol, fired_at)",
    "CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job, id)",
    # Unique so a manual candidates(persist=True) plus the scheduled post-close
    # run cannot store the same day's hits twice. On a pre-existing table that
    # already holds duplicates this creation fails and is skipped — dedupe
    # runs first in init_db().
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_scanner_hits_unique "
    "ON scanner_hits(date, scanner, symbol)",
    "CREATE INDEX IF NOT EXISTS idx_backtest_runs_symbol ON backtest_runs(symbol, ts)",
)

#: Collapse pre-existing duplicate scanner_hits rows (keep the newest id) so
#: the unique index above can be created on an established database.
_DEDUPE_SCANNER_HITS = """
    DELETE FROM scanner_hits WHERE id NOT IN (
        SELECT MAX(id) FROM scanner_hits GROUP BY date, scanner, symbol
    )
"""


def init_db() -> None:
    """Create all application tables if they do not already exist."""
    global _closed
    with _lock:
        _closed = False  # a deliberate (re)start lifts the shutdown latch
    conn = get_conn()
    with _lock:
        for ddl in _SCHEMA:
            conn.execute(ddl)
        for mig in _MIGRATIONS:
            try:
                conn.execute(mig)
            except sqlite3.OperationalError:
                pass  # column already exists
        try:
            conn.execute(_DEDUPE_SCANNER_HITS)
        except sqlite3.Error as exc:
            logger.warning("scanner_hits dedupe failed: %s", exc)
        for ddl in _INDEXES:
            try:
                conn.execute(ddl)
            except sqlite3.Error as exc:
                # A missing table on a partial schema is fine; a failed UNIQUE
                # index is not — INSERT OR REPLACE silently degrades to plain
                # INSERT without it, so the failure must be visible.
                logger.warning("index creation failed (%s): %s", ddl.split("(")[0].strip(), exc)
        conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    """Run a SELECT and return rows as plain dicts."""
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
        cur.close()
    return [dict(row) for row in rows]


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run an INSERT/UPDATE/DELETE, commit, and return the last row id."""
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        lastrowid = cur.lastrowid or 0
        cur.close()
    return lastrowid


def execute_rowcount(sql: str, params: Iterable[Any] = ()) -> int:
    """Run an UPDATE/DELETE, commit, and return the number of affected rows."""
    conn = get_conn()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        rowcount = cur.rowcount
        cur.close()
    return rowcount if rowcount is not None and rowcount >= 0 else 0


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> int:
    """Run one statement over many parameter tuples in a SINGLE transaction.

    The snapshot loop used to call execute() ~380 times — one lock acquisition
    and one commit per row, with no atomicity: a crash mid-loop left a
    half-written date that then became "the latest snapshot", silently
    shrinking every universe-wide alert. Returns the number of affected rows.
    """
    payload = [tuple(r) for r in rows]
    if not payload:
        return 0
    conn = get_conn()
    with _lock:
        try:
            cur = conn.executemany(sql, payload)
            conn.commit()
            rowcount = cur.rowcount
            cur.close()
        except Exception:
            conn.rollback()
            raise
    return rowcount if rowcount is not None and rowcount >= 0 else 0


def prune(table: str, date_column: str, keep_days: int) -> int:
    """Delete rows older than ``keep_days`` from an append-only table.

    Table and column names are validated against a whitelist — they cannot be
    parameterized in SQL, so they must never come from user input.
    """
    allowed = {
        "job_runs": "started_at",
        "alerts_fired": "fired_at",
        "scanner_hits": "created_at",
        "backtest_runs": "ts",
    }
    if allowed.get(table) != date_column:
        raise ValueError(f"prune: refusing unknown table/column {table}.{date_column}")
    # Cutoff in Cairo time to match what the producers store — the comparison
    # is lexicographic over ISO strings, so mixing offsets skews the boundary
    # by the UTC offset.
    cutoff = (
        datetime.now(_CAIRO) - timedelta(days=int(keep_days))
    ).isoformat()
    return execute_rowcount(
        f"DELETE FROM {table} WHERE {date_column} < ?", (cutoff,)  # noqa: S608
    )


def backup(target_dir: str | None = None) -> dict[str, Any]:
    """Write a consistent snapshot of the database via VACUUM INTO.

    Safe to run while the app is live (unlike copying the file, which can
    catch a torn WAL). Keeps the 7 most recent backups.
    """
    try:
        base = Path(target_dir) if target_dir else Path(settings.db_path).resolve().parent / "backup"
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(_CAIRO).strftime("%Y%m%d-%H%M%S")
        dest = base / f"egx-{stamp}.db"
        conn = get_conn()
        with _lock:
            # VACUUM INTO takes a literal path; quote it for SQL safety.
            conn.execute(f"VACUUM INTO '{str(dest).replace(chr(39), chr(39) * 2)}'")
        existing = sorted(base.glob("egx-*.db"), key=lambda p: p.name, reverse=True)
        removed = 0
        for stale in existing[7:]:
            try:
                stale.unlink()
                removed += 1
            except OSError:
                pass
        return {"backup": str(dest), "size_bytes": dest.stat().st_size, "pruned_backups": removed}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
