"""Verteilt freie Textnachrichten: erwartete Eingabe, neuer Link oder Hinweis."""

from __future__ import annotations

import logging

from telegram import Message, MessageEntity, Update

from ...services.urls import find_urls
from ..context import BotContextTypes, reply
from ..state import get_pending, set_pending
from . import manage, save

logger = logging.getLogger(__name__)

HINT = (
    "🤔 Da war kein Link drin.\n\n"
    "Schick mir eine URL (optional mit <code>#tags</code> und einer kurzen Notiz) "
    "oder nutze /help für alle Befehle."
)

_PENDING_HANDLERS = {
    "draft_tags": save.apply_draft_tags,
    "draft_note": save.apply_draft_note,
    "draft_url": save.apply_draft_url,
    "edit_tags": manage.apply_edit_tags,
    "edit_note": manage.apply_edit_note,
}


def message_text(message: Message) -> str:
    """Sichtbarer Text plus versteckte Ziel-URLs aus Hyperlinks."""
    parts: list[str] = []
    if message.text:
        parts.append(message.text)
    if message.caption:
        parts.append(message.caption)

    for entity in list(message.entities or ()) + list(message.caption_entities or ()):
        if entity.type == MessageEntity.TEXT_LINK and entity.url:
            parts.append(entity.url)

    return "\n".join(parts).strip()


async def text_router(update: Update, context: BotContextTypes) -> None:
    message = update.effective_message
    if message is None:  # pragma: no cover
        return

    text = message_text(message)
    pending = get_pending(context.user_data)
    has_url = bool(find_urls(text))

    if pending is not None:
        # Auf eine korrigierte URL warten wir explizit; ansonsten gewinnt ein
        # neuer Link gegenueber einer offenen Tag-/Notiz-Eingabe.
        if pending.kind == "draft_url" or not has_url:
            handler = _PENDING_HANDLERS.get(pending.kind)
            if handler is not None:
                await handler(update, context, pending.ref, text)
                return
        set_pending(context.user_data, None)

    if has_url:
        await save.handle_new_link(update, context, text)
        return

    await reply(update, HINT)
