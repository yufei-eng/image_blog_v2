#!/usr/bin/env python3
"""HTML renderer for photo blog — dark theme card layout inspired by Looki app."""

import base64
import math
import os
from typing import Dict, List, Optional


def _img_to_base64(path: str, max_width: int = 800) -> str:
    """Convert image to base64 with EXIF orientation fix and resize."""
    try:
        from PIL import Image, ImageOps
        import io
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


def render_blog_html(
    blog_content: dict,
    highlight_paths: List[str],
    output_path: str = "blog_output.html",
) -> str:
    """Render blog content to a self-contained HTML file.

    Args:
        blog_content: Generated blog dict (title, description, insights, tip, etc.)
        highlight_paths: File paths of highlight images (ordered by selection)
        output_path: Where to save the HTML file

    Returns:
        Absolute path to the generated HTML file
    """
    title = blog_content.get("title", "今日掠影")
    desc = blog_content.get("description", {})
    desc_text = desc.get("text", "") if isinstance(desc, dict) else str(desc)
    hero_idx = blog_content.get("hero_image_index", 0)
    insights = blog_content.get("insights", [])
    tip = blog_content.get("tip", "")
    footer_date = blog_content.get("footer_date", "")

    hero_b64 = ""
    if highlight_paths and hero_idx < len(highlight_paths):
        hero_b64 = _img_to_base64(highlight_paths[hero_idx], max_width=1000)

    insight_blocks = []
    for ins in insights:
        idx = ins.get("image_index", 0)
        text = ins.get("text", "")
        img_b64 = ""
        if idx < len(highlight_paths):
            img_b64 = _img_to_base64(highlight_paths[idx], max_width=600)
        insight_blocks.append({"text": text, "img_b64": img_b64})

    insights_html = ""
    for i, block in enumerate(insight_blocks):
        img_tag = f'<img src="data:image/jpeg;base64,{block["img_b64"]}" alt="insight-{i}" class="insight-img" loading="lazy">' if block["img_b64"] else ""
        is_reverse = "reverse" if i % 2 == 1 else ""
        insights_html += f"""
        <div class="insight-card {is_reverse}">
            <div class="insight-text"><p>{block["text"]}</p></div>
            <div class="insight-image">{img_tag}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — 片刻感悟</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0a0a0f;
    color: #e8e8ec;
    font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.8;
    max-width: 480px;
    margin: 0 auto;
    padding: 0;
    min-height: 100vh;
}}
.page {{
    padding: 24px 20px 40px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}}
.hero-section {{
    position: relative;
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 24px;
}}
.hero-img {{
    width: 100%;
    display: block;
    border-radius: 16px;
    filter: brightness(0.85);
}}
.hero-overlay {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 32px 20px 20px;
    background: linear-gradient(transparent, rgba(0,0,0,0.85));
}}
h1 {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 16px;
    color: #ffffff;
}}
.desc-text {{
    font-size: 15px;
    color: #c8c8d0;
    line-height: 1.9;
    margin-bottom: 24px;
    padding: 0 4px;
}}
.section-title {{
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 16px;
    padding-left: 12px;
    border-left: 3px solid #5b9bd5;
}}
.insight-card {{
    display: flex;
    gap: 14px;
    margin-bottom: 20px;
    align-items: flex-start;
}}
.insight-card.reverse {{
    flex-direction: row-reverse;
}}
.insight-text {{
    flex: 1;
    font-size: 14px;
    color: #b8b8c4;
    line-height: 1.85;
    padding-top: 4px;
}}
.insight-image {{
    flex: 0 0 140px;
}}
.insight-img {{
    width: 140px;
    height: 105px;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08);
}}
.tip-box {{
    background: rgba(91, 155, 213, 0.08);
    border: 1px solid rgba(91, 155, 213, 0.2);
    border-radius: 12px;
    padding: 16px 18px;
    margin-top: 24px;
}}
.tip-title {{
    font-size: 16px;
    font-weight: 600;
    color: #5b9bd5;
    margin-bottom: 8px;
}}
.tip-text {{
    font-size: 14px;
    color: #a0a0b0;
    line-height: 1.8;
}}
.footer {{
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid rgba(255,255,255,0.06);
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #666;
    font-size: 12px;
}}
.footer-label {{
    color: #5b9bd5;
    font-weight: 500;
}}
</style>
</head>
<body>

<div class="page">
    <div class="hero-section">
        {"<img src='data:image/jpeg;base64," + hero_b64 + "' alt='hero' class='hero-img'>" if hero_b64 else ""}
        <div class="hero-overlay">
            <h1>{title}</h1>
        </div>
    </div>

    <p class="desc-text">{desc_text}</p>

    <div class="section-title">洞察</div>
    {insights_html}

    <div class="tip-box">
        <div class="tip-title">小建议</div>
        <div class="tip-text">{tip}</div>
    </div>

    <div class="footer">
        <span class="footer-label">片刻感悟</span>
        <span>{footer_date}</span>
    </div>
</div>

</body>
</html>"""

    abs_path = os.path.abspath(output_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html)
    return abs_path
