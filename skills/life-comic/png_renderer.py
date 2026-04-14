"""PNG renderer for Life Comic — screenshots the HTML output via headless browser.

Uses Playwright (Chromium) to take a full-page, 2x HiDPI screenshot of the
rendered HTML, producing a pixel-perfect long image identical to what the user
sees when opening the HTML in a browser.

Fallback: if Playwright is unavailable, falls back to Pillow-based composite.
"""

import os
from typing import Optional


def _screenshot_html(html_path: str, png_path: str, width: int = 1080, scale: int = 2) -> bool:
    """Take a full-page screenshot of an HTML file via Playwright. Returns True on success."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": 800},
                device_scale_factor=scale,
            )
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_timeout(800)
            page.screenshot(path=png_path, full_page=True)
            browser.close()
        return os.path.exists(png_path)
    except Exception as e:
        print(f"  [WARN] Playwright screenshot failed: {e}")
        return False


def _fallback_composite(storyboard: dict, comic_image_path: Optional[str], png_path: str) -> str:
    """Pillow-based fallback when Playwright is not available."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    SCALE = 2
    CANVAS_W = 1080 * SCALE
    PAD = 40 * SCALE
    BG = (255, 252, 248)
    TEXT_C = (50, 50, 50)
    ACCENT = (140, 90, 160)

    def _font(size):
        for fp in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Helvetica.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size * SCALE)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _wrap(draw, text, font, max_w):
        lines, cur = [], ""
        for ch in text:
            if draw.textbbox((0, 0), cur + ch, font=font)[2] > max_w:
                if cur: lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur: lines.append(cur)
        return lines

    narrative = storyboard.get("narrative", {})
    title = narrative.get("title", storyboard.get("theme", "Life Comic"))
    body = narrative.get("body", "")
    content_w = CANVAS_W - 2 * PAD

    tf, bf = _font(48), _font(22)
    canvas = Image.new("RGB", (CANVAS_W, 4000), BG)
    draw = ImageDraw.Draw(canvas)
    y = PAD

    for tl in _wrap(draw, title, tf, content_w):
        draw.text((PAD, y), tl, fill=ACCENT, font=tf)
        y += 55 * SCALE
    y += 20 * SCALE

    if comic_image_path and os.path.exists(comic_image_path):
        ci = ImageOps.exif_transpose(Image.open(comic_image_path))
        if ci.mode != "RGB": ci = ci.convert("RGB")
        ratio = content_w / ci.width
        ch = int(ci.height * ratio)
        ci = ci.resize((content_w, ch), Image.LANCZOS)
        canvas.paste(ci, (PAD, y))
        y += ch + 20 * SCALE

    if body:
        for ln in _wrap(draw, body, bf, content_w):
            if y + 30 * SCALE > canvas.height - PAD:
                nc = Image.new("RGB", (CANVAS_W, canvas.height + 2000), BG)
                nc.paste(canvas, (0, 0))
                canvas, draw = nc, ImageDraw.Draw(nc)
            draw.text((PAD, y), ln, fill=TEXT_C, font=bf)
            y += 30 * SCALE
        y += 20 * SCALE

    canvas = canvas.crop((0, 0, CANVAS_W, y + PAD))
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    canvas.save(png_path, "PNG")
    return png_path


def render_comic_png(
    storyboard: dict,
    comic_image_path: Optional[str],
    reference_paths: list,
    output_path: str,
    html_path: str = None,
) -> str:
    """Render comic as PNG. Uses HTML screenshot if available, otherwise Pillow fallback."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if html_path and os.path.exists(html_path):
        if _screenshot_html(html_path, output_path):
            return output_path
        print("  [INFO] Falling back to Pillow composite")

    _fallback_composite(storyboard, comic_image_path, output_path)
    return output_path
