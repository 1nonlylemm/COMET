"""
Datetime Utilities
Provides timezone-safe datetime parsing and ISO 8601 UTC serialization.
"""
from datetime import date, datetime, timezone


def to_iso_utc(dt):
    """
    Serialize a date/datetime to an ISO 8601 UTC string.
    If naive datetime, assumes UTC and explicitly attaches +00:00.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        cleaned = dt.strip()
        if not cleaned:
            return None
        if cleaned.endswith('Z') or '+' in cleaned or (len(cleaned) > 10 and '-' in cleaned[10:]):
            return cleaned
        return f"{cleaned}Z"
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)
