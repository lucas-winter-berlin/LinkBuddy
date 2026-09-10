"""Aufbau der Telegram-Application: Handler, Zugriffsschutz, Jobs."""

from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    Defaults,
    MessageHandler,
    filters,
)

from ..config import Settings
from ..db import Database
from ..services.gemini import GeminiTagger
from . import jobs, keyboards
from .context import AppContext, BotContextTypes, app_context, is_authorised
from .handlers import common, manage, query, router, stats

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("suche", "Volltext-Suche"),
    BotCommand("tag", "Links mit einem Tag"),
    BotCommand("tags", "Alle Tags mit Count"),
    BotCommand("neue", "Letzte Links"),
    BotCommand("heute", "Heute gespeichert"),
    BotCommand("woche", "Letzte 7 Tage"),
    BotCommand("monat", "Letzte 30 Tage"),
    BotCommand("stats", "Statistiken"),
    BotCommand("top_tags", "Top 10 Tags"),
    BotCommand("timeline", "Verlauf eines Tags"),
    BotCommand("related", "Verwandte Tags"),
    BotCommand("similar", "Ähnliche Links"),
    BotCommand("edit", "Link bearbeiten"),
    BotCommand("delete", "Link löschen"),
    BotCommand("export", "Sammlung exportieren"),
    BotCommand("settings", "Konfiguration anzeigen"),
    BotCommand("help", "Alle Befehle"),
]


def build_application(settings: Settings, database: Database) -> Application:
    """Baut die Application inklusive aller Handler."""
    tagger = (
        GeminiTagger(settings.gemini_api_key, settings.gemini_model)
        if settings.gemini_enabled
        else None
    )
    app_ctx = AppContext(settings=settings, db=database, tagger=tagger)

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .defaults(Defaults(tzinfo=settings.timezone))
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.bot_data["app_context"] = app_ctx

    allowed = (
        filters.User(user_id=settings.owner_user_id)
        if settings.owner_user_id is not None
        else filters.ALL
    )

    _register_commands(application, allowed)
    _register_callbacks(application)

    # Freier Text: alles ausser Commands.
    application.add_handler(
        MessageHandler(
            allowed & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            router.text_router,
        )
    )

    # Muss zuletzt stehen: alles, was kein Handler davor abgeholt hat.
    application.add_handler(MessageHandler(filters.ALL, common.fallback))

    application.add_error_handler(common.error_handler)
    return application


def _guarded(callback):
    """Callback-Queries kennen keine Filter, deshalb die Pruefung im Wrapper."""

    async def wrapper(update, context: BotContextTypes) -> None:
        if not is_authorised(update, app_context(context).settings):
            await _reject_callback(update, context)
            return
        await callback(update, context)

    wrapper.__name__ = getattr(callback, "__name__", "guarded_callback")
    return wrapper


def _register_commands(application: Application, allowed) -> None:
    handlers = [
        ("start", common.start),
        ("help", common.help_command),
        ("settings", common.settings_command),
        ("suche", query.search_command),
        ("tag", query.tag_command),
        ("tags", query.tags_command),
        ("neue", query.period_command),
        ("heute", query.period_command),
        ("woche", query.period_command),
        ("monat", query.period_command),
        ("stats", stats.stats_command),
        ("top_tags", stats.top_tags_command),
        ("toptags", stats.top_tags_command),
        ("timeline", stats.timeline_command),
        ("related", stats.related_command),
        ("similar", stats.similar_command),
        ("edit", manage.edit_command),
        ("delete", manage.delete_command),
        ("export", manage.export_command),
    ]
    for name, callback in handlers:
        application.add_handler(CommandHandler(name, callback, filters=allowed))


def _register_callbacks(application: Application) -> None:
    from .handlers import save

    routes = [
        (keyboards.SAVE, save.save_callback),
        (keyboards.BROKEN, save.broken_callback),
        (keyboards.DUP, save.duplicate_callback),
        (keyboards.RES, manage.resource_callback),
        (keyboards.PAGE, query.pagination_callback),
        (keyboards.TAGVIEW, query.tag_view_callback),
    ]
    for prefix, callback in routes:
        application.add_handler(
            CallbackQueryHandler(_guarded(callback), pattern=rf"^{prefix}:")
        )


async def _reject_callback(update, context) -> None:
    """Buttons von fremden Accounts still ablehnen."""
    if update.callback_query is not None:
        await update.callback_query.answer("🔒 Dieser Bot ist privat.", show_alert=True)


async def _post_init(application: Application) -> None:
    ctx: AppContext = application.bot_data["app_context"]
    await ctx.db.create_schema()
    await application.bot.set_my_commands(BOT_COMMANDS)
    jobs.schedule_jobs(application)
    me = await application.bot.get_me()
    logger.info("Bot @%s ist bereit", me.username)


async def _post_shutdown(application: Application) -> None:
    ctx: AppContext = application.bot_data["app_context"]
    await ctx.db.dispose()
    logger.info("Datenbank-Verbindungen geschlossen")
