from linkbuddy.services.urls import (
    detect_source,
    find_urls,
    is_valid_url,
    normalise_url,
    url_hash,
)


def test_find_urls_with_www_and_punctuation():
    text = "Schau mal www.example.com/path und https://arxiv.org/abs/1."
    assert find_urls(text) == [
        "https://www.example.com/path",
        "https://arxiv.org/abs/1",
    ]


def test_is_valid_url():
    assert is_valid_url("https://example.com/x")
    assert not is_valid_url("ftp://example.com")
    assert not is_valid_url("notaurl")


def test_normalise_url_strips_tracking():
    raw = "HTTPS://WWW.Example.com/path/?utm_source=x&id=1&fbclid=abc#frag"
    assert normalise_url(raw) == "https://example.com/path?id=1"


def test_url_hash_stable_across_tracking():
    a = "https://example.com/a?utm_campaign=x"
    b = "https://www.example.com/a/"
    assert url_hash(a) == url_hash(b)


def test_detect_source():
    assert detect_source("https://arxiv.org/abs/1") == "paper"
    assert detect_source("https://github.com/x/y") == "code"
    assert detect_source("https://youtu.be/abc") == "video"
    assert detect_source("https://example.com") == "website"
