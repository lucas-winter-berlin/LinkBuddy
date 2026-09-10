"""Textbausteine fuer die Telegram-Ausgabe (Parse-Mode HTML)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape as _html_escape

from ..icons import DIVIDER, html, mark
from ..db.models import Resource, ensure_utc
from .tags import format_tags
from .urls import source_label

MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

WEEKDAYS_DE = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]


def esc(value: object) -> str:
    """HTML-Escaping fuer alles, was in eine Telegram-Nachricht wandert."""
    return _html_escape(str(value if value is not None else ""), quote=False)


def number_emoji(index: int) -> str:
    """Kompatibilitaets-Alias fuer Listennummern."""
    return mark(index)


def relative_age(value: datetime, *, now: datetime | None = None) -> str:
    """Deutsche Altersangabe wie "vor 2 Stunden" oder "vor 3 Tagen"."""
    now = now or datetime.now(timezone.utc)
    delta = now - ensure_utc(value)
    seconds = int(delta.total_seconds())

    if seconds < 0:
        return "gerade eben"
    if seconds < 60:
        return "gerade eben"

    minutes = seconds // 60
    if minutes < 60:
        return f"vor {minutes} Min."

    hours = minutes // 60
    if hours < 24:
        return "vor 1 Stunde" if hours == 1 else f"vor {hours} Stunden"

    days = hours // 24
    if days < 7:
        return "vor 1 Tag" if days == 1 else f"vor {days} Tagen"

    weeks = days // 7
    if days < 31:
        return "vor 1 Woche" if weeks == 1 else f"vor {weeks} Wochen"

    months = days // 30
    if months < 12:
        return "vor 1 Monat" if months == 1 else f"vor {months} Monaten"

    years = days // 365
    return "vor 1 Jahr" if years == 1 else f"vor {years} Jahren"


def format_date(value: datetime, tz) -> str:
    """Datum in lokaler Zeitzone als TT.MM.JJJJ."""
    return ensure_utc(value).astimezone(tz).strftime("%d.%m.%Y")


def format_long_date(value: datetime, tz) -> str:
    """Datum als "23. Januar 2026"."""
    local = ensure_utc(value).astimezone(tz)
    return f"{local.day}. {MONTHS_DE[local.month - 1]} {local.year}"


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
        return "· keine Links"
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


def page_footer(page_number: int, page_count: int, total: int, noun: str = "Ergebnisse") -> str:
    return f"{DIVIDER}\nSeite {page_number} / {page_count} ({total} {noun})"


def pluralise(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural
