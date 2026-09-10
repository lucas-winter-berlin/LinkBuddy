"""Kurzlebiger Zustand pro User.

Telegram erlaubt nur 64 Byte callback_data. Statt Suchbegriffe oder Entwuerfe
in die Buttons zu packen, liegen sie hier unter einem kurzen Token, das in der
callback_data steht. Der Zustand lebt im Arbeitsspeicher und ist nach einem
Neustart weg -- fuer laufende Dialoge ist das akzeptabel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Literal, MutableMapping

_token_counter = count(1)

# Aeltere Eintraege werden verworfen, damit user_data nicht unbegrenzt waechst.
MAX_ENTRIES = 40


def new_token() -> str:
    """Kompaktes, aufsteigendes Token in Base36."""
    value = next(_token_counter)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while value:
        value, rest = divmod(value, 36)
        out = digits[rest] + out
    return out or "0"


@dataclass
class Draft:
    """Ein Link, der gerade gespeichert werden soll."""

    url: str
    url_hash: str
    source: str
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    suggested_tags: list[str] = field(default_factory=list)
    user_tags: list[str] = field(default_factory=list)
    ai_used: bool = False
    broken_reason: str | None = None
    force_save: bool = False
    duplicate_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None


@dataclass
class ListView:
    """Merkt sich eine Ergebnisliste, damit Blaettern ohne Neu-Parsen geht."""

    kind: Literal["search", "tag", "period"]
    argument: str
    offset: int = 0
    title: str = ""
    page_size: int | None = None


@dataclass
class Pending:
    """Worauf der Bot gerade eine Texteingabe erwartet."""

    kind: Literal["draft_tags", "draft_note", "draft_url", "edit_tags", "edit_note"]
    ref: str


def _bucket(user_data: MutableMapping[str, Any], name: str) -> dict[str, Any]:
    bucket = user_data.get(name)
    if not isinstance(bucket, dict):
        bucket = {}
        user_data[name] = bucket
    return bucket


def _store(user_data: MutableMapping[str, Any], name: str, value: Any) -> str:
    bucket = _bucket(user_data, name)
    token = new_token()
    bucket[token] = value
    while len(bucket) > MAX_ENTRIES:
        bucket.pop(next(iter(bucket)))
    return token


def put_draft(user_data: MutableMapping[str, Any], draft: Draft) -> str:
    return _store(user_data, "drafts", draft)


def get_draft(user_data: MutableMapping[str, Any], token: str) -> Draft | None:
    value = _bucket(user_data, "drafts").get(token)
    return value if isinstance(value, Draft) else None


def drop_draft(user_data: MutableMapping[str, Any], token: str) -> None:
    _bucket(user_data, "drafts").pop(token, None)


def put_view(user_data: MutableMapping[str, Any], view: ListView) -> str:
    return _store(user_data, "views", view)


def get_view(user_data: MutableMapping[str, Any], token: str) -> ListView | None:
    value = _bucket(user_data, "views").get(token)
    return value if isinstance(value, ListView) else None


def set_pending(user_data: MutableMapping[str, Any], pending: Pending | None) -> None:
    if pending is None:
        user_data.pop("pending", None)
    else:
        user_data["pending"] = pending


def get_pending(user_data: MutableMapping[str, Any]) -> Pending | None:
    value = user_data.get("pending")
    return value if isinstance(value, Pending) else None
