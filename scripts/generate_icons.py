"""Erzeugt 100x100 Material-Style Icons als WEBP fuer Telegram Custom Emoji.

Weisse Striche auf transparentem Grund. Mit needs_repainting=True faerbt
Telegram sie in die aktuelle Textfarbe ein (monochrom, Theme-tauglich).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 100
PAD = 22
STROKE = 7
OUT = Path(__file__).resolve().parents[1] / "assets" / "emoji"


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _save(name: str, img: Image.Image) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.webp"
    img.save(path, "WEBP", lossless=True)
    return path


def _box() -> tuple[int, int, int, int]:
    return PAD, PAD, SIZE - PAD, SIZE - PAD


def icon_check() -> Path:
    img, d = _canvas()
    d.line([(30, 52), (44, 68), (72, 34)], fill="white", width=STROKE, joint="curve")
    return _save("ok", img)


def icon_close() -> Path:
    img, d = _canvas()
    d.line([(32, 32), (68, 68)], fill="white", width=STROKE)
    d.line([(68, 32), (32, 68)], fill="white", width=STROKE)
    return _save("no", img)


def icon_edit() -> Path:
    img, d = _canvas()
    # Stift / Pencil
    d.line([(34, 66), (66, 34)], fill="white", width=STROKE)
    d.polygon([(30, 70), (38, 72), (36, 64)], fill="white")
    d.line([(62, 30), (70, 38)], fill="white", width=STROKE)
    return _save("edit", img)


def icon_note() -> Path:
    img, d = _canvas()
    x0, y0, x1, y1 = _box()
    d.rounded_rectangle([x0, y0, x1, y1], radius=8, outline="white", width=STROKE)
    for y in (42, 54, 66):
        d.line([(38, y), (62, y)], fill="white", width=STROKE - 2)
    return _save("note", img)


def icon_link() -> Path:
    img, d = _canvas()
    # External-link: Quadrat + Pfeil
    d.rounded_rectangle([28, 36, 64, 72], radius=6, outline="white", width=STROKE)
    d.line([(52, 28), (72, 28), (72, 48)], fill="white", width=STROKE)
    d.line([(48, 52), (72, 28)], fill="white", width=STROKE)
    return _save("link", img)


def icon_search() -> Path:
    img, d = _canvas()
    d.ellipse([26, 26, 62, 62], outline="white", width=STROKE)
    d.line([(58, 58), (74, 74)], fill="white", width=STROKE)
    return _save("search", img)


def icon_stats() -> Path:
    img, d = _canvas()
    d.rectangle([28, 54, 40, 72], outline="white", width=STROKE - 1, fill="white")
    d.rectangle([46, 40, 58, 72], outline="white", width=STROKE - 1, fill="white")
    d.rectangle([64, 28, 76, 72], outline="white", width=STROKE - 1, fill="white")
    return _save("stats", img)


def icon_related() -> Path:
    img, d = _canvas()
    # Zwei verkettete Knoten
    d.ellipse([24, 38, 48, 62], outline="white", width=STROKE)
    d.ellipse([52, 38, 76, 62], outline="white", width=STROKE)
    d.line([(48, 50), (52, 50)], fill="white", width=STROKE)
    return _save("related", img)


def icon_save() -> Path:
    img, d = _canvas()
    # Download-Pfeil
    d.line([(50, 26), (50, 60)], fill="white", width=STROKE)
    d.line([(34, 48), (50, 66), (66, 48)], fill="white", width=STROKE)
    d.line([(30, 74), (70, 74)], fill="white", width=STROKE)
    return _save("save", img)


def icon_refresh() -> Path:
    img, d = _canvas()
    d.arc([26, 26, 74, 74], start=40, end=300, fill="white", width=STROKE)
    d.polygon([(68, 28), (78, 42), (60, 40)], fill="white")
    return _save("refresh", img)


def icon_trash() -> Path:
    img, d = _canvas()
    d.line([(34, 36), (66, 36)], fill="white", width=STROKE)
    d.line([(42, 28), (58, 28)], fill="white", width=STROKE)
    d.rounded_rectangle([36, 40, 64, 74], radius=4, outline="white", width=STROKE)
    d.line([(46, 48), (46, 66)], fill="white", width=STROKE - 2)
    d.line([(54, 48), (54, 66)], fill="white", width=STROKE - 2)
    return _save("trash", img)


def icon_warn() -> Path:
    img, d = _canvas()
    d.polygon([(50, 24), (78, 74), (22, 74)], outline="white", width=STROKE)
    d.line([(50, 42), (50, 56)], fill="white", width=STROKE)
    d.ellipse([46, 62, 54, 70], fill="white")
    return _save("warn", img)


def icon_wait() -> Path:
    img, d = _canvas()
    d.ellipse([26, 26, 74, 74], outline="white", width=STROKE)
    d.line([(50, 36), (50, 52)], fill="white", width=STROKE)
    d.line([(50, 52), (62, 60)], fill="white", width=STROKE)
    return _save("wait", img)


def icon_section() -> Path:
    img, d = _canvas()
    d.polygon([(38, 28), (68, 50), (38, 72)], outline="white", width=STROKE)
    return _save("section", img)


def icon_export() -> Path:
    img, d = _canvas()
    d.line([(50, 66), (50, 32)], fill="white", width=STROKE)
    d.line([(34, 44), (50, 28), (66, 44)], fill="white", width=STROKE)
    d.line([(30, 74), (70, 74)], fill="white", width=STROKE)
    return _save("export", img)


def icon_tag() -> Path:
    img, d = _canvas()
    d.polygon([(28, 28), (58, 28), (74, 50), (58, 72), (28, 72)], outline="white", width=STROKE)
    d.ellipse([36, 40, 46, 50], fill="white")
    return _save("tag", img)


def icon_gear() -> Path:
    img, d = _canvas()
    d.ellipse([36, 36, 64, 64], outline="white", width=STROKE)
    for angle_box in (
        (46, 22, 54, 34),
        (46, 66, 54, 78),
        (22, 46, 34, 54),
        (66, 46, 78, 54),
    ):
        d.rectangle(list(angle_box), fill="white")
    return _save("gear", img)


def icon_lock() -> Path:
    img, d = _canvas()
    d.rounded_rectangle([32, 46, 68, 76], radius=6, outline="white", width=STROKE)
    d.arc([38, 24, 62, 52], start=180, end=0, fill="white", width=STROKE)
    return _save("lock", img)


def icon_tip() -> Path:
    img, d = _canvas()
    d.ellipse([30, 24, 70, 64], outline="white", width=STROKE)
    d.line([(50, 64), (50, 72)], fill="white", width=STROKE)
    d.line([(40, 78), (60, 78)], fill="white", width=STROKE)
    return _save("tip", img)


GENERATORS = [
    icon_check,
    icon_close,
    icon_edit,
    icon_note,
    icon_link,
    icon_search,
    icon_stats,
    icon_related,
    icon_save,
    icon_refresh,
    icon_trash,
    icon_warn,
    icon_wait,
    icon_section,
    icon_export,
    icon_tag,
    icon_gear,
    icon_lock,
    icon_tip,
]


def main() -> None:
    paths = [gen() for gen in GENERATORS]
    print(f"{len(paths)} Icons in {OUT}")
    for path in paths:
        print(" ", path.name)


if __name__ == "__main__":
    main()
