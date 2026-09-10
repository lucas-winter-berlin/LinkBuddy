"""Zeitfenster fuer die zeitbasierten Commands und Statistiken.

Alle Grenzen werden in der Bot-Zeitzone bestimmt und als UTC zurueckgegeben,
damit sie direkt gegen ``created_at`` verglichen werden koennen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PERIOD_ALIASES = {
    "heute": "heute",
    "today": "heute",
    "woche": "woche",
    "week": "woche",
    "monat": "monat",
    "month": "monat",
    "jahr": "jahr",
    "year": "jahr",
    "all": "all",
    "alle": "all",
    "gesamt": "all",
}

PERIOD_LABELS = {
    "heute": "heute",
    "woche": "diese Woche",
    "monat": "diesen Monat",
    "jahr": "dieses Jahr",
    "all": "insgesamt",
}


def parse_period(value: str | None, *, default: str = "all") -> str:
    if not value:
        return default
    return PERIOD_ALIASES.get(value.strip().lower(), default)


def local_now(tz: ZoneInfo, *, now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(tz)


def period_start(
    period: str, tz: ZoneInfo, *, now: datetime | None = None
) -> datetime | None:
    """Untere Grenze eines Zeitraums in UTC. None bedeutet "ohne Grenze"."""
    reference = local_now(tz, now=now)

    if period == "heute":
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "woche":
        start = reference - timedelta(days=7)
    elif period == "monat":
        start = reference - timedelta(days=30)
    elif period == "jahr":
        start = reference - timedelta(days=365)
    else:
        return None

    return start.astimezone(timezone.utc)


def previous_window(
    period: str, tz: ZoneInfo, *, now: datetime | None = None
) -> tuple[datetime, datetime] | None:
    """Der gleich lange Zeitraum davor -- Basis fuer Trend-Prozente."""
    start = period_start(period, tz, now=now)
    if start is None:
        return None
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    length = reference - start
    return start - length, start


def trend_percent(current: int, previous: int) -> str | None:
    """Veraenderung gegenueber dem Vorzeitraum als "+20%"."""
    if previous <= 0:
        return "neu" if current > 0 else None
    change = round((current - previous) / previous * 100)
    sign = "+" if change >= 0 else ""
    return f"{sign}{change}%"
