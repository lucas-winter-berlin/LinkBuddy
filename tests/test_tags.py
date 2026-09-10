from linkbuddy.services.tags import (
    InvalidTagError,
    extract_hashtags,
    format_tags,
    matches_tag,
    merge_tags,
    normalise_tag,
    parse_tags,
    strip_hashtags,
    tags_to_text,
)
import pytest


def test_normalise_tag_strips_hash_and_case():
    assert normalise_tag("#AI/Evals") == "ai/evals"


def test_normalise_tag_rejects_garbage():
    with pytest.raises(InvalidTagError):
        normalise_tag("!!!")


def test_parse_tags_mixed_separators():
    assert parse_tags("#ai/agents, tools berlin/food") == [
        "ai/agents",
        "tools",
        "berlin/food",
    ]


def test_extract_and_strip_hashtags():
    text = "https://x.test #ai/agents Gutes Paper! #tools"
    assert extract_hashtags(text) == ["ai/agents", "tools"]
    assert strip_hashtags(text) == "https://x.test Gutes Paper!"


def test_tags_to_text_and_match():
    assert tags_to_text(["ai/agents", "tools"]) == "|ai/agents|tools|"
    assert matches_tag("ai/agents", "ai")
    assert matches_tag("ai/agents", "ai/agents")
    assert not matches_tag("tools", "ai")


def test_merge_and_format():
    assert merge_tags(["a", "b"], ["b", "c"]) == ["a", "b", "c"]
    assert format_tags(["ai"]) == "#ai"
    assert format_tags([]) == "(keine)"
