"""Textbausteine fuer die Telegram-Ausgabe (Parse-Mode HTML)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape as _html_escape

from ..icons import DIVIDER, html, mark
from ..db.models import Resource, ensure_utc
from .tags import format_tags
from .urls import source_label

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def esc(value: object) -> str:
    """HTML-Escaping fuer alles, was in eine Telegram-Nachricht wandert."""
    return _html_escape(str(value if value is not None else ""), quote=False)


def number_emoji(index: int) -> str:
    """Kompatibilitaets-Alias fuer Listennummern."""
    return mark(index)


def relative_age(value: datetime, *, now: datetime | None = None) -> str:
    """English relative age like "2 hours ago" or "3 days ago"."""
    now = now or datetime.now(timezone.utc)
    delta = now - ensure_utc(value)
    seconds = int(delta.total_seconds())

    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"

    hours = minutes // 60
    if hours < 24:
        return "1 hour ago" if hours == 1 else f"{hours} hours ago"

    days = hours // 24
    if days < 7:
        return "1 day ago" if days == 1 else f"{days} days ago"

    weeks = days // 7
    if days < 31:
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"

    months = days // 30
    if months < 12:
        return "1 month ago" if months == 1 else f"{months} months ago"

    years = days // 365
    return "1 year ago" if years == 1 else f"{years} years ago"


def format_date(value: datetime, tz) -> str:
    """Datum in lokaler Zeitzone als TT.MM.JJJJ."""
    return ensure_utc(value).astimezone(tz).strftime("%d.%m.%Y")


def format_long_date(value: datetime, tz) -> str:
    """Datum als "23 January 2026"."""
    local = ensure_utc(value).astimezone(tz)
    return f"{local.day} {MONTHS[local.month - 1]} {local.year}"


def display_title(resource: Resource) -> str:
    """Titel, sonst gekuerzte URL."""
    if resource.title:
        return resource.title
    return shorten_url(resource.url)


def shorten_url(url: str, *, max_length: int = 60) -> str:
    if len(url) <= max_length:
        return url
    return url[: max_length - 1] + "…"


def progress_bar(fraction: float, *, width: int = 10) -> str:
    """Balken aus gefuellten und leeren Bloecken."""
    filled = max(0, min(width, round(fraction * width)))
    return "▓" * filled + "░" * (width - filled)


def simple_link_list(resources: list[Resource]) -> str:
    """Kompakte Liste: - Titel (als Link)."""
    if not resources:
        return "· no links"
    return "\n".join(
        f'- <a href="{esc(resource.url)}">{esc(display_title(resource))}</a>'
        for resource in resources
    )


def resource_block(
    resource: Resource, index: int | None = None, *, now: datetime | None = None
) -> str:
    """Ein Listeneintrag: Titel als Link, Tags, Notiz, Quelle und Alter."""
    prefix = f"<code>{mark(index)}</code> " if index is not None else ""
    lines = [
        f"{prefix}<a href=\"{esc(resource.url)}\">{esc(display_title(resource))}</a>"
        f"  <code>#{resource.id}</code>"
    ]
    if resource.tags:
        lines.append(f"   Tags: {esc(format_tags(list(resource.tags)))}")
    if resource.notes:
        lines.append(f"   {html('note')} {esc(resource.notes)}")
    lines.append(
        f"   {source_label(resource.source)} | {esc(relative_age(resource.created_at, now=now))}"
    )
    return "\n".join(lines)


def resource_list(
    resources: list[Resource], *, start_index: int = 1, now: datetime | None = None
) -> str:
    return "\n\n".join(
        resource_block(resource, start_index + offset, now=now)
        for offset, resource in enumerate(resources)
    )


def page_footer(page_number: int, page_count: int, total: int, noun: str = "results") -> str:
    return f"{DIVIDER}\nPage {page_number} / {page_count} ({total} {noun})"


def pluralise(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural
