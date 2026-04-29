#!/usr/bin/env python3
"""HTML renderer for life comic — comic grid + narrative text layout."""

import base64
import os
from typing import Dict, List, Optional


def _img_to_base64(path: str, max_width: int = 1000) -> tuple[str, str]:
    """Convert image to base64. Returns (base64_str, mime_type)."""
    try:
        from PIL import Image, ImageOps
        import io
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
    except Exception as e:
        print(f"  [WARN] PIL failed for {os.path.basename(path)}: {e}")
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "gif": "image/gif"}
        mime = mime_map.get(ext, "image/png")
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), mime


def render_comic_html(
    storyboard: dict,
    comic_image_path: Optional[str],
    reference_photo_paths: List[str],
    output_path: str = "comic_output.html",
) -> str:
    """Render comic to self-contained HTML.

    Args:
        storyboard: Generated storyboard dict with theme, narrative, panels
        comic_image_path: Path to generated comic grid image (may be None)
        reference_photo_paths: Original reference photo paths (fallback display)
        output_path: Where to save HTML

    Returns:
        Absolute path to generated HTML file
    """
    lang = storyboard.get("_lang", "en")
    brand = "\u751f\u6d3b\u6f2b\u753b" if lang == "zh" else "Life Comic"
    theme = storyboard.get("theme", brand)
    narrative = storyboard.get("narrative", {})
    title = narrative.get("title", f"《{theme}》")
    body = narrative.get("body", "")
    footer_date = storyboard.get("footer_date", "")
    panels = storyboard.get("panels", [])

    comic_b64, comic_mime = "", "image/jpeg"
    if comic_image_path and os.path.exists(comic_image_path):
        comic_b64, comic_mime = _img_to_base64(comic_image_path, max_width=1200)

    fallback_gallery = ""
    if not comic_b64 and reference_photo_paths:
        imgs_html = ""
        for i, pp in enumerate(reference_photo_paths[:6]):
            b64, mime = _img_to_base64(pp, max_width=400)
            emotion_tag = panels[i].get("emotion_tag", "") if i < len(panels) else ""
            imgs_html += f"""
            <div class="fallback-panel">
                <img src="data:{mime};base64,{b64}" alt="panel-{i}" class="fallback-img">
                <span class="panel-tag">{emotion_tag}</span>
            </div>"""
        fallback_gallery = f'<div class="fallback-grid">{imgs_html}</div>'

    comic_section = ""
    if comic_b64:
        comic_section = f'<img src="data:{comic_mime};base64,{comic_b64}" alt="comic" class="comic-img">'
    elif fallback_gallery:
        comic_section = fallback_gallery

    html_lang = "zh-CN" if lang == "zh" else "en"
    html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {brand}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0c0c14;
    color: #e0e0e8;
    font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.8;
    max-width: 480px;
    margin: 0 auto;
    padding: 0;
}}
.container {{
    padding: 24px 20px 48px;
}}
.comic-section {{
    margin-bottom: 28px;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}}
.comic-img {{
    width: 100%;
    display: block;
    border-radius: 16px;
}}
.fallback-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    border-radius: 16px;
    overflow: hidden;
}}
.fallback-panel {{
    position: relative;
    overflow: hidden;
    border-radius: 8px;
}}
.fallback-img {{
    width: 100%;
    height: 160px;
    object-fit: cover;
    display: block;
    filter: saturate(0.6) contrast(1.1);
    border: 2px solid rgba(255,255,255,0.1);
    border-radius: 8px;
}}
.panel-tag {{
    position: absolute;
    bottom: 6px;
    left: 8px;
    background: rgba(0,0,0,0.65);
    color: #d0d0e0;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
}}
.narrative-section {{
    padding: 0 4px;
}}
h1 {{
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 18px;
    letter-spacing: 1px;
}}
.narrative-body {{
    font-size: 15px;
    color: #b0b0c0;
    line-height: 2.0;
    text-align: justify;
    margin-bottom: 28px;
}}
.footer {{
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid rgba(255,255,255,0.06);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: #555;
}}
.footer-label {{
    color: #6b8fbe;
    font-weight: 500;
}}
</style>
</head>
<body>

<div class="container">
    <div class="comic-section">
        {comic_section}
    </div>

    <div class="narrative-section">
        <h1>{title}</h1>
        <p class="narrative-body">{body}</p>
    </div>

    <div class="footer">
        <span class="footer-label">{brand}</span>
        <span>{footer_date}</span>
    </div>
</div>

</body>
</html>"""

    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html)
    return abs_path
