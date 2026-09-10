"""Gemeinsame Laufzeit-Objekte und kleine Helfer fuer alle Handler."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..config import Settings
from ..db import Database, ResourceRepository
from ..services.gemini import GeminiTagger

logger = logging.getLogger(__name__)

BotContextTypes = ContextTypes.DEFAULT_TYPE


@dataclass
class AppContext:
    """Alles, was Handler zur Laufzeit brauchen; liegt in ``bot_data``."""

    settings: Settings
    db: Database
    tagger: GeminiTagger | None

    def repository(self, session) -> ResourceRepository:
        return ResourceRepository(session)


def app_context(context: BotContextTypes) -> AppContext:
    ctx = context.application.bot_data.get("app_context")
    if not isinstance(ctx, AppContext):  # pragma: no cover - Programmierfehler
        raise RuntimeError("AppContext wurde nicht in bot_data hinterlegt.")
    return ctx


def is_authorised(update: Update, settings: Settings) -> bool:
    """Single-User-Bot: nur die konfigurierte Telegram-User-ID darf schreiben."""
    user = update.effective_user
    if user is None:
        return False
    if settings.owner_user_id is None:
        # Ohne OWNER_USER_ID laeuft der Bot offen -- nur fuer die Ersteinrichtung
        # gedacht, damit man ueberhaupt an die eigene User-ID kommt.
        return True
    return user.id == settings.owner_user_id


async def reply(update: Update, text: str, **kwargs: Any):
    """Antwort im HTML-Modus ohne Link-Vorschau."""
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    message = update.effective_message
    if message is None:  # pragma: no cover - bei Callback ohne Nachricht
        chat = update.effective_chat
        if chat is None:
            return None
        return await chat.send_message(text, **kwargs)
    return await message.reply_text(text, **kwargs)


async def edit(update: Update, text: str, **kwargs: Any):
    """Bearbeitet die Nachricht hinter einem Callback."""
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    query = update.callback_query
    if query is None or query.message is None:
        return await reply(update, text, **kwargs)
    return await query.edit_message_text(text, **kwargs)


def user_id_of(update: Update) -> int:
    user = update.effective_user
    if user is None:  # pragma: no cover
        raise RuntimeError("Update ohne User.")
    return user.id
