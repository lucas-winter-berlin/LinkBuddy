"""Konservatives Auto-Tagging.

Reihenfolge: Domain-Hinweise, Wort-Treffer in bestehenden Tags, haeufige
Co-Occurrences. Erst danach darf Gemini ergaenzen -- und auch dann nur mit
Tags, die der User schon benutzt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .gemini import GeminiTagger
from .tags import merge_tags

# Kuratierte Domain-Hinweise. Diese wenigen Tags darf der Bot auch dann
# vorschlagen, wenn der User sie noch nie vergeben hat -- sonst bleibt eine
# frische Sammlung ohne jeden Vorschlag.
DOMAIN_TAG_HINTS: dict[str, list[str]] = {
    "arxiv.org": ["ai/research"],
    "openreview.net": ["ai/research"],
    "biorxiv.org": ["research"],
    "github.com": ["tools"],
    "gitlab.com": ["tools"],
    "huggingface.co": ["ai/tools"],
    "pypi.org": ["tools"],
    "npmjs.com": ["tools"],
    "youtube.com": ["video"],
    "youtu.be": ["video"],
    "vimeo.com": ["video"],
    "instagram.com": ["inspiration"],
}

_WORD_SPLIT = re.compile(r"[^\wäöüß]+", re.UNICODE)

# Zu kurze Tag-Segmente ("ai", "ml") wuerden in URLs staendig zufaellig
# matchen, deshalb erst ab dieser Laenge auf Wortbasis vorschlagen.
MIN_WORD_MATCH_LENGTH = 4


@dataclass(frozen=True)
class TagSuggestion:
    """Vorschlaege plus die Info, ob Gemini beteiligt war."""

    tags: list[str]
    used_ai: bool = False


def _haystack(url: str, title: str | None) -> set[str]:
    """Wortmenge aus URL-Pfad und Titel."""
    parsed = urlparse(url)
    raw = f"{parsed.path} {parsed.query} {title or ''}".lower()
    return {word for word in _WORD_SPLIT.split(raw) if word}


def domain_hints(url: str) -> list[str]:
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    for domain_key, tags in DOMAIN_TAG_HINTS.items():
        if domain == domain_key or domain.endswith("." + domain_key):
            return list(tags)
    return []


def _related_words(left: str, right: str) -> bool:
    """True, wenn zwei Woerter denselben Stamm teilen (agents/agent, evals/evaluating)."""
    if left == right:
        return True
    if len(left) < MIN_WORD_MATCH_LENGTH or len(right) < MIN_WORD_MATCH_LENGTH:
        return False
    if left.startswith(right) or right.startswith(left):
        return True
    shared = 0
    for a, b in zip(left, right):
        if a != b:
            break
        shared += 1
    return shared >= MIN_WORD_MATCH_LENGTH


def word_matches(url: str, title: str | None, known_tags: list[str]) -> list[str]:
    """Bekannte Tags, deren letztes Segment als Wort in URL oder Titel steht."""
    words = _haystack(url, title)
    matches: list[str] = []
    for tag in known_tags:
        leaf = tag.split("/")[-1]
        if len(leaf) < MIN_WORD_MATCH_LENGTH:
            continue
        if any(_related_words(leaf, word) for word in words):
            matches.append(tag)
    return matches


def co_occurrence_boost(
    seeds: list[str], co_occurrences: dict[str, dict[str, int]], *, min_count: int = 2
) -> list[str]:
    """Tags, die haeufig zusammen mit den bereits gefundenen auftauchen."""
    scores: dict[str, int] = {}
    for seed in seeds:
        for other, count in (co_occurrences.get(seed) or {}).items():
            if other in seeds or count < min_count:
                continue
            scores[other] = scores.get(other, 0) + count
    return [tag for tag, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def heuristic_suggestions(
    *,
    url: str,
    title: str | None,
    known_tags: list[str],
    co_occurrences: dict[str, dict[str, int]] | None = None,
    limit: int = 3,
) -> list[str]:
    known_set = set(known_tags)
    suggestions: list[str] = []

    for tag in domain_hints(url):
        # Existiert schon ein Untertag (#ai/research statt #research), nimm den.
        if tag not in known_set:
            deeper = [k for k in known_tags if k.endswith("/" + tag.split("/")[-1])]
            if deeper:
                tag = deeper[0]
        if tag not in suggestions:
            suggestions.append(tag)

    for tag in word_matches(url, title, known_tags):
        if tag not in suggestions:
            suggestions.append(tag)

    if co_occurrences and len(suggestions) < limit:
        for tag in co_occurrence_boost(suggestions, co_occurrences):
            if tag not in suggestions:
                suggestions.append(tag)
            if len(suggestions) >= limit:
                break

    return suggestions[:limit]


async def suggest_tags(
    *,
    url: str,
    title: str | None,
    known_tags: list[str],
    co_occurrences: dict[str, dict[str, int]] | None = None,
    tagger: GeminiTagger | None = None,
    limit: int = 3,
) -> TagSuggestion:
    """Vorschlaege aus Heuristik und optional Gemini, auf `limit` begrenzt.

    Gemini wird auch bei leerer Tagsammlung gefragt und darf dann sparsam
    neue Tags erfinden. Heuristik-Treffer behalten Vorrang.
    """
    from .gemini import NEW_TAG_THRESHOLD

    suggestions = heuristic_suggestions(
        url=url,
        title=title,
        known_tags=known_tags,
        co_occurrences=co_occurrences,
        limit=limit,
    )

    if tagger is None:
        return TagSuggestion(tags=suggestions, used_ai=False)

    # Bei voller Heuristik und schon reicher Tagsammlung reicht die Heuristik.
    allow_new = len(known_tags) < NEW_TAG_THRESHOLD
    if len(suggestions) >= limit and not allow_new:
        return TagSuggestion(tags=suggestions, used_ai=False)

    ai_tags = await tagger.suggest(
        url=url,
        title=title,
        known_tags=known_tags,
        limit=limit,
        allow_new=allow_new,
    )
    if not ai_tags:
        return TagSuggestion(tags=suggestions, used_ai=False)

    return TagSuggestion(tags=merge_tags(suggestions, ai_tags)[:limit], used_ai=True)
