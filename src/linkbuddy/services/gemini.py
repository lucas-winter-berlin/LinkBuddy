"""Gemini-Anbindung fuer Tag-Vorschlaege.

Bewusst defensiv: faellt der Aufruf aus welchem Grund auch immer aus, liefert
der Tagger eine leere Liste und der Bot arbeitet nur mit Heuristiken weiter.

Bei einer noch kleinen Tagsammlung darf Gemini 1–2 neue Tags vorschlagen.
Sobald genug eigene Tags existieren, bleibt es bei bestehenden.
"""

from __future__ import annotations

import asyncio
import logging

from .tags import InvalidTagError, normalise_tag

logger = logging.getLogger(__name__)

# Unter dieser Anzahl bekannter Tags darf Gemini neue erfinden.
NEW_TAG_THRESHOLD = 12
MAX_NEW_TAGS = 2

PROMPT_EXISTING_ONLY = """Du bist ein Tag-Assistent fuer eine private Linksammlung.

Existierende Tags des Users:
{tag_list}

Neue Ressource:
- URL: {url}
- Titel: {title}

Regeln:
- Nutze AUSSCHLIESSLICH Tags aus der Liste oben.
- Erfinde keine neuen Tags und veraendere die Schreibweise nicht.
- Maximal {limit} Vorschlaege, lieber weniger.
- Schlage nur vor, was eindeutig passt.

Antworte in einer Zeile im Format: #tag1 #tag2
Wenn nichts eindeutig passt, antworte genau: (keine)
"""

PROMPT_ALLOW_NEW = """Du bist ein Tag-Assistent fuer eine private Linksammlung.
Die Sammlung ist noch klein – du darfst sparsam neue Tags vorschlagen.

Bereits vorhandene Tags:
{tag_list}

Neue Ressource:
- URL: {url}
- Titel: {title}

Regeln:
- Bevorzuge vorhandene Tags, wenn sie passen.
- Du darfst maximal {max_new} NEUE Tags erfinden.
- Neue Tags: kurz, klein geschrieben, Format #kategorie oder #kategorie/unter
  (nur Buchstaben, Ziffern, -, _; z.B. #ai/agents #tools #berlin/events).
- Maximal {limit} Vorschlaege insgesamt, lieber weniger.
- Keine Satzzeichen, keine Leerzeichen im Tag.

Antworte in einer Zeile im Format: #tag1 #tag2
Wenn nichts sinnvoll passt, antworte genau: (keine)
"""


class GeminiTagger:
    """Duenner Wrapper um google-genai. Der Client wird erst bei Bedarf gebaut."""

    def __init__(self, api_key: str, model: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # lokaler Import: nur noetig, wenn aktiviert

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def suggest(
        self,
        *,
        url: str,
        title: str | None,
        known_tags: list[str],
        limit: int = 3,
        allow_new: bool | None = None,
    ) -> list[str]:
        """Fragt Gemini nach Tags. Bei kleiner Sammlung auch neue erlaubt."""
        if allow_new is None:
            allow_new = len(known_tags) < NEW_TAG_THRESHOLD

        if not known_tags and not allow_new:
            return []

        tag_list = (
            ", ".join(f"#{t}" for t in known_tags)
            if known_tags
            else "(noch keine – schlage passende neue vor)"
        )
        template = PROMPT_ALLOW_NEW if allow_new else PROMPT_EXISTING_ONLY
        prompt = template.format(
            tag_list=tag_list,
            url=url,
            title=title or "(kein Titel)",
            limit=limit,
            max_new=MAX_NEW_TAGS,
        )

        try:
            from google.genai import types

            client = self._ensure_client()
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2 if allow_new else 0.0,
                        max_output_tokens=256,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                ),
                timeout=self._timeout,
            )
            text = (response.text or "").strip()
        except asyncio.TimeoutError:
            logger.warning("Gemini-Tagging abgebrochen (Timeout nach %.1fs)", self._timeout)
            return []
        except Exception as exc:
            logger.warning("Gemini-Tagging fehlgeschlagen: %s", exc)
            return []

        return parse_tag_response(
            text,
            known_tags=known_tags,
            limit=limit,
            allow_new=allow_new,
            max_new=MAX_NEW_TAGS,
        )


def parse_tag_response(
    text: str,
    *,
    known_tags: list[str],
    limit: int = 3,
    allow_new: bool = False,
    max_new: int = MAX_NEW_TAGS,
) -> list[str]:
    """Liest die Modell-Antwort.

    Bekannte Tags haben Vorrang. Neue Tags werden nur uebernommen, wenn
    ``allow_new`` gesetzt ist und das Kontingent ``max_new`` noch reicht.
    """
    if not text or "(keine" in text.lower():
        return []

    allowed = set(known_tags)
    existing: list[str] = []
    invented: list[str] = []

    for token in text.replace(",", " ").split():
        if not token.startswith("#"):
            continue
        try:
            tag = normalise_tag(token)
        except InvalidTagError:
            continue
        if tag in allowed:
            if tag not in existing:
                existing.append(tag)
        elif allow_new and tag not in invented and len(invented) < max_new:
            invented.append(tag)

    # Bekannte zuerst, dann neue – insgesamt auf limit kappen.
    result = existing + invented
    return result[:limit]
