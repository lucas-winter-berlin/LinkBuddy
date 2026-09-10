"""Inline-Tastaturen und das Schema der callback_data."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .. import icons as ic

SAVE = "save"
DUP = "dup"
BROKEN = "broken"
RES = "res"
PAGE = "pg"
TAGVIEW = "tv"
NOOP = "noop"


def _btn(text: str, *, icon: str | None = None, **kwargs) -> InlineKeyboardButton:
    """Button mit optionalem Custom-Emoji-Icon (Premium-Owner) und Text-Fallback."""
    emoji_id = ic.button_icon_id(icon) if icon else None
    if emoji_id:
        # Icon sitzt links vom Label – kein Text-Praefix noetig.
        return InlineKeyboardButton(text, icon_custom_emoji_id=emoji_id, **kwargs)
    prefix = f"{ic.plain(icon)} " if icon else ""
    return InlineKeyboardButton(f"{prefix}{text}", **kwargs)


def confirm_save(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Speichern", icon="ok", callback_data=f"{SAVE}:ok:{token}"),
                _btn("Tags", icon="edit", callback_data=f"{SAVE}:tags:{token}"),
            ],
            [
                _btn("Notiz", icon="note", callback_data=f"{SAVE}:note:{token}"),
                _btn("Abbrechen", icon="no", callback_data=f"{SAVE}:cancel:{token}"),
            ],
        ]
    )


def broken_link(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Trotzdem speichern", icon="save", callback_data=f"{BROKEN}:save:{token}")],
            [
                _btn("URL korrigieren", icon="edit", callback_data=f"{BROKEN}:edit:{token}"),
                _btn("Abbrechen", icon="no", callback_data=f"{BROKEN}:cancel:{token}"),
            ],
        ]
    )


def duplicate(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Alt updaten", icon="refresh", callback_data=f"{DUP}:merge:{token}")],
            [_btn("Separat speichern", icon="save", callback_data=f"{DUP}:copy:{token}")],
            [_btn("Abbrechen", icon="no", callback_data=f"{DUP}:cancel:{token}")],
        ]
    )


def saved_actions(resource_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Öffnen", icon="link", url=url)],
            [
                _btn("Edit", icon="edit", callback_data=f"{RES}:edit:{resource_id}"),
                _btn("Ähnliche", icon="related", callback_data=f"{RES}:similar:{resource_id}"),
                _btn("Löschen", icon="trash", callback_data=f"{RES}:del:{resource_id}"),
            ],
        ]
    )


def edit_menu(resource_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Tags", icon="edit", callback_data=f"{RES}:edittags:{resource_id}"),
                _btn("Notiz", icon="note", callback_data=f"{RES}:editnote:{resource_id}"),
            ],
            [_btn("Fertig", icon="ok", callback_data=f"{RES}:done:{resource_id}")],
        ]
    )


def delete_confirm(resource_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Ja, löschen", icon="ok", callback_data=f"{RES}:delyes:{resource_id}"),
                _btn("Nein", icon="no", callback_data=f"{RES}:delno:{resource_id}"),
            ]
        ]
    )


def pagination(
    token: str, *, offset: int, has_prev: bool, has_next: bool
) -> InlineKeyboardMarkup | None:
    if not has_prev and not has_next:
        return None
    row: list[InlineKeyboardButton] = []
    if has_prev:
        row.append(_btn("Neuere", icon="refresh", callback_data=f"{PAGE}:{token}:prev"))
    if has_next:
        row.append(_btn("Ältere", icon="save", callback_data=f"{PAGE}:{token}:next"))
    return InlineKeyboardMarkup([row])


def tag_overview(root: str, subtags: list[str]) -> InlineKeyboardMarkup | None:
    buttons = [
        InlineKeyboardButton(f"#{tag}", callback_data=f"{TAGVIEW}:{tag}")
        for tag in subtags[:8]
        if len(f"{TAGVIEW}:{tag}".encode()) <= 64
    ]
    if not buttons:
        return None
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)
