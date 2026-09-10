"""/start, /help, /settings und der globale Fehler-Handler."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest

from ... import icons as ic
from ..context import BotContextTypes, app_context, is_authorised, reply, user_id_of

logger = logging.getLogger(__name__)

HELP_TEXT = f"""<b>{ic.BOOK} COMMANDS</b>

<b>{ic.LINK} SAVE</b>
  Paste or forward a link
  → Bot suggests tags, you confirm
  <code>https://... #ai/evals Short note</code>

<b>{ic.SEARCH} SEARCH &amp; BROWSE</b>
  /search &lt;keyword&gt; – full text in URL, title, tags, note
  /tag #category – links with a tag
  /tags – all tags with counts
  /latest [N] – last N links (default: 5)
  /today – saved today
  /week – last 7 days
  /month – last 30 days

<b>{ic.STATS} STATS</b>
  /stats – overview
  /stats #ai – stats for a tag
  /top_tags [week|month|year] – top 10 tags
  /timeline #ai – tag over time

<b>{ic.RELATED} RELATIONS</b>
  /related #ai – tags that co-occur
  /similar &lt;ID&gt; – similar links

<b>{ic.GEAR} MANAGE</b>
  /edit &lt;ID&gt; – edit tags/note
  /delete &lt;ID&gt; – delete link (confirm)
  /export [#tag] [format] – markdown | json | csv | notion

<b>{ic.TIP} OTHER</b>
  Bottom keyboard – tap Latest / Tags / Search / …
  /menu – show the keyboard again
  /help – this overview
  /settings – current config

<b>{ic.TIP} TIPS</b>
  · Tags: #category/sub (e.g. #ai/evals)
  · Multiple tags: #ai/agents #tools
  · Use the <code>#ID</code> after each hit for /edit, /delete, /similar
  · Forwarding a link is enough – the bot detects it"""


async def start(update: Update, context: BotContextTypes) -> None:
    from .. import keyboards as kb

    settings = app_context(context).settings
    uid = user_id_of(update)

    lines = [f"{ic.OK} <b>LinkBuddy</b> ist bereit.", ""]
    if settings.owner_user_id is None:
        lines += [
            f"{ic.WARN} <b>OWNER_USER_ID ist nicht gesetzt.</b> Der Bot antwortet damit jedem.",
            f"Trag <code>OWNER_USER_ID={uid}</code> in die .env ein und starte neu.",
            "",
        ]
    lines += [
        "Schick mir einfach einen Link – ich schlage Tags vor, du bestätigst.",
        "Unten: Tasten für Latest / Tags / Search / …",
        "",
        "/help zeigt alle Befehle · /menu zeigt die Tastatur erneut.",
    ]
    await reply(update, "\n".join(lines), reply_markup=kb.main_reply_keyboard())


async def menu_command(update: Update, context: BotContextTypes) -> None:
    from .. import keyboards as kb

    await reply(
        update,
        f"{ic.OK} Keyboard ready – tap a button or paste a link.",
        reply_markup=kb.main_reply_keyboard(),
    )


async def help_command(update: Update, context: BotContextTypes) -> None:
    from .. import keyboards as kb

    await reply(update, HELP_TEXT, reply_markup=kb.main_reply_keyboard())


async def settings_command(update: Update, context: BotContextTypes) -> None:
    settings = app_context(context).settings
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    backend = "PostgreSQL" if "postgresql" in settings.database_url else "SQLite"
    tagging = (
        f"Heuristik + Gemini ({settings.gemini_model})"
        if settings.gemini_enabled
        else "nur Heuristik (kein GEMINI_API_KEY gesetzt)"
    )
    text = (
        f"<b>{ic.GEAR} EINSTELLUNGEN</b>\n"
        f"Datenbank: {backend}\n"
        f"Auto-Tagging: {tagging}\n"
        f"Zeitzone: {settings.timezone.key}\n"
        f"Wöchentlicher Export: {weekdays[settings.export_day]} "
        f"{settings.export_time.strftime('%H:%M')}\n"
        f"Max. Tags pro Link: {settings.max_tags_per_link}\n"
        f"Max. Notizlänge: {settings.max_note_length} Zeichen\n"
        f"Treffer pro Seite: {settings.page_size}\n"
        f"Umgebung: {settings.environment}"
    )
    await reply(update, text)


async def fallback(update: Update, context: BotContextTypes) -> None:
    """Letzter Handler: Zugriff abweisen oder auf /help verweisen."""
    settings = app_context(context).settings
    if not is_authorised(update, settings):
        user = update.effective_user
        logger.warning("Zugriff abgelehnt fuer User-ID %s", user.id if user else "?")
        await reply(update, f"{ic.LOCK} Dieser Bot ist privat.")
        return

    message = update.effective_message
    if message is not None and message.text and message.text.startswith("/"):
        await reply(update, f"{ic.WARN} Diesen Befehl kenne ich nicht. /help zeigt alle.")
        return
    await reply(
        update,
        f"{ic.TIP} Damit kann ich nichts anfangen. Schick mir einen Link oder nutze /help.",
    )


async def error_handler(update: object, context: BotContextTypes) -> None:
    """Loggt den Stacktrace, meldet dem User aber nur eine kurze Nachricht."""
    logger.error("Unbehandelter Fehler", exc_info=context.error)

    if isinstance(context.error, BadRequest) and "message is not modified" in str(
        context.error
    ).lower():
        return

    if not isinstance(update, Update):
        return
    chat = update.effective_chat
    if chat is None:
        return
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{ic.NO} Da ist etwas schiefgelaufen. Der Fehler wurde protokolliert.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:  # pragma: no cover - Fehler im Fehlerpfad
        logger.exception("Fehlermeldung konnte nicht zugestellt werden")
