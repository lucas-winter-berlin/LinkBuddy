"""Queries: /search, /tag, /tags, /latest, /today, /week, /month."""

from __future__ import annotations

import logging

from telegram import Update

from ... import icons as ic
from ...db.repository import Page, ResourceRepository
from ...services.formatting import (
    DIVIDER,
    esc,
    page_footer,
    resource_list,
    simple_link_list,
)
from ...services.periods import period_start
from ...services.tags import InvalidTagError, normalise_tag
from .. import keyboards
from ..context import BotContextTypes, app_context, edit, reply, user_id_of
from ..state import ListView, get_view, put_view

logger = logging.getLogger(__name__)

# Tag-Listen duerfen laenger sein als die Detail-Suche.
TAG_PAGE_SIZE = 30


def _period_title(period: str) -> str:
    return {
        "all": f"{ic.NEW} Letzte Links",
        "heute": f"{ic.WAIT} Heute gespeichert",
        "woche": f"{ic.WAIT} Letzte 7 Tage",
        "monat": f"{ic.WAIT} Letzte 30 Tage",
    }[period]


# ----------------------------------------------------------------------
# Gemeinsames Rendern einer Ergebnisseite
# ----------------------------------------------------------------------


async def _load_page(
    repo: ResourceRepository, user_id: int, view: ListView, *, page_size: int, tz
) -> Page:
    if view.kind == "search":
        return await repo.search(user_id, view.argument, limit=page_size, offset=view.offset)
    if view.kind == "tag":
        return await repo.by_tag(user_id, view.argument, limit=page_size, offset=view.offset)
    since = period_start(view.argument, tz)
    return await repo.by_period(user_id, since=since, limit=page_size, offset=view.offset)


def _render_page(view: ListView, page: Page, *, empty_hint: str) -> str:
    if page.total == 0:
        return empty_hint

    # Tag-Ansicht: schlicht "#tag" + Bullet-Liste
    if view.kind == "tag":
        header = f"<b>#{esc(view.argument)}</b>"
        body = simple_link_list(page.items)
        if page.page_count > 1:
            footer = page_footer(page.page_number, page.page_count, page.total, "Links")
            return f"{header}\n\n{body}\n\n{footer}"
        return f"{header}\n\n{body}"

    # title darf HTML (Custom Emoji) enthalten – nicht escapen
    header = f"<b>{view.title}</b>"
    body = resource_list(page.items, start_index=page.offset + 1)
    footer = page_footer(page.page_number, page.page_count, page.total, "Links")
    return f"{header}\n\n{body}\n\n{footer}"


async def _show_view(
    update: Update,
    context: BotContextTypes,
    view: ListView,
    *,
    empty_hint: str,
    token: str | None = None,
    page_size: int | None = None,
) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)
    size = page_size or view.page_size or ctx.settings.page_size
    view.page_size = size

    async with ctx.db.session() as session:
        page = await _load_page(
            ctx.repository(session), user_id, view, page_size=size, tz=ctx.settings.timezone
        )

    if token is None:
        token = put_view(context.user_data, view)

    text = _render_page(view, page, empty_hint=empty_hint)
    markup = keyboards.pagination(
        token, offset=page.offset, has_prev=page.has_prev, has_next=page.has_next
    )

    if update.callback_query is not None:
        await edit(update, text, reply_markup=markup)
    else:
        await reply(update, text, reply_markup=markup)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------


async def search_command(update: Update, context: BotContextTypes) -> None:
    keyword = " ".join(context.args or []).strip()
    if not keyword:
        await reply(update, "Usage: <code>/search &lt;keyword&gt;</code>")
        return

    view = ListView(
        kind="search",
        argument=keyword,
        title=f'{ic.SEARCH} Ergebnisse für "{esc(keyword)}"',
    )
    await _show_view(
        update,
        context,
        view,
        empty_hint=f'· Keine Links gefunden für "{esc(keyword)}"',
    )


async def tag_command(update: Update, context: BotContextTypes) -> None:
    raw = " ".join(context.args or []).strip()
    if not raw:
        await reply(update, "Nutzung: <code>/tag #kategorie</code> oder <code>/tags</code>")
        return
    try:
        tag = normalise_tag(raw)
    except InvalidTagError:
        await reply(update, "! Ungültiges Tag-Format. Nutze: <code>#kategorie/unter</code>")
        return
    await _show_tag(update, context, tag)


async def _show_tag(update: Update, context: BotContextTypes, tag: str) -> None:
    """Alle Links zu einem Tag als schlichte Bullet-Liste."""
    view = ListView(kind="tag", argument=tag, title=f"#{tag}")
    await _show_view(
        update,
        context,
        view,
        empty_hint=f"· Keine Links mit <code>#{esc(tag)}</code>",
        page_size=TAG_PAGE_SIZE,
    )


async def tags_command(update: Update, context: BotContextTypes) -> None:
    """Alle Tags mit ihren Links, gruppiert:

    #ai
    - Link 1
    - Link 2
    """
    ctx = app_context(context)
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        tree = await repo.tag_tree(user_id)
        if not tree:
            await reply(update, "· Noch keine Tags vergeben. Speichere den ersten Link!")
            return

        blocks: list[str] = []
        # Pro Wurzel-Tag eine Gruppe mit allen Links darunter
        for root in tree:
            resources = await repo.list_for_export(user_id, tag=root)
            if not resources:
                continue
            blocks.append(f"<b>#{esc(root)}</b>\n{simple_link_list(resources)}")

    if not blocks:
        await reply(update, "· Noch keine Tags vergeben.")
        return

    text = "\n\n".join(blocks)
    # Telegram-Limit ~4096 Zeichen
    if len(text) > 4000:
        text = text[:3900] + "\n\n… Liste gekürzt. Nutze /tag #name für Details."

    if update.callback_query is not None:
        await edit(update, text)
    else:
        await reply(update, text)


async def period_command(update: Update, context: BotContextTypes) -> None:
    """Handles /latest, /today, /week, /month (plus legacy German aliases)."""
    message = update.effective_message
    command = ""
    if message and message.text:
        command = message.text.split()[0].lstrip("/").split("@")[0].lower()

    period = {
        "latest": "all",
        "new": "all",
        "neue": "all",
        "today": "heute",
        "heute": "heute",
        "week": "woche",
        "woche": "woche",
        "month": "monat",
        "monat": "monat",
    }.get(command, "all")

    page_size = app_context(context).settings.page_size
    if period == "all" and context.args:
        try:
            requested = int(context.args[0])
            page_size = max(1, min(20, requested))
        except ValueError:
            await reply(update, "Usage: <code>/latest [count]</code>")
            return

    view = ListView(kind="period", argument=period, title=_period_title(period))
    empty = {
        "all": "· Noch keine Links gespeichert.",
        "heute": "· Heute noch nichts gespeichert.",
        "woche": "· In den letzten 7 Tagen nichts gespeichert.",
        "monat": "· In den letzten 30 Tagen nichts gespeichert.",
    }[period]

    await _show_view(update, context, view, empty_hint=empty, page_size=page_size)


# ----------------------------------------------------------------------
# Callbacks
# ----------------------------------------------------------------------


async def pagination_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, token, direction = query.data.split(":", 2)
    view = get_view(context.user_data, token)

    if view is None:
        await query.answer("Diese Liste ist abgelaufen. Bitte neu suchen.", show_alert=True)
        return

    size = view.page_size or app_context(context).settings.page_size
    view.offset = max(0, view.offset + (size if direction == "next" else -size))
    await query.answer()
    await _show_view(update, context, view, empty_hint="· Keine weiteren Links.", token=token)


async def tag_view_callback(update: Update, context: BotContextTypes) -> None:
    query = update.callback_query
    assert query is not None
    _, tag = query.data.split(":", 1)
    await query.answer()
    await _show_tag(update, context, tag)
