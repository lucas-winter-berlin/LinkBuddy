from linkbuddy.services.gemini import parse_tag_response
from linkbuddy.services.tagging import (
    co_occurrence_boost,
    domain_hints,
    heuristic_suggestions,
    suggest_tags,
    word_matches,
)
import pytest


def test_domain_hints_arxiv():
    assert "ai/research" in domain_hints("https://arxiv.org/abs/123")


def test_word_matches_existing_tags():
    matches = word_matches(
        "https://example.com/agent-framework",
        "Evaluating LLM Agents",
        ["ai/agents", "ai/evals", "berlin"],
    )
    assert "ai/agents" in matches
    assert "ai/evals" in matches


def test_heuristic_prefers_existing_deeper_tags():
    tags = heuristic_suggestions(
        url="https://arxiv.org/abs/agents",
        title="Evaluating LLM Agents",
        known_tags=["ai/research", "ai/agents", "ai/evals"],
        limit=3,
    )
    assert "ai/agents" in tags
    assert "ai/evals" in tags
    assert len(tags) <= 3


def test_co_occurrence_boost():
    boosted = co_occurrence_boost(
        ["ai/agents"],
        {"ai/agents": {"ai/evals": 5, "noise": 1}},
        min_count=2,
    )
    assert boosted == ["ai/evals"]


def test_parse_gemini_response_filters_unknown():
    known = ["ai/agents", "ai/evals"]
    assert parse_tag_response("#ai/agents #invented #ai/evals", known_tags=known) == [
        "ai/agents",
        "ai/evals",
    ]
    assert parse_tag_response("(keine Suggestions)", known_tags=known) == []


def test_parse_gemini_response_allows_new_when_enabled():
    known = ["ai/agents"]
    assert parse_tag_response(
        "#ai/agents #tools #skills #noise",
        known_tags=known,
        allow_new=True,
        max_new=2,
        limit=3,
    ) == ["ai/agents", "tools", "skills"]


def test_parse_gemini_response_allows_new_with_empty_known():
    assert parse_tag_response(
        "#ai/agents #tools",
        known_tags=[],
        allow_new=True,
        max_new=2,
    ) == ["ai/agents", "tools"]


@pytest.mark.asyncio
async def test_suggest_tags_without_gemini():
    suggestion = await suggest_tags(
        url="https://github.com/openai/agents",
        title="Agents Framework",
        known_tags=["tools", "ai/agents"],
        tagger=None,
        limit=3,
    )
    assert "tools" in suggestion.tags or "ai/agents" in suggestion.tags
    assert suggestion.used_ai is False
