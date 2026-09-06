"""EGX trading calendar: Cairo time, Sun-Thu sessions, 2026 public holidays."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CAIRO = ZoneInfo("Africa/Cairo")

SESSION_OPEN = time(10, 0)
SESSION_CLOSE = time(14, 30)

# Trading week is Sunday-Thursday. datetime.weekday(): Mon=0 ... Sun=6.
_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}  # Sun, Mon, Tue, Wed, Thu

# Best-effort 2026 Egyptian public holidays (EGX closures).
# Islamic (lunar) dates are APPROXIMATE — they depend on moon sighting and the
# official announcement; update from egx.com.eg when confirmed.
EGX_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 7),   # Coptic Christmas
        date(2026, 1, 25),  # January 25 Revolution / Police Day
        date(2026, 3, 20),  # Eid al-Fitr (approx.)
        date(2026, 3, 21),  # Eid al-Fitr holiday (approx.)
        date(2026, 3, 22),  # Eid al-Fitr holiday (approx.)
        date(2026, 3, 23),  # Eid al-Fitr holiday (approx.)
        date(2026, 4, 13),  # Sham El Nessim (Monday after Coptic Easter)
        date(2026, 4, 25),  # Sinai Liberation Day
        date(2026, 5, 1),   # Labour Day
        date(2026, 5, 27),  # Eid al-Adha (approx.)
        date(2026, 5, 28),  # Eid al-Adha holiday (approx.)
        date(2026, 5, 29),  # Eid al-Adha holiday (approx.)
        date(2026, 5, 30),  # Eid al-Adha holiday (approx.)
        date(2026, 6, 16),  # Islamic New Year (approx.)
        date(2026, 6, 30),  # June 30 Revolution Day
        date(2026, 7, 23),  # July 23 Revolution Day
        date(2026, 8, 25),  # Prophet's Birthday / Mawlid (approx.)
        date(2026, 10, 6),  # Armed Forces Day
    }
)


def now_cairo() -> datetime:
    """Current timezone-aware datetime in Africa/Cairo."""
    return datetime.now(CAIRO)


# Years the holiday table actually covers. Outside these, weekday-only logic
# silently treats every holiday as a trading day — warn (once per year) so the
# table gets updated instead of quietly degrading.
_HOLIDAY_YEARS: frozenset[int] = frozenset({d.year for d in EGX_HOLIDAYS})
_warned_years: set[int] = set()


def is_trading_day(d: date | None = None) -> bool:
    """True if `d` (default: today in Cairo) is a Sun-Thu non-holiday."""
    if d is None:
        d = now_cairo().date()
    if d.year not in _HOLIDAY_YEARS and d.year not in _warned_years:
        _warned_years.add(d.year)
        logger.warning(
            "EGX_HOLIDAYS has no entries for %d — holidays will be treated as "
            "trading days until app/calendar_egx.py is updated from egx.com.eg",
            d.year,
        )
    return d.weekday() in _TRADING_WEEKDAYS and d not in EGX_HOLIDAYS


def last_trading_day(d: date | None = None) -> date:
    """Most recent trading day at or before `d` (default: today in Cairo).

    Used to stamp snapshot rows with the session the data belongs to, so a
    manual snapshot on a Friday/holiday doesn't fabricate rows for a
    non-trading date.
    """
    if d is None:
        d = now_cairo().date()
    for _ in range(60):  # bounded scan; closures never span 60 days
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
    return d


def last_completed_session(dt: datetime | None = None) -> date:
    """Most recent session whose closing bar is final (default: now, Cairo).

    Distinct from `last_trading_day`, which returns today while today's session
    is still running. Anything that grafts a session bar onto a candle series
    must use this one: mid-session the day's OHLC is still moving, and a partial
    bar reads as a real one to the pattern and level detectors.
    """
    if dt is None:
        dt = now_cairo()
    elif dt.tzinfo is not None:
        dt = dt.astimezone(CAIRO)
    d = dt.date()
    if is_trading_day(d) and dt.time() >= SESSION_CLOSE:
        return d
    return last_trading_day(d - timedelta(days=1))


def is_market_open(dt: datetime | None = None) -> bool:
    """True if the EGX session is open at `dt` (default: now, Cairo time)."""
    if dt is None:
        dt = now_cairo()
    elif dt.tzinfo is not None:
        dt = dt.astimezone(CAIRO)
    if not is_trading_day(dt.date()):
        return False
    return SESSION_OPEN <= dt.time() < SESSION_CLOSE


def _next_open(dt: datetime) -> datetime:
    """First session-open datetime at or after `dt` (Cairo)."""
    d = dt.date()
    # Today still counts if the open hasn't passed yet.
    if is_trading_day(d) and dt.time() < SESSION_OPEN:
        return datetime.combine(d, SESSION_OPEN, tzinfo=CAIRO)
    d += timedelta(days=1)
    for _ in range(60):  # bounded scan; holidays never span 60 days
        if is_trading_day(d):
            return datetime.combine(d, SESSION_OPEN, tzinfo=CAIRO)
        d += timedelta(days=1)
    return datetime.combine(d, SESSION_OPEN, tzinfo=CAIRO)


def session_state() -> dict:
    """Current session snapshot for the API/UI."""
    now = now_cairo()
    return {
        "open": is_market_open(now),
        "now_cairo": now.isoformat(),
        "next_open": _next_open(now).isoformat(),
        "is_trading_day": is_trading_day(now.date()),
    }
