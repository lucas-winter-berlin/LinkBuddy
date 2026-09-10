"""Einstiegspunkt: Konfiguration laden, Schema anlegen, Polling starten."""

from __future__ import annotations

import logging
import sys

from .bot.app import build_application
from .config import ConfigError, load_settings
from .db import Database


def configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
    # httpx loggt jeden Telegram-Poll auf INFO – das verstopft die Logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.INFO)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 1

    configure_logging(settings.log_level)
    logger = logging.getLogger("linkbuddy")

    # Die Engine wird hier nur konstruiert. Verbunden und migriert wird in
    # post_init, damit der Connection-Pool im Event-Loop der Application liegt.
    database = Database(settings.database_url)
    backend = "PostgreSQL" if "postgresql" in settings.database_url else "SQLite"
    logger.info("Datenbank-Backend: %s", backend)
    if not settings.gemini_enabled:
        logger.info("Kein GEMINI_API_KEY gesetzt – Auto-Tagging läuft rein heuristisch.")

    application = build_application(settings, database)
    logger.info("Starte Polling …")
    application.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
