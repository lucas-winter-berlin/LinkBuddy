"""Export der Sammlung als JSON, Markdown, CSV oder Notion-CSV."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ..db.models import Resource, ensure_utc
from .tags import format_tag

FORMATS = ("json", "markdown", "csv", "notion")
FORMAT_ALIASES = {
    "md": "markdown",
    "markdown": "markdown",
    "json": "json",
    "csv": "csv",
    "notion": "notion",
}

EXTENSIONS = {"json": "json", "markdown": "md", "csv": "csv", "notion": "csv"}


@dataclass(frozen=True)
class ExportFile:
    """Fertige Exportdatei im Speicher."""

    filename: str
    content: bytes

    @property
    def size_kb(self) -> float:
        return len(self.content) / 1024


def parse_format(value: str | None) -> str | None:
    """Normalisiert eine Formatangabe, None wenn sie unbekannt ist."""
    if not value:
        return None
    return FORMAT_ALIASES.get(value.strip().lower())


def build_export(
    resources: list[Resource],
    *,
    fmt: str = "json",
    tag_filter: str | None = None,
    today: date | None = None,
    filename: str | None = None,
) -> ExportFile:
    """Baut die Exportdatei im gewuenschten Format."""
    if fmt not in FORMATS:
        raise ValueError(f"Unbekanntes Format: {fmt}")

    builders = {
        "json": _build_json,
        "markdown": _build_markdown,
        "csv": _build_csv,
        "notion": _build_notion_csv,
    }
    content = builders[fmt](resources, tag_filter)
    name = filename or f"linkbuddy_export_{today or date.today()}.{EXTENSIONS[fmt]}"
    return ExportFile(filename=name, content=content.encode("utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_json(resources: list[Resource], tag_filter: str | None) -> str:
    payload = {
        "export_date": _now_iso(),
        "tag_filter": format_tag(tag_filter) if tag_filter else None,
        "count": len(resources),
        "resources": [r.to_dict() for r in resources],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_markdown(resources: list[Resource], tag_filter: str | None) -> str:
    heading = f"# Ressourcen Export – {format_tag(tag_filter)}" if tag_filter else (
        "# Ressourcen Export"
    )
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    lines = [heading, "", f"Export: {today} | {len(resources)} Links", ""]

    grouped: dict[str, list[Resource]] = defaultdict(list)
    for resource in resources:
        for tag in resource.tags or ["(ohne Tag)"]:
            grouped[tag].append(resource)

    for tag in sorted(grouped, key=lambda t: (-len(grouped[t]), t)):
        entries = grouped[tag]
        lines.append(f"## {format_tag(tag) if tag != '(ohne Tag)' else tag} ({len(entries)})")
        for resource in entries:
            title = resource.title or resource.url
            line = f"- [{_md_escape(title)}]({resource.url})"
            if resource.notes:
                line += f" – {_md_escape(resource.notes)}"
            lines.append(line)
        lines.append("")

    lines.extend(["---", "*Exportiert von LinkBuddy*"])
    return "\n".join(lines)


def _md_escape(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def _build_csv(resources: list[Resource], tag_filter: str | None) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ID", "URL", "Title", "Tags", "Notes", "Source", "Created"])
    for resource in resources:
        writer.writerow(
            [
                resource.id,
                resource.url,
                resource.title or "",
                ",".join(resource.tags or []),
                resource.notes or "",
                resource.source,
                ensure_utc(resource.created_at).date().isoformat(),
            ]
        )
    return buffer.getvalue()


def _build_notion_csv(resources: list[Resource], tag_filter: str | None) -> str:
    """CSV mit Spaltennamen, die Notion direkt als Datenbank importiert."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Name", "URL", "Tags", "Notes", "Source", "Created"])
    for resource in resources:
        writer.writerow(
            [
                resource.title or resource.url,
                resource.url,
                ", ".join(resource.tags or []),
                resource.notes or "",
                resource.source,
                ensure_utc(resource.created_at).date().isoformat(),
            ]
        )
    return buffer.getvalue()
