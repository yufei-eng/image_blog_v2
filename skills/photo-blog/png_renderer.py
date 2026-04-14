"""PNG composite renderer for Photo Blog.

Creates a single shareable high-DPI PNG image combining title, photos, and text.
Uses 2x scale factor for crisp rendering on Retina / high-DPI displays.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

SCALE = 2
CANVAS_W = 1080 * SCALE
CARD_PADDING = 40 * SCALE
PHOTO_SPACING = 16 * SCALE
BG_COLOR = (255, 252, 248)
TEXT_COLOR = (50, 50, 50)
ACCENT_COLOR = (180, 120, 70)
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


def _fit_photo(path: str, target_w: int, target_h: int) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = ImageOps.fit(img, (target_w, target_h), Image.LANCZOS)
    return img


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
    """Scale a logical pixel value."""
    return val * SCALE


def _ensure_canvas(canvas: Image.Image, draw: ImageDraw.Draw, y: int, extra: int) -> tuple[Image.Image, ImageDraw.Draw]:
    """Extend canvas height if needed."""
    if y + extra > canvas.height - CARD_PADDING:
        new_h = canvas.height + max(extra + CARD_PADDING * 2, _s(600))
        new_canvas = Image.new("RGB", (CANVAS_W, new_h), BG_COLOR)
        new_canvas.paste(canvas, (0, 0))
        return new_canvas, ImageDraw.Draw(new_canvas)
    return canvas, draw


def render_blog_png(blog_content: dict, highlight_paths: list[str], output_path: str) -> str:
    """Render blog as a single high-DPI composite PNG."""
    title = blog_content.get("title", "Photo Blog")
    desc = blog_content.get("description", {}).get("text", "")
    insights = blog_content.get("insights", [])
    footer_date = blog_content.get("footer_date", "")

    title_font = _load_font(48)
    body_font = _load_font(24)
    small_font = _load_font(18)

    content_w = CANVAS_W - 2 * CARD_PADDING
    n_photos = len(highlight_paths)

    if n_photos <= 1:
        cols = 1
    elif n_photos <= 4:
        cols = 2
    else:
        cols = 3

    photo_w = (content_w - (cols - 1) * PHOTO_SPACING) // cols
    photo_h = int(photo_w * 0.75)
    n_rows = (n_photos + cols - 1) // cols
    photos_block_h = n_rows * photo_h + (n_rows - 1) * PHOTO_SPACING

    line_h_title = _s(55)
    line_h_body = _s(32)
    line_h_small = _s(24)

    estimated_h = (
        CARD_PADDING + line_h_title * 2
        + _s(20)
        + line_h_body * 6
        + _s(20)
        + photos_block_h
        + _s(40)
        + len(insights) * line_h_body * 4
        + _s(80)
        + CARD_PADDING
    )

    canvas = Image.new("RGB", (CANVAS_W, max(estimated_h, _s(600))), BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    y = CARD_PADDING

    title_lines = _wrap_text(draw, title, title_font, content_w)
    for tl in title_lines:
        draw.text((CARD_PADDING, y), tl, fill=ACCENT_COLOR, font=title_font)
        y += line_h_title
    y += _s(6)
    draw.line([(CARD_PADDING, y), (CANVAS_W - CARD_PADDING, y)], fill=ACCENT_COLOR, width=SCALE * 2)
    y += _s(20)

    if desc:
        desc_lines = _wrap_text(draw, desc, body_font, content_w)
        for dl in desc_lines:
            draw.text((CARD_PADDING, y), dl, fill=TEXT_COLOR, font=body_font)
            y += line_h_body
        y += _s(24)

    for idx, path in enumerate(highlight_paths):
        row, col = divmod(idx, cols)
        px = CARD_PADDING + col * (photo_w + PHOTO_SPACING)
        py = y + row * (photo_h + PHOTO_SPACING)
        try:
            photo = _fit_photo(path, photo_w, photo_h)
            canvas.paste(photo, (px, py))
        except Exception:
            draw.rectangle([(px, py), (px + photo_w, py + photo_h)], fill=(220, 220, 220))

    y += photos_block_h + _s(30)

    for i, ins in enumerate(insights):
        text = ins.get("text", "")
        lines = _wrap_text(draw, f"{i+1}. {text}", body_font, content_w)
        for ln in lines:
            canvas, draw = _ensure_canvas(canvas, draw, y, line_h_body)
            draw.text((CARD_PADDING, y), ln, fill=TEXT_COLOR, font=body_font)
            y += line_h_body
        y += _s(12)

    if footer_date:
        y += _s(20)
        canvas, draw = _ensure_canvas(canvas, draw, y, line_h_small + _s(40))
        draw.text((CARD_PADDING, y), footer_date, fill=DATE_COLOR, font=small_font)
        y += _s(40)

    canvas = canvas.crop((0, 0, CANVAS_W, min(y + CARD_PADDING, canvas.height)))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path
