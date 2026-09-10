"""Der Speicher-Flow: Link erkennen, pruefen, taggen, bestaetigen, sichern."""

from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.constants import ParseMode

from ... import icons as ic
from ...db.models import Resource
from ...services import tagging
from ...services.formatting import (
    esc,
    format_date,
    relative_age,
    resource_block,
    shorten_url,
)
from ...services.tags import (
    InvalidTagError,
    extract_hashtags,
    format_tags,
    merge_tags,
    parse_tags,
    strip_hashtags,
)
from ...services.urls import (
    check_link,
    detect_source,
    extract_title,
    find_urls,
    is_valid_url,
    source_label,
    url_hash,
)
from .. import keyboards
from ..context import BotContextTypes, app_context, edit, reply, user_id_of
from ..state import Draft, Pending, drop_draft, get_draft, put_draft, set_pending

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Eingang: Nachricht mit Link
# ----------------------------------------------------------------------


async def handle_new_link(update: Update, context: BotContextTypes, text: str) -> None:
    """Verarbeitet eine Nachricht, in der mindestens eine URL steckt."""
    settings = app_context(context).settings
    urls = find_urls(text)
    url = urls[0]

    if not is_valid_url(url, max_length=settings.max_url_length):
        await reply(update, "! Invalid URL. Try again.")
        return

    # Tags und Notiz stehen im selben Text wie der Link.
    remainder = text.replace(url, " ", 1)
    user_tags = extract_hashtags(remainder)
    note = _clean_note(strip_hashtags(remainder), settings.max_note_length)

    status = await reply(update, f"{ic.WAIT} Checking link …")
    if status is None:  # pragma: no cover
        return

    draft = Draft(
        url=url,
        url_hash=url_hash(url),
        source=detect_source(url),
        tags=list(user_tags),
        user_tags=list(user_tags),
        notes=note,
        chat_id=status.chat_id,
        message_id=status.message_id,
    )

    if len(urls) > 1:
        await status.reply_text(
            f"◦ Found {len(urls)} links – saving the first one. "
            "Send the others one by one.",
        )

    await _advance_draft(update, context, draft, status)


async def _advance_draft(
    update: Update, context: BotContextTypes, draft: Draft, status: Message
) -> None:
    """Duplikat pruefen, sonst Erreichbarkeit pruefen, sonst Bestaetigung zeigen."""
    ctx = app_context(context)
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        duplicate = await repo.find_duplicate(user_id, draft.url_hash)

    if duplicate is not None and not draft.force_save:
        draft.duplicate_id = duplicate.id
        token = put_draft(context.user_data, draft)
        await status.edit_text(
            _render_duplicate(duplicate, draft, ctx.settings.timezone),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=keyboards.duplicate(token),
        )
        return

    if not draft.force_save:
        check = await check_link(draft.url, timeout=ctx.settings.http_timeout)
        if not check.reachable:
            draft.broken_reason = check.message
            token = put_draft(context.user_data, draft)
            await status.edit_text(
                f"{esc(check.message)}\n\n<code>{esc(shorten_url(draft.url, max_length=90))}</code>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=keyboards.broken_link(token),
            )
            return

    await _prepare_confirmation(update, context, draft, status)


async def _prepare_confirmation(
    update: Update, context: BotContextTypes, draft: Draft, status: Message
) -> None:
    """Titel holen, Tags vorschlagen und die Bestaetigungskarte anzeigen."""
    ctx = app_context(context)
    settings = ctx.settings
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        known_tags = await repo.known_tags(user_id)
        co_occurrences = await repo.all_co_occurrences(user_id)

    draft.title = await extract_title(draft.url, timeout=settings.http_timeout)

    suggestion = await tagging.suggest_tags(
        url=draft.url,
        title=draft.title,
        known_tags=known_tags,
        co_occurrences=co_occurrences,
        tagger=ctx.tagger,
        limit=settings.tag_suggestion_limit,
    )
    draft.suggested_tags = suggestion.tags
    draft.ai_used = suggestion.used_ai
    # Vom User getippte Tags haben Vorrang, Vorschlaege ergaenzen.
    draft.tags = merge_tags(draft.user_tags, suggestion.tags)[: settings.max_tags_per_link]

    token = put_draft(context.user_data, draft)
    await status.edit_text(
        _render_confirmation(draft),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=keyboards.confirm_save(token),
    )


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------


def _render_confirmation(draft: Draft) -> str:
    label = source_label(draft.source)
    headline = draft.title or shorten_url(draft.url)
    lines = [
        f"{label} detected: <b>{esc(headline)}</b>",
        f"<a href=\"{esc(draft.url)}\">{esc(shorten_url(draft.url, max_length=70))}</a>",
        "",
        f"Tags: {esc(format_tags(draft.tags))}",
        f"Note: {esc(draft.notes) if draft.notes else '(none)'}",
    ]
    if draft.broken_reason:
        lines += ["", f"! Note: {esc(draft.broken_reason)}"]
    if draft.suggested_tags:
        origin = "Gemini + heuristic" if draft.ai_used else "heuristic"
        lines += ["", f"<i>Tag suggestion via {origin}</i>"]
    return "\n".join(lines)


def _render_duplicate(original: Resource, draft: Draft, tz) -> str:
    lines = [
        "! <b>You've already saved this URL!</b>",
        "",
        f"Original from: {format_date(original.created_at, tz)} "
        f"({relative_age(original.created_at)})",
        f"   Tags: {esc(format_tags(list(original.tags or [])))}",
        f"   Note: {esc(original.notes) if original.notes else '(none)'}",
        "",
        f"New tags: {esc(format_tags(draft.user_tags))}",
        f"New note: {esc(draft.notes) if draft.notes else '(none)'}",
    ]
    return "\n".join(lines)


def _render_saved(resource: Resource) -> str:
    return "\n".join(
        [
            "✓ <b>Saved!</b>",
            "",
            resource_block(resource),
        ]
    )


def _clean_note(raw: str, max_length: int) -> str | None:
    note = (raw or "").strip()
    if not note:
        return None
    return note[:max_length]


# ----------------------------------------------------------------------
# Callbacks der Bestaetigungskarte
# ----------------------------------------------------------------------


async def save_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, action, token = query.data.split(":", 2)
    draft = get_draft(context.user_data, token)

    if draft is None:
        await query.answer("This draft expired. Send the link again.", show_alert=True)
        return

    if action == "cancel":
        drop_draft(context.user_data, token)
        set_pending(context.user_data, None)
        await query.answer("Cancelled")
        await edit(update, "× Not saved.")
        return

    if action == "tags":
        set_pending(context.user_data, Pending(kind="draft_tags", ref=token))
        await query.answer()
        await edit(
            update,
            "✎ Send me the tags (comma- or #-separated):\n"
            f"<code>{esc(' '.join('#' + t for t in draft.tags))}</code>\n\n"
            "Use <code>-</code> to clear all tags.",
        )
        return

    if action == "note":
        set_pending(context.user_data, Pending(kind="draft_note", ref=token))
        await query.answer()
        await edit(
            update,
            "≡ Send me the note (one sentence).\n"
            "Use <code>-</code> to clear it.",
        )
        return

    if action == "ok":
        await query.answer("Saving …")
        await _persist_draft(update, context, draft, token)


async def broken_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, action, token = query.data.split(":", 2)
    draft = get_draft(context.user_data, token)

    if draft is None:
        await query.answer("This draft expired.", show_alert=True)
        return

    if action == "cancel":
        drop_draft(context.user_data, token)
        await query.answer("Cancelled")
        await edit(update, "× Not saved.")
        return

    if action == "edit":
        set_pending(context.user_data, Pending(kind="draft_url", ref=token))
        await query.answer()
        await edit(update, "✎ Send me the corrected URL.")
        return

    if action == "save":
        draft.force_save = True
        await query.answer()
        message = query.message
        if message is None:  # pragma: no cover
            return
        await message.edit_text(f"{ic.WAIT} Fetching title …")
        await _prepare_confirmation(update, context, draft, message)


async def duplicate_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, action, token = query.data.split(":", 2)
    draft = get_draft(context.user_data, token)
    ctx = app_context(context)
    user_id = user_id_of(update)

    if draft is None:
        await query.answer("This draft expired.", show_alert=True)
        return

    if action == "cancel":
        drop_draft(context.user_data, token)
        await query.answer("Cancelled")
        await edit(update, "× Nothing saved.")
        return

    if action == "merge":
        await query.answer("Updating …")
        async with ctx.db.session() as session:
            repo = ctx.repository(session)
            original = await repo.get(user_id, draft.duplicate_id or 0)
            if original is None:
                await edit(update, "· The original no longer exists.")
                return
            merged = merge_tags(list(original.tags or []), draft.user_tags)
            merged = merged[: ctx.settings.max_tags_per_link]
            await repo.update_content(
                original,
                tags=merged,
                notes=draft.notes if draft.notes else None,
            )
            text = "↻ <b>Original updated!</b>\n\n" + resource_block(original)
        drop_draft(context.user_data, token)
        await edit(update, text, reply_markup=keyboards.saved_actions(original.id, original.url))
        return

    if action == "copy":
        draft.force_save = True
        await query.answer()
        message = query.message
        if message is None:  # pragma: no cover
            return
        await message.edit_text(f"{ic.WAIT} Fetching title …")
        await _prepare_confirmation(update, context, draft, message)


# ----------------------------------------------------------------------
# Texteingaben, die zu einem Entwurf gehoeren
# ----------------------------------------------------------------------


async def apply_draft_tags(update: Update, context: BotContextTypes, token: str, text: str) -> None:
    ctx = app_context(context)
    draft = get_draft(context.user_data, token)
    if draft is None:
        set_pending(context.user_data, None)
        await reply(update, "· This draft expired. Send the link again.")
        return

    if text.strip() == "-":
        tags: list[str] = []
    else:
        try:
            tags = parse_tags(text)
        except InvalidTagError as exc:
            await reply(
                update,
                f"! Invalid tag format: <code>{esc(exc.raw)}</code>\nUse: #category/sub",
            )
            return
        if len(tags) > ctx.settings.max_tags_per_link:
            await reply(
                update,
                f"! Max. {ctx.settings.max_tags_per_link} tags per link. Remove some.",
            )
            return

    draft.tags = tags
    draft.user_tags = tags
    set_pending(context.user_data, None)
    await reply(
        update,
        _render_confirmation(draft),
        reply_markup=keyboards.confirm_save(token),
    )


async def apply_draft_note(update: Update, context: BotContextTypes, token: str, text: str) -> None:
    ctx = app_context(context)
    draft = get_draft(context.user_data, token)
    if draft is None:
        set_pending(context.user_data, None)
        await reply(update, "· This draft expired. Send the link again.")
        return

    draft.notes = None if text.strip() == "-" else _clean_note(text, ctx.settings.max_note_length)
    set_pending(context.user_data, None)
    await reply(
        update,
        _render_confirmation(draft),
        reply_markup=keyboards.confirm_save(token),
    )


async def apply_draft_url(update: Update, context: BotContextTypes, token: str, text: str) -> None:
    ctx = app_context(context)
    draft = get_draft(context.user_data, token)
    if draft is None:
        set_pending(context.user_data, None)
        await reply(update, "· This draft expired. Send the link again.")
        return

    urls = find_urls(text)
    if not urls or not is_valid_url(urls[0], max_length=ctx.settings.max_url_length):
        await reply(update, "! That doesn't look like a valid URL. Try again?")
        return

    set_pending(context.user_data, None)
    drop_draft(context.user_data, token)

    draft.url = urls[0]
    draft.url_hash = url_hash(draft.url)
    draft.source = detect_source(draft.url)
    draft.force_save = False
    draft.broken_reason = None

    status = await reply(update, f"{ic.WAIT} Checking link …")
    if status is None:  # pragma: no cover
        return
    await _advance_draft(update, context, draft, status)


# ----------------------------------------------------------------------
# Persistieren
# ----------------------------------------------------------------------


async def _persist_draft(
    update: Update, context: BotContextTypes, draft: Draft, token: str
) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)

    meta: dict[str, object] = {}
    if draft.broken_reason:
        meta["broken"] = True
        meta["broken_reason"] = draft.broken_reason
    if draft.ai_used:
        meta["ai_tagged"] = True

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        resource = await repo.create(
            user_id=user_id,
            url=draft.url,
            url_hash=draft.url_hash,
            tags=draft.tags[: ctx.settings.max_tags_per_link],
            title=draft.title,
            notes=draft.notes,
            source=draft.source,
            meta=meta,
        )
        if draft.duplicate_id:
            await repo.link_duplicate(draft.duplicate_id, resource.id)
        text = _render_saved(resource)
        markup = keyboards.saved_actions(resource.id, resource.url)

    drop_draft(context.user_data, token)
    set_pending(context.user_data, None)
    await edit(update, text, reply_markup=markup)
