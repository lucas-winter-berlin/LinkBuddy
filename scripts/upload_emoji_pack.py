"""Laedt das LinkBuddy Custom-Emoji-Pack zu Telegram hoch und speichert die IDs.

Voraussetzungen:
  - Bot laeuft / Token in .env
  - OWNER_USER_ID gesetzt (wird Pack-Owner)
  - Du hast den Bot mindestens einmal angeschrieben (/start)

Icons: assets/emoji/*.webp (vorher: python scripts/generate_icons.py)
Ergebnis: assets/emoji_pack.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from linkbuddy.config import load_settings  # noqa: E402

EMOJI_DIR = ROOT / "assets" / "emoji"
PACK_FILE = ROOT / "assets" / "emoji_pack.json"

# Name muss auf _by_<botusername> enden (Kleinbuchstaben).
PACK_TITLE = "LinkBuddy Icons"

# Fallback-Emoji pro Icon (sichtbar, wenn Custom Emoji nicht darstellbar ist)
FALLBACKS: dict[str, str] = {
    "ok": "✅",
    "no": "❌",
    "edit": "✏️",
    "note": "📝",
    "link": "🔗",
    "search": "🔍",
    "stats": "📊",
    "related": "🔀",
    "save": "💾",
    "refresh": "🔄",
    "trash": "🗑",
    "warn": "⚠️",
    "wait": "⏳",
    "section": "▶️",
    "export": "📤",
    "tag": "🏷",
    "gear": "⚙️",
    "lock": "🔒",
    "tip": "💡",
}

KEYWORDS: dict[str, list[str]] = {
    "ok": ["ok", "check", "save"],
    "no": ["close", "cancel", "delete"],
    "edit": ["edit", "pencil"],
    "note": ["note", "text"],
    "link": ["link", "open", "url"],
    "search": ["search", "find"],
    "stats": ["stats", "chart"],
    "related": ["related", "similar"],
    "save": ["download", "save"],
    "refresh": ["refresh", "update"],
    "trash": ["trash", "delete"],
    "warn": ["warn", "alert"],
    "wait": ["wait", "loading"],
    "section": ["section", "menu"],
    "export": ["export", "upload"],
    "tag": ["tag"],
    "gear": ["settings", "gear"],
    "lock": ["lock", "private"],
    "tip": ["tip", "idea"],
}


async def main() -> int:
    from telegram import Bot, InputSticker
    from telegram.constants import StickerFormat
    from telegram.error import BadRequest, TelegramError

    settings = load_settings(ROOT / ".env")
    if not settings.owner_user_id:
        print("OWNER_USER_ID fehlt in .env")
        return 1

    bot = Bot(settings.telegram_bot_token)
    async with bot:
        me = await bot.get_me()
        username = (me.username or "").lower()
        pack_name = f"linkbuddy_icons_by_{username}"
        print(f"Bot @{username} | Pack: {pack_name}")

        files = sorted(EMOJI_DIR.glob("*.webp"))
        if not files:
            print("Keine WEBP-Icons. Zuerst: python scripts/generate_icons.py")
            return 1

        # Existierendes Pack? Dann nur IDs aktualisieren.
        existing = None
        try:
            existing = await bot.get_sticker_set(pack_name)
            print(f"Pack existiert bereits ({len(existing.stickers)} Stickers)")
        except TelegramError:
            existing = None

        if existing is None:
            first = files[0]
            key = first.stem
            print(f"Erstelle Pack mit {key} …")
            with first.open("rb") as fh:
                uploaded = await bot.upload_sticker_file(
                    user_id=settings.owner_user_id,
                    sticker=fh,
                    sticker_format=StickerFormat.STATIC,
                )
            sticker = InputSticker(
                sticker=uploaded.file_id,
                format=StickerFormat.STATIC,
                emoji_list=[FALLBACKS.get(key, "⭐")],
                keywords=KEYWORDS.get(key, [key]),
            )
            try:
                await bot.create_new_sticker_set(
                    user_id=settings.owner_user_id,
                    name=pack_name,
                    title=PACK_TITLE,
                    stickers=[sticker],
                    sticker_type="custom_emoji",
                    needs_repainting=True,
                )
            except BadRequest as exc:
                print(f"createNewStickerSet fehlgeschlagen: {exc}")
                print(
                    "Tipp: Bot einmal per /start anschreiben. "
                    "Custom-Emoji-Packs brauchen ggf. Premium beim Owner."
                )
                return 1

            for path in files[1:]:
                key = path.stem
                print(f"  + {key}")
                with path.open("rb") as fh:
                    uploaded = await bot.upload_sticker_file(
                        user_id=settings.owner_user_id,
                        sticker=fh,
                        sticker_format=StickerFormat.STATIC,
                    )
                sticker = InputSticker(
                    sticker=uploaded.file_id,
                    format=StickerFormat.STATIC,
                    emoji_list=[FALLBACKS.get(key, "⭐")],
                    keywords=KEYWORDS.get(key, [key]),
                )
                await bot.add_sticker_to_set(
                    user_id=settings.owner_user_id,
                    name=pack_name,
                    sticker=sticker,
                )

            existing = await bot.get_sticker_set(pack_name)

        # IDs zuordnen: Reihenfolge der Stickers entspricht Upload-Reihenfolge,
        # zusaetzlich per Keyword/Fallback matchen.
        ids: dict[str, str] = {}
        by_emoji = {s.emoji: s for s in existing.stickers if s.emoji}
        for key, fallback in FALLBACKS.items():
            sticker = by_emoji.get(fallback)
            if sticker and sticker.custom_emoji_id:
                ids[key] = sticker.custom_emoji_id

        # Fallback-Zuordnung ueber Dateireihenfolge, falls Emoji-Match fehlt
        if len(ids) < len(FALLBACKS):
            stems = [p.stem for p in files]
            for sticker, stem in zip(existing.stickers, stems):
                if sticker.custom_emoji_id and stem not in ids:
                    ids[stem] = sticker.custom_emoji_id

        payload = {
            "pack_name": pack_name,
            "pack_title": PACK_TITLE,
            "bot_username": username,
            "needs_repainting": True,
            "ids": ids,
            "fallbacks": FALLBACKS,
            "add_link": f"https://t.me/addemoji/{pack_name}",
        }
        PACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        PACK_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Gespeichert: {PACK_FILE}")
        print(f"Emoji hinzufuegen: {payload['add_link']}")
        print(f"{len(ids)} Custom-Emoji-IDs")
        for key, eid in sorted(ids.items()):
            print(f"  {key}: {eid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
