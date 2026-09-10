from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from linkbuddy.config import ConfigError, load_settings
from linkbuddy.services.formatting import relative_age
from linkbuddy.services.periods import parse_period, period_start, trend_percent
import pytest


def test_relative_age_german():
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    created = now.replace(hour=10)
    assert relative_age(created, now=now) == "vor 2 Stunden"


def test_period_start_heute():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 3, 1, 15, 0, tzinfo=timezone.utc)
    start = period_start("heute", tz, now=now)
    assert start is not None
    local = start.astimezone(tz)
    assert local.hour == 0
    assert local.day == 1


def test_parse_period_and_trend():
    assert parse_period("week") == "woche"
    assert trend_percent(12, 10) == "+20%"
    assert trend_percent(5, 0) == "neu"


def test_load_settings_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.env")


def test_load_settings_ok(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=123:abc\nOWNER_USER_ID=99\nEXPORT_DAY=6\nEXPORT_TIME=18:00\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    settings = load_settings(env)
    assert settings.owner_user_id == 99
    assert settings.export_day_ptb == 0  # Spec-Sonntag → PTB-Sonntag
    assert settings.gemini_enabled is False
