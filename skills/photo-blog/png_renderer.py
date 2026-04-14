"""PNG renderer for Photo Blog — screenshots the HTML output via headless browser.

Uses Playwright (Chromium) to take a full-page, 2x HiDPI screenshot of the
rendered HTML, producing a pixel-perfect long image identical to what the user
sees when opening the HTML in a browser.

Fallback: if Playwright is unavailable, falls back to Pillow-based composite.
"""

import os
import subprocess
import sys


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


def _fallback_composite(blog_content: dict, highlight_paths: list, png_path: str) -> str:
    """Pillow-based fallback when Playwright is not available."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    SCALE = 2
    CANVAS_W = 1080 * SCALE
    PAD = 40 * SCALE
    BG = (255, 252, 248)
    TEXT_C = (50, 50, 50)
    ACCENT = (180, 120, 70)

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

    title = blog_content.get("title", "Photo Blog")
    desc = blog_content.get("description", {}).get("text", "")
    insights = blog_content.get("insights", [])
    content_w = CANVAS_W - 2 * PAD

    tf, bf = _font(48), _font(24)
    canvas = Image.new("RGB", (CANVAS_W, 4000), BG)
    draw = ImageDraw.Draw(canvas)
    y = PAD

    for tl in _wrap(draw, title, tf, content_w):
        draw.text((PAD, y), tl, fill=ACCENT, font=tf)
        y += 55 * SCALE
    y += 20 * SCALE

    if desc:
        for dl in _wrap(draw, desc, bf, content_w):
            draw.text((PAD, y), dl, fill=TEXT_C, font=bf)
            y += 32 * SCALE
        y += 20 * SCALE

    n = len(highlight_paths)
    cols = 1 if n <= 1 else (2 if n <= 4 else 3)
    pw = (content_w - (cols - 1) * 16 * SCALE) // cols
    ph = int(pw * 0.75)
    for idx, path in enumerate(highlight_paths):
        r, c = divmod(idx, cols)
        px = PAD + c * (pw + 16 * SCALE)
        py = y + r * (ph + 16 * SCALE)
        try:
            img = ImageOps.exif_transpose(Image.open(path))
            if img.mode != "RGB": img = img.convert("RGB")
            canvas.paste(ImageOps.fit(img, (pw, ph), Image.LANCZOS), (px, py))
        except Exception:
            pass
    rows = (n + cols - 1) // cols
    y += rows * ph + (rows - 1) * 16 * SCALE + 30 * SCALE

    for i, ins in enumerate(insights):
        for ln in _wrap(draw, f"{i+1}. {ins.get('text', '')}", bf, content_w):
            if y + 32 * SCALE > canvas.height - PAD:
                nc = Image.new("RGB", (CANVAS_W, canvas.height + 2000), BG)
                nc.paste(canvas, (0, 0))
                canvas, draw = nc, ImageDraw.Draw(nc)
            draw.text((PAD, y), ln, fill=TEXT_C, font=bf)
            y += 32 * SCALE
        y += 12 * SCALE

    canvas = canvas.crop((0, 0, CANVAS_W, y + PAD))
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    canvas.save(png_path, "PNG")
    return png_path


def render_blog_png(blog_content: dict, highlight_paths: list, output_path: str, html_path: str = None) -> str:
    """Render blog as PNG. Uses HTML screenshot if available, otherwise Pillow fallback."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if html_path and os.path.exists(html_path):
        if _screenshot_html(html_path, output_path):
            return output_path
        print("  [INFO] Falling back to Pillow composite")

    _fallback_composite(blog_content, highlight_paths, output_path)
    return output_path
