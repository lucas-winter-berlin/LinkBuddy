"""Auswertungen: /stats, /top_tags, /timeline, /related, /similar."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from telegram import Update

from ... import icons as ic
from ...services.formatting import (
    DIVIDER,
    esc,
    format_long_date,
    progress_bar,
    relative_age,
    resource_block,
)
from ...services.periods import (
    PERIOD_LABELS,
    parse_period,
    period_start,
    previous_window,
    trend_percent,
)
from ...services.tags import InvalidTagError, normalise_tag
from ...services.urls import source_label
from ..context import BotContextTypes, app_context, reply, user_id_of

logger = logging.getLogger(__name__)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def stats_command(update: Update, context: BotContextTypes) -> None:
    raw = " ".join(context.args or []).strip()
    if raw:
        try:
            tag = normalise_tag(raw)
        except InvalidTagError:
            await reply(update, "! Invalid tag format. Use: <code>#category/sub</code>")
            return
        await _tag_stats(update, context, tag)
        return
    await _overall_stats(update, context)


async def _overall_stats(update: Update, context: BotContextTypes) -> None:
    ctx = app_context(context)
    settings = ctx.settings
    user_id = user_id_of(update)
    tz = settings.timezone

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        total = await repo.count(user_id)
        if total == 0:
            await reply(update, "· No links saved yet. Send me the first one!")
            return

        week_start = period_start("woche", tz)
        month_start = period_start("monat", tz)
        this_week = await repo.count(user_id, since=week_start)
        this_month = await repo.count(user_id, since=month_start)

        prev_week = previous_window("woche", tz)
        prev_month = previous_window("monat", tz)
        last_week = await repo.count_between(user_id, *prev_week) if prev_week else 0
        last_month = await repo.count_between(user_id, *prev_month) if prev_month else 0

        tag_counts = await repo.tag_counts(user_id)
        by_source = await repo.count_by_source(user_id)
        oldest = await repo.oldest_created_at(user_id)

    week_trend = trend_percent(this_week, last_week)
    month_trend = trend_percent(this_month, last_month)

    lines = [
        f"<b>{ic.STATS} RESOURCE OVERVIEW</b>",
        DIVIDER,
        f"Total: <b>{total}</b> links",
        f"   This week: {this_week} new" + (f" ({week_trend})" if week_trend else ""),
        f"   This month: {this_month} new" + (f" ({month_trend})" if month_trend else ""),
        "",
    ]

    top = tag_counts.most_common(5)
    if top:
        lines.append(f"<b>{ic.TAG} Top Tags</b>")
        lines.append("   " + " | ".join(f"#{esc(tag)} ({cnt})" for tag, cnt in top))
        lines.append("")

    if by_source:
        lines.append(f"<b>{ic.CHART} By source</b>")
        width = max(len(source_label(src)) for src, _ in by_source)
        for src, cnt in by_source:
            share = cnt / total
            label = source_label(src).ljust(width)
            lines.append(f"   <code>{esc(label)}</code> {progress_bar(share)} {cnt} ({share:.0%})")
        lines.append("")

    if oldest:
        lines.append(f"Oldest link: {format_long_date(oldest, tz)}")
    lines.append(f"Next export: {_next_export_text(settings)}")
    lines.append(DIVIDER)

    await reply(update, "\n".join(lines))


async def _tag_stats(update: Update, context: BotContextTypes, tag: str) -> None:
    ctx = app_context(context)
    tz = ctx.settings.timezone
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        page = await repo.by_tag(user_id, tag, limit=1, offset=0)
        total = page.total
        if total == 0:
            await reply(update, f"· No links with <code>#{esc(tag)}</code>")
            return

        counts = await repo.tag_counts(user_id)
        week = await repo.count_tagged(user_id, tag, since=period_start("woche", tz))
        month = await repo.count_tagged(user_id, tag, since=period_start("monat", tz))

        prev = previous_window("woche", tz)
        last_week = (
            await repo.count_tagged(user_id, tag, since=prev[0], before=prev[1]) if prev else 0
        )

        newest = await repo.last_used(user_id, tag)

    subtags = sorted(
        ((t, c) for t, c in counts.items() if t.startswith(tag + "/")),
        key=lambda kv: (-kv[1], kv[0]),
    )

    lines = [f"<b>{ic.TAG} TAG: #{esc(tag)}</b> ({total} links)", DIVIDER]
    if subtags:
        lines.append("Subgroups:")
        lines += [f"  #{esc(sub)} ({cnt})" for sub, cnt in subtags]
        lines.append("")
    lines += [f"This week: {week} new", f"This month: {month} new"]
    if newest:
        lines.append(f"Last added: {relative_age(newest)}")

    trend = trend_percent(week, last_week)
    if trend:
        arrow = ic.TREND_UP if week >= last_week else ic.TREND_DOWN
        lines += ["", f"Trend: {arrow} {trend} vs. last week"]

    await reply(update, "\n".join(lines))


async def top_tags_command(update: Update, context: BotContextTypes) -> None:
    ctx = app_context(context)
    tz = ctx.settings.timezone
    user_id = user_id_of(update)

    period = parse_period(context.args[0] if context.args else None, default="all")
    since = period_start(period, tz)

    async with ctx.db.session() as session:
        counts = await ctx.repository(session).tag_counts(user_id, since=since)

    top = counts.most_common(10)
    if not top:
        await reply(update, f"· No tags {PERIOD_LABELS[period]}.")
        return

    lines = [f"<b>{ic.STATS} TOP 10 TAGS ({PERIOD_LABELS[period]})</b>", ""]
    highest = top[0][1]
    for index, (tag, count) in enumerate(top, start=1):
        bar = progress_bar(count / highest, width=8)
        lines.append(f"{index}. #{esc(tag)} {bar} {count}")
    await reply(update, "\n".join(lines))


async def timeline_command(update: Update, context: BotContextTypes) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)
    raw = " ".join(context.args or []).strip()
    if not raw:
        await reply(update, "Usage: <code>/timeline #ai</code>")
        return
    try:
        tag = normalise_tag(raw)
    except InvalidTagError:
        await reply(update, "! Invalid tag format. Use: <code>#category/sub</code>")
        return

    async with ctx.db.session() as session:
        buckets = await ctx.repository(session).timeline(user_id, tag, weeks=12)

    if not buckets:
        await reply(update, f"· No links with <code>#{esc(tag)}</code>")
        return

    highest = max(count for _, count in buckets)
    tz = ctx.settings.timezone
    lines = [f"<b>{ic.CHART} TIMELINE: #{esc(tag)}</b>", ""]
    for monday, count in buckets:
        local = monday.astimezone(tz)
        sunday = local + timedelta(days=6)
        label = f"W{local.isocalendar().week:02d} ({local:%d.%m}–{sunday:%d.%m})"
        bar = progress_bar(count / highest, width=10)
        noun = "link" if count == 1 else "links"
        lines.append(f"<code>{esc(label)}</code> {bar} {count} {noun}")
    await reply(update, "\n".join(lines))


async def related_command(update: Update, context: BotContextTypes) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)
    raw = " ".join(context.args or []).strip()
    if not raw:
        await reply(update, "Usage: <code>/related #ai/evals</code>")
        return
    try:
        tag = normalise_tag(raw)
    except InvalidTagError:
        await reply(update, "! Invalid tag format. Use: <code>#category/sub</code>")
        return

    async with ctx.db.session() as session:
        related = await ctx.repository(session).related_tags(user_id, tag)

    if not related:
        await reply(
            update,
            f"· <code>#{esc(tag)}</code> never co-occurs with other tags yet.",
        )
        return

    highest = related[0][1]
    lines = [f"<b>{ic.RELATED} TAGS THAT CO-OCCUR WITH #{esc(tag)}</b>", ""]
    for other, count in related[:10]:
        lines.append(f"#{esc(other)} ({count}x)  {progress_bar(count / highest, width=8)}")
    await reply(update, "\n".join(lines))


async def similar_command(update: Update, context: BotContextTypes) -> None:
    if not context.args:
        await reply(update, "Usage: <code>/similar &lt;link-ID&gt;</code>")
        return
    try:
        resource_id = int(context.args[0].lstrip("#"))
    except ValueError:
        await reply(update, "! Link ID must be a number, e.g. <code>/similar 5</code>")
        return
    await show_similar(update, context, resource_id)


async def show_similar(update: Update, context: BotContextTypes, resource_id: int) -> None:
    ctx = app_context(context)
    user_id = user_id_of(update)

    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        source = await repo.get(user_id, resource_id)
        if source is None:
            await reply(update, f"· No link with ID <code>{resource_id}</code>.")
            return
        matches = await repo.similar(user_id, source, limit=5)
        source_text = resource_block(source)

    if not matches:
        await reply(
            update,
            f"<b>{ic.RELATED} SIMILAR LINKS TO</b>\n\n{source_text}\n\n· Nothing comparable found.",
        )
        return

    lines = [f"<b>{ic.RELATED} SIMILAR LINKS TO</b>\n\n{source_text}", "", DIVIDER, ""]
    for index, (resource, shared) in enumerate(matches, start=1):
        lines.append(resource_block(resource, index))
        lines.append(f"   Shared: {esc(' '.join('#' + t for t in shared))}")
        lines.append("")
    await reply(update, "\n".join(lines).strip())


def _next_export_text(settings) -> str:
    """Naechster geplanter Weekly-Export in lokaler Zeit."""
    tz = settings.timezone
    now = datetime.now(timezone.utc).astimezone(tz)
    days_ahead = (settings.export_day - now.weekday()) % 7
    candidate = now.replace(
        hour=settings.export_time.hour,
        minute=settings.export_time.minute,
        second=0,
        microsecond=0,
    ) + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return f"{WEEKDAYS[settings.export_day]} {candidate:%d.%m.} at {candidate:%H:%M}"
