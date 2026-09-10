"""Verteilt freie Textnachrichten: Menü, Pending, neuer Link oder Hinweis."""

from __future__ import annotations

import logging

from telegram import Message, MessageEntity, Update

from ...services.urls import find_urls
from .. import keyboards as kb
from ..context import BotContextTypes, reply
from ..state import Pending, get_pending, set_pending
from . import common, manage, query, save, stats

logger = logging.getLogger(__name__)

HINT = (
    "🤔 Da war kein Link drin.\n\n"
    "Paste a URL (optional <code>#tags</code> + note), tap a bottom button, "
    "or use /help."
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
        if pending.kind == "menu_search" and not has_url:
            set_pending(context.user_data, None)
            await query.search_with_keyword(update, context, text)
            return
        if pending.kind == "menu_tag" and not has_url:
            set_pending(context.user_data, None)
            await _run_tag_query(update, context, text)
            return
        # Auf eine korrigierte URL warten wir explizit; ansonsten gewinnt ein
        # neuer Link gegenueber einer offenen Tag-/Notiz-Eingabe.
        if pending.kind == "draft_url" or not has_url:
            handler = _PENDING_HANDLERS.get(pending.kind)
            if handler is not None:
                await handler(update, context, pending.ref, text)
                return
        set_pending(context.user_data, None)

    if await _dispatch_menu_button(update, context, text):
        return

    if has_url:
        await save.handle_new_link(update, context, text)
        return

    await reply(update, HINT)


async def _dispatch_menu_button(
    update: Update, context: BotContextTypes, text: str
) -> bool:
    """Mappt Reply-Keyboard-Labels auf bestehende Handler. True = erledigt."""
    label = text.strip()
    if label == kb.BTN_LATEST:
        context.user_data["_menu_period_cmd"] = "latest"
        await query.period_command(update, context)
        return True
    if label == kb.BTN_TODAY:
        context.user_data["_menu_period_cmd"] = "today"
        await query.period_command(update, context)
        return True
    if label == kb.BTN_WEEK:
        context.user_data["_menu_period_cmd"] = "week"
        await query.period_command(update, context)
        return True
    if label == kb.BTN_MONTH:
        context.user_data["_menu_period_cmd"] = "month"
        await query.period_command(update, context)
        return True
    if label == kb.BTN_TAGS:
        await query.tags_command(update, context)
        return True
    if label == kb.BTN_STATS:
        await stats.stats_command(update, context)
        return True
    if label == kb.BTN_SEARCH:
        set_pending(context.user_data, Pending(kind="menu_search", ref=""))
        await reply(
            update,
            "🔍 Send a search keyword (or paste a link to save instead).",
        )
        return True
    if label == kb.BTN_EXPORT:
        await manage.export_command(update, context)
        return True
    if label == kb.BTN_HELP:
        await common.help_command(update, context)
        return True
    if label == kb.BTN_SETTINGS:
        await common.settings_command(update, context)
        return True
    return False


async def _run_tag_query(
    update: Update, context: BotContextTypes, raw: str
) -> None:
    from ...services.tags import InvalidTagError, normalise_tag

    try:
        tag = normalise_tag(raw)
    except InvalidTagError:
        await reply(update, "! Invalid tag. Use: <code>#category/sub</code>")
        return
    await query.show_tag(update, context, tag)
