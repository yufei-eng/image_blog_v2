"""PNG composite renderer for Life Comic.

Creates a single shareable high-DPI PNG image combining the generated comic, narrative, and metadata.
Uses 2x scale factor for crisp rendering on Retina / high-DPI displays.
"""

import os
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageOps

SCALE = 2
CANVAS_W = 1080 * SCALE
CARD_PADDING = 40 * SCALE
BG_COLOR = (255, 252, 248)
TEXT_COLOR = (50, 50, 50)
ACCENT_COLOR = (140, 90, 160)
SUBTITLE_COLOR = (120, 120, 120)
DATE_COLOR = (150, 150, 150)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size * SCALE)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) > max_w:
            if cur:
                lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _s(val: int) -> int:
    return val * SCALE


def _ensure_canvas(canvas: Image.Image, draw: ImageDraw.Draw, y: int, extra: int) -> tuple[Image.Image, ImageDraw.Draw]:
    if y + extra > canvas.height - CARD_PADDING:
        new_h = canvas.height + max(extra + CARD_PADDING * 2, _s(600))
        new_canvas = Image.new("RGB", (CANVAS_W, new_h), BG_COLOR)
        new_canvas.paste(canvas, (0, 0))
        return new_canvas, ImageDraw.Draw(new_canvas)
    return canvas, draw


def render_comic_png(
    storyboard: dict,
    comic_image_path: Optional[str],
    reference_paths: list[str],
    output_path: str,
) -> str:
    """Render comic as a single high-DPI composite PNG. Returns output path."""
    theme = storyboard.get("theme", "Life Comic")
    narrative = storyboard.get("narrative", {})
    title = narrative.get("title", theme)
    body = narrative.get("body", "")
    footer_date = storyboard.get("footer_date", "")

    title_font = _load_font(48)
    body_font = _load_font(22)
    small_font = _load_font(18)
    content_w = CANVAS_W - 2 * CARD_PADDING

    line_h_title = _s(55)
    line_h_body = _s(30)
    line_h_small = _s(24)

    comic_img = None
    comic_h = 0
    if comic_image_path and os.path.exists(comic_image_path):
        comic_img = Image.open(comic_image_path)
        comic_img = ImageOps.exif_transpose(comic_img)
        if comic_img.mode != "RGB":
            comic_img = comic_img.convert("RGB")
        ratio = content_w / comic_img.width
        comic_h = int(comic_img.height * ratio)
        comic_img = comic_img.resize((content_w, comic_h), Image.LANCZOS)

    estimated_h = CARD_PADDING + line_h_title * 2 + _s(40) + comic_h + _s(40) + _s(600) + CARD_PADDING
    canvas = Image.new("RGB", (CANVAS_W, max(estimated_h, _s(600))), BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    y = CARD_PADDING

    for tl in _wrap_text(draw, title, title_font, content_w):
        draw.text((CARD_PADDING, y), tl, fill=ACCENT_COLOR, font=title_font)
        y += line_h_title
    y += _s(6)

    draw.text((CARD_PADDING, y), theme, fill=SUBTITLE_COLOR, font=small_font)
    y += line_h_small + _s(10)

    if comic_img:
        canvas.paste(comic_img, (CARD_PADDING, y))
        y += comic_h + _s(20)

    draw.line([(CARD_PADDING, y), (CANVAS_W - CARD_PADDING, y)], fill=ACCENT_COLOR, width=SCALE * 2)
    y += _s(20)

    if body:
        for ln in _wrap_text(draw, body, body_font, content_w):
            canvas, draw = _ensure_canvas(canvas, draw, y, line_h_body)
            draw.text((CARD_PADDING, y), ln, fill=TEXT_COLOR, font=body_font)
            y += line_h_body
        y += _s(20)

    if footer_date:
        canvas, draw = _ensure_canvas(canvas, draw, y, line_h_small + _s(40))
        draw.text((CARD_PADDING, y), footer_date, fill=DATE_COLOR, font=small_font)
        y += _s(40)

    canvas = canvas.crop((0, 0, CANVAS_W, min(y + CARD_PADDING, canvas.height)))
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path
