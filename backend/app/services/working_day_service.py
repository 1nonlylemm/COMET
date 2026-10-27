"""working_day_service.py

Authoritative shared service for holiday-aware working-day arithmetic in COMET.
Consolidated single source of truth for:
- SlaDeadline due date computation and countdown tracking (sla_service)
- Escalation breach candidate identification and auto-escalation intervals (escalation_service)
- Official notice follow-up reminders (notice_follow_up_service)

Precedence Rules:
1. LGU-specific non-working date (scope='lgu', matching lgu_id)
2. Laguna Provincial non-working date (scope='provincial')
3. National non-working date (scope='national')
4. Explicit special working day (is_non_working=False overrides normal weekend/holiday designation)
5. Ordinary weekend (Saturday/Sunday -> non-working)
6. Ordinary weekday (Monday-Friday -> working)

Missing Calendar Safety:
- For formal compliance deadlines (is_formal_deadline=True):
  If the engine encounters a year whose calendar data is unconfigured in the database,
  it raises WorkingCalendarUnavailableError rather than silently falling back to weekday-only.
- For internal tracking timers (is_formal_deadline=False):
  It logs an operational warning and falls back to weekday-only calculation.
"""
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Optional, Union

from sqlalchemy import extract

logger = logging.getLogger(__name__)


class WorkingCalendarUnavailableError(Exception):
    """Raised when a formal compliance deadline requires holiday calendar data that is not configured."""

    def __init__(self, message: str, year: Optional[int] = None, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.year = year
        self.status_code = status_code


# In-memory cache for year holiday mappings:
# Key: (year, lgu_id) -> Dict[date, bool] (date -> is_non_working)
_CALENDAR_CACHE = {}
_CONFIGURED_YEARS_CACHE = set()


def clear_holiday_cache():
    """Clear in-memory holiday calendar cache."""
    global _CALENDAR_CACHE, _CONFIGURED_YEARS_CACHE
    _CALENDAR_CACHE.clear()
    _CONFIGURED_YEARS_CACHE.clear()


def _to_aware_datetime(value: Union[date, datetime]) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def _compute_easter_holidays(year: int) -> dict:
    """Safe statutory fallback: Computes movable Holy Week holidays from Easter Sunday via dateutil."""
    try:
        from dateutil.easter import easter
    except ImportError:
        return {}

    easter_sunday = easter(year)
    maundy_thursday = easter_sunday - timedelta(days=3)
    good_friday = easter_sunday - timedelta(days=2)
    black_saturday = easter_sunday - timedelta(days=1)

    return {
        maundy_thursday: True,
        good_friday: True,
        black_saturday: True,
    }


def _load_year_holidays(year: int, lgu_id: Optional[int] = None) -> dict:
    """Load and cache holiday records for a specific year and optional LGU.

    Returns dict mapping date -> is_non_working.
    """
    cache_key = (year, lgu_id)
    if cache_key in _CALENDAR_CACHE:
        return _CALENDAR_CACHE[cache_key]

    # Check if HolidayCalendar table exists and has rows for this year
    try:
        from app.models.calendar import HolidayCalendar

        records = HolidayCalendar.query.filter(
            extract('year', HolidayCalendar.holiday_date) == year
        ).all()
    except Exception as exc:
        logger.debug("Database query for HolidayCalendar failed or not in app context: %s", exc)
        records = None

    if records is not None and len(records) > 0:
        _CONFIGURED_YEARS_CACHE.add(year)
        # Precedence: National -> Provincial -> LGU
        # Also handle special working days (is_non_working=False)
        date_map = {}

        # 1. National
        for r in records:
            if r.scope == 'national':
                date_map[r.holiday_date] = (r.is_non_working, getattr(r, 'is_provisional', False))

        # 2. Provincial
        for r in records:
            if r.scope == 'provincial':
                date_map[r.holiday_date] = (r.is_non_working, getattr(r, 'is_provisional', False))

        # 3. LGU-specific (only if matching lgu_id)
        if lgu_id is not None:
            for r in records:
                if r.scope == 'lgu' and r.lgu_id == lgu_id:
                    date_map[r.holiday_date] = (r.is_non_working, getattr(r, 'is_provisional', False))

        _CALENDAR_CACHE[cache_key] = date_map
        return date_map

    # No records in database for this year
    _CALENDAR_CACHE[cache_key] = None
    return None


def is_working_day(
    date_or_dt: Union[date, datetime],
    lgu_id: Optional[int] = None,
    *,
    is_formal_deadline: bool = True,
) -> bool:
    """Determine whether a given date is an official working day under Philippine law and local calendar.

    Precedence:
    1. LGU non-working
    2. Provincial non-working
    3. National non-working
    4. Explicit special working day (is_non_working=False)
    5. Ordinary weekend (Saturday/Sunday -> non-working)
    6. Ordinary weekday (Monday-Friday -> working)

    Missing-calendar and Provisional Safety:
    - If formal compliance deadline requires holiday data for an unseeded year, raises WorkingCalendarUnavailableError.
    - If formal compliance deadline encounters a provisional holiday record (unproclaimed), raises WorkingCalendarUnavailableError.
    - Internal tracking timers fall back to weekday arithmetic or evaluate provisional entries with an operational warning log.
    """
    check_date = date_or_dt.date() if isinstance(date_or_dt, datetime) else date_or_dt
    year = check_date.year

    year_holidays = _load_year_holidays(year, lgu_id=lgu_id)

    if year_holidays is None:
        # Year is not configured in database
        if is_formal_deadline:
            raise WorkingCalendarUnavailableError(
                f"The working-day calendar for {year} is not configured. "
                "This formal compliance deadline cannot be calculated safely.",
                year=year,
                status_code=422,
            )
        logger.warning(
            "Working-day calendar for year %s is not configured. "
            "Falling back to operational weekday-only calculation for tracking timer.",
            year,
        )
        return check_date.weekday() < 5

    # If date is explicitly registered in holiday calendar:
    if check_date in year_holidays:
        is_non_working, is_provisional = year_holidays[check_date]
        if is_provisional:
            if is_formal_deadline:
                raise WorkingCalendarUnavailableError(
                    f"The calendar entry for {check_date} is provisional (official annual proclamation not yet issued). "
                    "This formal compliance deadline cannot be calculated authoritatively.",
                    year=year,
                    status_code=422,
                )
            logger.warning(
                "Calendar entry for %s is provisional. Using as non-binding estimate for internal tracking timer.",
                check_date,
            )
        if not is_non_working:
            # Explicit special working day (offices remain open)
            return True
        # Explicit non-working day (regular holiday, special non-working, local holiday, suspension)
        return False

    # Default: Monday-Friday = working day, Saturday-Sunday = non-working day
    return check_date.weekday() < 5


def add_working_days(
    start_dt: Union[date, datetime],
    working_days: int,
    lgu_id: Optional[int] = None,
    *,
    is_formal_deadline: bool = True,
) -> datetime:
    """Add a specified number of working days to a start date/datetime.

    In accordance with Philippine Civil Code (Article 13):
    The trigger day is excluded, and counting begins on the succeeding calendar day.
    """
    if working_days is None or working_days == 0:
        return _to_aware_datetime(start_dt)
    if working_days < 0:
        raise ValueError("Working days must be zero or positive")

    current = _to_aware_datetime(start_dt)
    remaining = working_days

    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline):
            remaining -= 1

    return current


def count_working_days_between(
    start_dt: Union[date, datetime],
    end_dt: Union[date, datetime],
    lgu_id: Optional[int] = None,
    *,
    is_formal_deadline: bool = True,
) -> int:
    """Count the number of working days elapsed between start_dt and end_dt.

    Counting excludes start_dt and includes end_dt. Returns 0 if end_dt <= start_dt.
    """
    start = _to_aware_datetime(start_dt)
    end = _to_aware_datetime(end_dt)
    if end <= start:
        return 0

    current_date = start.date()
    end_date = end.date()
    working_days = 0

    while current_date < end_date:
        current_date += timedelta(days=1)
        if is_working_day(current_date, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline):
            working_days += 1

    return working_days


def working_days_delta(
    from_dt: Union[date, datetime],
    to_dt: Union[date, datetime],
    lgu_id: Optional[int] = None,
    *,
    is_formal_deadline: bool = True,
) -> int:
    """Calculate signed working-day difference between two timestamps.

    Returns positive if to_dt >= from_dt, negative otherwise.
    """
    start = _to_aware_datetime(from_dt)
    end = _to_aware_datetime(to_dt)
    if end >= start:
        return count_working_days_between(start, end, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline)
    return -count_working_days_between(end, start, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline)
