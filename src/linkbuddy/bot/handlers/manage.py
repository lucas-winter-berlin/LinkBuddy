"""Verwaltung: /edit, /delete, /export und die zugehoerigen Callbacks."""

from __future__ import annotations

import logging
from io import BytesIO

from telegram import Update

from ...services.export import FORMATS, build_export, parse_format
from ...services.formatting import esc, format_date, resource_block
from ...services.tags import (
    InvalidTagError,
    format_tags,
    normalise_tag,
    parse_tags,
)
from .. import keyboards
from ..context import BotContextTypes, app_context, edit, reply, user_id_of
from ..state import Pending, set_pending
from .stats import show_similar

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# /edit
# ----------------------------------------------------------------------


async def edit_command(update: Update, context: BotContextTypes) -> None:
    resource_id = _parse_id(context.args)
    if resource_id is None:
        await reply(update, "Usage: <code>/edit &lt;link-ID&gt;</code>")
        return
    await _show_edit_menu(update, context, resource_id)


async def _show_edit_menu(update: Update, context: BotContextTypes, resource_id: int) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        resource = await ctx.repository(session).get(user_id, resource_id)
        if resource is None:
            await reply(update, f"😕 No link with ID <code>{resource_id}</code>.")
            return
        text = (
            f"<b>✏️ Edit link #{resource.id}</b>\n\n"
            f"<a href=\"{esc(resource.url)}\">{esc(resource.title or resource.url)}</a>\n\n"
            f"Tags: {esc(format_tags(list(resource.tags or [])))}\n"
            f"Note: {esc(resource.notes) if resource.notes else '(none)'}"
        )

    markup = keyboards.edit_menu(resource_id)
    if update.callback_query is not None:
        await edit(update, text, reply_markup=markup)
    else:
        await reply(update, text, reply_markup=markup)


async def apply_edit_tags(
    update: Update, context: BotContextTypes, ref: str, text: str
) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)
    resource_id = int(ref)

    if text.strip() == "-":
        tags: list[str] = []
    else:
        try:
            tags = parse_tags(text)
        except InvalidTagError as exc:
            await reply(
                update,
                f"⚠️ Invalid tag format: <code>{esc(exc.raw)}</code>\nUse: #category/sub",
            )
            return
        if len(tags) > ctx.settings.max_tags_per_link:
            await reply(
                update, f"⚠️ Max. {ctx.settings.max_tags_per_link} tags per link. Remove some."
            )
            return

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        resource = await repo.get(user_id, resource_id)
        if resource is None:
            set_pending(context.user_data, None)
            await reply(update, "😕 That link no longer exists.")
            return
        await repo.update_content(resource, tags=tags)
        text_out = "✅ Tags updated.\n\n" + resource_block(resource)
        markup = keyboards.saved_actions(resource.id, resource.url)

    set_pending(context.user_data, None)
    await reply(update, text_out, reply_markup=markup)


async def apply_edit_note(
    update: Update, context: BotContextTypes, ref: str, text: str
) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)
    resource_id = int(ref)
    note = "" if text.strip() == "-" else text.strip()[: ctx.settings.max_note_length]

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        resource = await repo.get(user_id, resource_id)
        if resource is None:
            set_pending(context.user_data, None)
            await reply(update, "😕 That link no longer exists.")
            return
        await repo.update_content(resource, notes=note)
        text_out = "✅ Note updated.\n\n" + resource_block(resource)
        markup = keyboards.saved_actions(resource.id, resource.url)

    set_pending(context.user_data, None)
    await reply(update, text_out, reply_markup=markup)


# ----------------------------------------------------------------------
# /delete
# ----------------------------------------------------------------------


async def delete_command(update: Update, context: BotContextTypes) -> None:
    resource_id = _parse_id(context.args)
    if resource_id is None:
        await reply(update, "Usage: <code>/delete &lt;link-ID&gt;</code>")
        return
    await _ask_delete(update, context, resource_id)


async def _ask_delete(update: Update, context: BotContextTypes, resource_id: int) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        resource = await ctx.repository(session).get(user_id, resource_id)
        if resource is None:
            await reply(update, f"😕 No link with ID <code>{resource_id}</code>.")
            return
        text = (
            "<b>❌ Confirm delete?</b>\n\n"
            f"<a href=\"{esc(resource.url)}\">{esc(resource.title or resource.url)}</a>\n"
            f"Tags: {esc(format_tags(list(resource.tags or [])))}\n"
            f"Saved: {format_date(resource.created_at, ctx.settings.timezone)}\n\n"
            "The link will no longer appear in search or stats."
        )

    markup = keyboards.delete_confirm(resource_id)
    if update.callback_query is not None:
        await edit(update, text, reply_markup=markup)
    else:
        await reply(update, text, reply_markup=markup)


# ----------------------------------------------------------------------
# Callbacks rund um eine einzelne Ressource
# ----------------------------------------------------------------------


async def resource_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, action, raw_id = query.data.split(":", 2)
    resource_id = int(raw_id)
    ctx = app_context(context)
    user_id = user_id_of(update)

    if action == "edit":
        await query.answer()
        await _show_edit_menu(update, context, resource_id)
        return

    if action == "edittags":
        set_pending(context.user_data, Pending(kind="edit_tags", ref=str(resource_id)))
        await query.answer()
        await edit(
            update,
            "✏️ Send me the new tags (comma- or #-separated).\n"
            "Use <code>-</code> to clear all tags.",
        )
        return

    if action == "editnote":
        set_pending(context.user_data, Pending(kind="edit_note", ref=str(resource_id)))
        await query.answer()
        await edit(
            update,
            "📝 Send me the new note.\nUse <code>-</code> to clear it.",
        )
        return

    if action == "done":
        set_pending(context.user_data, None)
        await query.answer("Done")
        async with ctx.db.session() as session:
            resource = await ctx.repository(session).get(user_id, resource_id)
        if resource is None:
            await edit(update, "😕 That link no longer exists.")
            return
        await edit(
            update,
            resource_block(resource),
            reply_markup=keyboards.saved_actions(resource.id, resource.url),
        )
        return

    if action == "similar":
        await query.answer()
        await show_similar(update, context, resource_id)
        return

    if action == "del":
        await query.answer()
        await _ask_delete(update, context, resource_id)
        return

    if action == "delno":
        await query.answer("Cancelled")
        await edit(update, "👍 Nothing deleted.")
        return

    if action == "delyes":
        await query.answer("Deleting …")
        async with ctx.db.session() as session:
            repo = ctx.repository(session)
            resource = await repo.get(user_id, resource_id)
            if resource is None:
                await edit(update, "😕 That link no longer exists.")
                return
            await repo.soft_delete(resource)
        await edit(update, f"✅ Link <code>#{resource_id}</code> deleted.")


# ----------------------------------------------------------------------
# /export
# ----------------------------------------------------------------------


async def export_command(update: Update, context: BotContextTypes) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)

    tag: str | None = None
    fmt = "json"
    for arg in context.args or []:
        parsed_format = parse_format(arg)
        if parsed_format:
            fmt = parsed_format
            continue
        try:
            tag = normalise_tag(arg)
        except InvalidTagError:
            await reply(
                update,
                "Usage: <code>/export [#tag] [format]</code>\n"
                f"Formats: {', '.join(FORMATS)}",
            )
            return

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        resources = await repo.list_for_export(user_id, tag=tag)

    if not resources:
        await reply(update, "😕 Nothing to export.")
        return

    export = build_export(resources, fmt=fmt, tag_filter=tag)
    caption = (
        f"💾 Export created\n"
        f"Format: {fmt} | Links: {len(resources)} | {export.size_kb:.1f} KB"
        + (f"\nFilter: #{tag}" if tag else "")
    )

    message = update.effective_message
    if message is None:  # pragma: no cover
        return
    await message.reply_document(
        document=BytesIO(export.content), filename=export.filename, caption=caption
    )

    async with ctx.db.session() as session:
        await ctx.repository(session).log_export(
            user_id, link_count=len(resources), file_path=export.filename, status="sent"
        )


def _parse_id(args: list[str] | None) -> int | None:
    if not args:
        return None
    try:
        return int(args[0].lstrip("#"))
    except ValueError:
        return None
