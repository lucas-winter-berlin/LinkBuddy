"""URL-Erkennung, Normalisierung, Quellen-Erkennung, Validierung, Titel."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)

# Zeichen, die am Satzende stehen und nicht mehr zur URL gehoeren.
_TRAILING_PUNCTUATION = ".,;:!?"

USER_AGENT = (
    "Mozilla/5.0 (compatible; LinkBuddyBot/1.0; +https://github.com/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Tracking-Parameter, die fuer die Identitaet einer URL irrelevant sind.
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref_src",
    "ref_url",
    "spm",
    "yclid",
}

SOURCE_BY_DOMAIN: dict[str, str] = {
    "instagram.com": "instagram",
    "arxiv.org": "paper",
    "biorxiv.org": "paper",
    "openreview.net": "paper",
    "pubmed.ncbi.nlm.nih.gov": "paper",
    "semanticscholar.org": "paper",
    "acm.org": "paper",
    "github.com": "code",
    "gitlab.com": "code",
    "huggingface.co": "code",
    "pypi.org": "code",
    "npmjs.com": "code",
    "youtube.com": "video",
    "youtu.be": "video",
    "vimeo.com": "video",
    "twitch.tv": "video",
    "tiktok.com": "video",
}

SOURCE_LABELS: dict[str, str] = {
    "instagram": "Instagram",
    "paper": "Paper",
    "code": "Code",
    "video": "Video",
    "website": "Website",
}

VALID_SOURCES = tuple(SOURCE_LABELS)


@dataclass(frozen=True)
class LinkCheck:
    """Ergebnis der Erreichbarkeitspruefung."""

    reachable: bool
    status_code: int | None = None
    message: str | None = None


def find_urls(text: str) -> list[str]:
    """Findet alle URLs in einer Nachricht, inklusive "www."-Kurzform."""
    found: list[str] = []
    for raw in URL_PATTERN.findall(text or ""):
        candidate = raw.rstrip(_TRAILING_PUNCTUATION)
        # Klammern am Ende nur abschneiden, wenn sie unbalanciert sind.
        while candidate.endswith(")") and candidate.count("(") < candidate.count(")"):
            candidate = candidate[:-1]
        if candidate.lower().startswith("www."):
            candidate = "https://" + candidate
        if candidate not in found:
            found.append(candidate)
    return found


def is_valid_url(url: str, *, max_length: int = 2048) -> bool:
    if not url or len(url) > max_length:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    return bool(parsed.netloc) and "." in parsed.netloc


def normalise_url(url: str) -> str:
    """Kanonische Form fuer den Duplikat-Vergleich.

    Schema und Host klein, "www." weg, Tracking-Parameter raus, Fragment raus,
    abschliessender Slash weg. Die Original-URL bleibt davon unberuehrt.
    """
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if (scheme == "http" and netloc.endswith(":80")) or (
        scheme == "https" and netloc.endswith(":443")
    ):
        netloc = netloc.rsplit(":", 1)[0]

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, parsed.params, urlencode(query), ""))


def url_hash(url: str) -> str:
    """SHA256 ueber die normalisierte URL."""
    return hashlib.sha256(normalise_url(url).encode("utf-8")).hexdigest()


def detect_source(url: str) -> str:
    """Leitet die Quelle aus der Domain ab, Default "website"."""
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    for domain_key, source in SOURCE_BY_DOMAIN.items():
        if domain == domain_key or domain.endswith("." + domain_key):
            return source
    return "website"


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, SOURCE_LABELS["website"])


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"},
    )


async def check_link(url: str, *, timeout: float = 5.0) -> LinkCheck:
    """Prueft, ob eine URL antwortet. HEAD zuerst, bei Ablehnung GET."""
    try:
        async with _client(timeout) as client:
            response = await client.head(url)
            if response.status_code in (403, 405, 501):
                response = await client.get(url)
            if response.status_code == 404:
                return LinkCheck(False, 404, "! Link not responding (404)")
            if response.status_code >= 400:
                return LinkCheck(
                    False,
                    response.status_code,
                    f"! Link returned an error ({response.status_code})",
                )
            return LinkCheck(True, response.status_code)
    except httpx.TimeoutException:
        return LinkCheck(False, None, "! Link not responding (timeout)")
    except httpx.HTTPError as exc:
        return LinkCheck(False, None, f"! URL unreachable: {type(exc).__name__}")


async def extract_title(url: str, *, timeout: float = 5.0, max_length: int = 100) -> str | None:
    """Holt og:title, sonst <title>, sonst <h1>. None wenn nichts brauchbar ist."""
    try:
        async with _client(timeout) as client:
            response = await client.get(url)
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return None
            soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return None

    for finder in (
        lambda: _meta_content(soup, "property", "og:title"),
        lambda: _meta_content(soup, "name", "twitter:title"),
        lambda: soup.title.string if soup.title and soup.title.string else None,
        lambda: soup.h1.get_text() if soup.h1 else None,
    ):
        try:
            value = finder()
        except Exception:
            value = None
        if value:
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned:
                return cleaned[:max_length]
    return None


def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str | None:
    tag = soup.find("meta", attrs={attr: value})
    if tag is None:
        return None
    content = tag.get("content")
    return content if isinstance(content, str) else None
