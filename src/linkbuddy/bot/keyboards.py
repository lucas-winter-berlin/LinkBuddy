"""Inline-Tastaturen, Reply-Keyboard und callback_data-Schema."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .. import icons as ic

SAVE = "save"
DUP = "dup"
BROKEN = "broken"
RES = "res"
PAGE = "pg"
TAGVIEW = "tv"
NOOP = "noop"

# Persistent reply-keyboard labels (exact match in the text router).
BTN_LATEST = "📥 Latest"
BTN_TODAY = "📅 Today"
BTN_WEEK = "🗓 Week"
BTN_MONTH = "🗓 Month"
BTN_TAGS = "🏷 Tags"
BTN_STATS = "📊 Stats"
BTN_SEARCH = "🔍 Search"
BTN_EXPORT = "📤 Export"
BTN_HELP = "❓ Help"
BTN_SETTINGS = "⚙️ Settings"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Handy-freundliche Dauer-Leiste statt Slash-Commands."""
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(BTN_LATEST),
                KeyboardButton(BTN_TODAY),
                KeyboardButton(BTN_WEEK),
                KeyboardButton(BTN_MONTH),
            ],
            [
                KeyboardButton(BTN_TAGS),
                KeyboardButton(BTN_STATS),
                KeyboardButton(BTN_SEARCH),
            ],
            [
                KeyboardButton(BTN_EXPORT),
                KeyboardButton(BTN_HELP),
                KeyboardButton(BTN_SETTINGS),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Paste a link or tap a button…",
    )


def _btn(text: str, *, icon: str | None = None, **kwargs) -> InlineKeyboardButton:
    """Button mit optionalem Custom-Emoji-Icon (Premium-Owner) und Text-Fallback."""
    emoji_id = ic.button_icon_id(icon) if icon else None
    if emoji_id:
        return InlineKeyboardButton(text, icon_custom_emoji_id=emoji_id, **kwargs)
    prefix = f"{ic.plain(icon)} " if icon else ""
    return InlineKeyboardButton(f"{prefix}{text}", **kwargs)


def confirm_save(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Save", icon="ok", callback_data=f"{SAVE}:ok:{token}"),
                _btn("Tags", icon="edit", callback_data=f"{SAVE}:tags:{token}"),
            ],
            [
                _btn("Note", icon="note", callback_data=f"{SAVE}:note:{token}"),
                _btn("Cancel", icon="no", callback_data=f"{SAVE}:cancel:{token}"),
            ],
        ]
    )


def broken_link(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Save anyway", icon="save", callback_data=f"{BROKEN}:save:{token}")],
            [
                _btn("Fix URL", icon="edit", callback_data=f"{BROKEN}:edit:{token}"),
                _btn("Cancel", icon="no", callback_data=f"{BROKEN}:cancel:{token}"),
            ],
        ]
    )


def duplicate(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Update existing", icon="refresh", callback_data=f"{DUP}:merge:{token}")],
            [_btn("Save separately", icon="save", callback_data=f"{DUP}:copy:{token}")],
            [_btn("Cancel", icon="no", callback_data=f"{DUP}:cancel:{token}")],
        ]
    )


def saved_actions(resource_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("Open", icon="link", url=url)],
            [
                _btn("Edit", icon="edit", callback_data=f"{RES}:edit:{resource_id}"),
                _btn("Similar", icon="related", callback_data=f"{RES}:similar:{resource_id}"),
                _btn("Delete", icon="trash", callback_data=f"{RES}:del:{resource_id}"),
            ],
        ]
    )


def edit_menu(resource_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Tags", icon="edit", callback_data=f"{RES}:edittags:{resource_id}"),
                _btn("Note", icon="note", callback_data=f"{RES}:editnote:{resource_id}"),
            ],
            [_btn("Done", icon="ok", callback_data=f"{RES}:done:{resource_id}")],
        ]
    )


def delete_confirm(resource_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("Yes, delete", icon="ok", callback_data=f"{RES}:delyes:{resource_id}"),
                _btn("No", icon="no", callback_data=f"{RES}:delno:{resource_id}"),
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
        row.append(_btn("Newer", icon="refresh", callback_data=f"{PAGE}:{token}:prev"))
    if has_next:
        row.append(_btn("Older", icon="save", callback_data=f"{PAGE}:{token}:next"))
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
