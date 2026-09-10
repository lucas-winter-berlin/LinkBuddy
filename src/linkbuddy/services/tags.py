"""Normalisierung, Validierung und Darstellung von Tags."""

from __future__ import annotations

import re

# Tags werden intern ohne fuehrendes "#" und in Kleinschreibung gehalten:
# "ai/evals". Erlaubt sind Buchstaben (inkl. Umlaute), Ziffern, "-" und "_",
# hierarchisch mit "/" getrennt.
_SEGMENT = r"[\w-]+"
TAG_PATTERN = re.compile(rf"^{_SEGMENT}(?:/{_SEGMENT})*$", re.UNICODE)

# Findet #tags in freiem Text.
HASHTAG_PATTERN = re.compile(rf"#({_SEGMENT}(?:/{_SEGMENT})*)", re.UNICODE)

TAG_SEPARATOR = "|"


class InvalidTagError(ValueError):
    """Ein Tag entspricht nicht dem Format #kategorie/unter."""

    def __init__(self, raw: str) -> None:
        super().__init__(raw)
        self.raw = raw


def normalise_tag(raw: str) -> str:
    """Bringt ein Tag auf die interne Form. Wirft InvalidTagError bei Unsinn."""
    tag = raw.strip().lstrip("#").strip().lower()
    tag = tag.strip("/")
    tag = re.sub(r"/{2,}", "/", tag)
    tag = tag.replace(" ", "-")
    if not tag or not TAG_PATTERN.match(tag):
        raise InvalidTagError(raw)
    return tag


def parse_tags(raw: str) -> list[str]:
    """Liest Tags aus Freitext, egal ob "#a #b", "a, b" oder gemischt.

    Reihenfolge bleibt erhalten, Duplikate fallen weg.
    """
    if not raw or not raw.strip():
        return []
    candidates = [part for part in re.split(r"[,\s]+", raw.strip()) if part]
    result: list[str] = []
    for candidate in candidates:
        tag = normalise_tag(candidate)
        if tag not in result:
            result.append(tag)
    return result


def extract_hashtags(text: str) -> list[str]:
    """Zieht nur die #hashtags aus einer Nachricht, ohne uebrigen Text."""
    result: list[str] = []
    for match in HASHTAG_PATTERN.finditer(text or ""):
        try:
            tag = normalise_tag(match.group(1))
        except InvalidTagError:
            continue
        if tag not in result:
            result.append(tag)
    return result


def strip_hashtags(text: str) -> str:
    """Entfernt die #hashtags und laesst den Rest als Notiz uebrig."""
    return re.sub(r"\s{2,}", " ", HASHTAG_PATTERN.sub("", text or "")).strip()


def tags_to_text(tags: list[str]) -> str:
    """Baut das LIKE-taugliche Suchfeld: "|ai/agents|tools|"."""
    if not tags:
        return TAG_SEPARATOR * 2
    return TAG_SEPARATOR + TAG_SEPARATOR.join(tags) + TAG_SEPARATOR


def format_tag(tag: str) -> str:
    return f"#{tag}"


def format_tags(tags: list[str]) -> str:
    return " ".join(format_tag(t) for t in tags) if tags else "(keine)"


def tag_prefix_parts(tag: str) -> list[str]:
    """Alle Praefixe eines Tags: "ai/agents/x" -> ["ai", "ai/agents", "ai/agents/x"]."""
    segments = tag.split("/")
    return ["/".join(segments[: i + 1]) for i in range(len(segments))]


def matches_tag(tag: str, query: str) -> bool:
    """True, wenn `tag` das gesuchte Tag ist oder darunter liegt."""
    return tag == query or tag.startswith(query + "/")


def merge_tags(existing: list[str], new: list[str]) -> list[str]:
    """Vereinigt zwei Tag-Listen ohne Duplikate, Reihenfolge stabil."""
    merged = list(existing)
    for tag in new:
        if tag not in merged:
            merged.append(tag)
    return merged
