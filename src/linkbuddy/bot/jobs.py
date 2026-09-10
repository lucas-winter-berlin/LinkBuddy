"""Der automatische wöchentliche Export."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO

from telegram.ext import Application, ContextTypes

from .. import icons as ic
from ..services.export import build_export
from ..services.periods import period_start

logger = logging.getLogger(__name__)

WEEKLY_EXPORT_JOB = "weekly_export"


async def weekly_export(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Schickt die Links der letzten sieben Tage als JSON an den Besitzer."""
    from .context import AppContext

    ctx = context.application.bot_data.get("app_context")
    if not isinstance(ctx, AppContext):  # pragma: no cover
        logger.error("Weekly Export ohne AppContext abgebrochen")
        return

    user_id = ctx.settings.owner_user_id
    if user_id is None:
        logger.warning("Weekly Export übersprungen: OWNER_USER_ID ist nicht gesetzt")
        return

    since = period_start("woche", ctx.settings.timezone)
    async with ctx.db.session() as session:
        repo = ctx.repository(session)
        resources = await repo.list_for_export(
            user_id, since=since, limit=ctx.settings.export_chunk_size
        )
        total = await repo.count(user_id)

    if not resources:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{ic.EMPTY} Diese Woche keine neuen Links. Deine Sammlung: "
            f"{total} Links insgesamt.",
        )
        async with ctx.db.session() as session:
            await ctx.repository(session).log_export(
                user_id, link_count=0, file_path=None, status="sent"
            )
        return

    now = datetime.now(timezone.utc).astimezone(ctx.settings.timezone)
    week_label = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    export = build_export(
        resources, fmt="json", filename=f"linkbuddy_week_{week_label}.json"
    )

    status = "sent"
    try:
        await context.bot.send_document(
            chat_id=user_id,
            document=BytesIO(export.content),
            filename=export.filename,
            caption=(
                f"{ic.EXPORT} Deine Ressourcen dieser Woche\n"
                f"{len(resources)} neue Links | {total} insgesamt"
            ),
        )
    except Exception:
        status = "failed"
        logger.exception("Weekly Export konnte nicht gesendet werden")

    async with ctx.db.session() as session:
        await ctx.repository(session).log_export(
            user_id,
            link_count=len(resources),
            file_path=export.filename,
            status=status,
        )


def schedule_jobs(application: Application) -> None:
    """Registriert den Weekly-Export in der JobQueue."""
    from .context import AppContext

    ctx = application.bot_data.get("app_context")
    if not isinstance(ctx, AppContext):  # pragma: no cover
        raise RuntimeError("AppContext fehlt in bot_data.")

    job_queue = application.job_queue
    if job_queue is None:
        logger.warning(
            "Keine JobQueue verfügbar – installiere python-telegram-bot[job-queue]. "
            "Der wöchentliche Export bleibt aus."
        )
        return

    run_at = ctx.settings.export_time.replace(tzinfo=ctx.settings.timezone)
    job_queue.run_daily(
        weekly_export,
        time=run_at,
        days=(ctx.settings.export_day_ptb,),
        name=WEEKLY_EXPORT_JOB,
    )
    logger.info(
        "Weekly Export geplant: Wochentag %s um %s (%s)",
        ctx.settings.export_day,
        run_at.strftime("%H:%M"),
        ctx.settings.timezone.key,
    )
