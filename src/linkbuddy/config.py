"""Zentrale Konfiguration, aus Umgebungsvariablen gelesen."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# EXPORT_DAY folgt der Spec (0=Montag ... 6=Sonntag). Der JobQueue von
# python-telegram-bot zaehlt dagegen 0=Sonntag ... 6=Samstag.
_SPEC_DAY_TO_PTB_DAY = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}


class ConfigError(RuntimeError):
    """Wird geworfen, wenn Pflicht-Konfiguration fehlt oder unbrauchbar ist."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    owner_user_id: int | None
    gemini_api_key: str | None
    gemini_model: str
    timezone: ZoneInfo
    export_day: int
    export_time: dt_time
    http_timeout: float
    max_tags_per_link: int
    max_note_length: int
    max_url_length: int
    search_limit: int
    page_size: int
    export_chunk_size: int
    log_level: str
    environment: str
    tag_suggestion_limit: int = 3
    domain_source_map: dict[str, str] = field(default_factory=dict)

    @property
    def export_day_ptb(self) -> int:
        """Export-Wochentag in der Zaehlweise der PTB JobQueue."""
        return _SPEC_DAY_TO_PTB_DAY[self.export_day]

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} muss eine Zahl sein, war: {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} muss eine Zahl sein, war: {raw!r}") from exc


def _parse_time(raw: str) -> dt_time:
    parts = raw.strip().split(":")
    if len(parts) not in (2, 3):
        raise ConfigError(f"EXPORT_TIME muss HH:MM sein, war: {raw!r}")
    try:
        numbers = [int(p) for p in parts]
    except ValueError as exc:
        raise ConfigError(f"EXPORT_TIME muss HH:MM sein, war: {raw!r}") from exc
    hour, minute = numbers[0], numbers[1]
    second = numbers[2] if len(numbers) == 3 else 0
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
        raise ConfigError(f"EXPORT_TIME liegt ausserhalb gueltiger Zeiten: {raw!r}")
    return dt_time(hour, minute, second)


def _normalise_database_url(raw: str) -> str:
    """Bringt gaengige DSN-Formen auf einen async-faehigen SQLAlchemy-Treiber."""
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        url = "sqlite+aiosqlite://" + url[len("sqlite://") :]
    return url


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    """Liest die Konfiguration. Fehlende Pflichtwerte fuehren zu ConfigError."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN fehlt. Lege eine .env nach dem Vorbild von "
            ".env.example an."
        )

    default_db = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'linkbuddy.db').as_posix()}"
    database_url = _normalise_database_url(os.getenv("DATABASE_URL", default_db))

    owner_raw = os.getenv("OWNER_USER_ID", "").strip()
    owner_user_id = int(owner_raw) if owner_raw else None

    export_day = _env_int("EXPORT_DAY", 6)
    if export_day not in _SPEC_DAY_TO_PTB_DAY:
        raise ConfigError("EXPORT_DAY muss zwischen 0 (Montag) und 6 (Sonntag) liegen.")

    tz_name = os.getenv("BOT_TIMEZONE", "Europe/Berlin").strip() or "Europe/Berlin"
    try:
        timezone = ZoneInfo(tz_name)
    except Exception as exc:  # ZoneInfoNotFoundError und Verwandte
        raise ConfigError(f"BOT_TIMEZONE unbekannt: {tz_name!r}") from exc

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip() or None

    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        owner_user_id=owner_user_id,
        gemini_api_key=gemini_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip(),
        timezone=timezone,
        export_day=export_day,
        export_time=_parse_time(os.getenv("EXPORT_TIME", "18:00")),
        http_timeout=_env_float("HTTP_TIMEOUT", 5.0),
        max_tags_per_link=_env_int("MAX_TAGS_PER_LINK", 10),
        max_note_length=_env_int("MAX_NOTE_LENGTH", 200),
        max_url_length=_env_int("MAX_URL_LENGTH", 2048),
        search_limit=_env_int("SEARCH_LIMIT", 50),
        page_size=_env_int("PAGE_SIZE", 5),
        export_chunk_size=_env_int("EXPORT_CHUNK_SIZE", 100),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        environment=os.getenv("DEPLOYMENT_ENV", "development").strip(),
    )
