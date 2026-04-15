"""Rich-text (Markdown) renderer for Photo Blog.

Produces Markdown compatible with the BeeAI chat frontend (Copilot block format: markdown).
The output uses standard Markdown syntax that renders in chat agent windows.
"""

import base64
import os
from typing import Optional
from PIL import Image, ImageOps


def _img_to_base64_url(path: str, max_w: int = 600) -> str:
    """Convert image to inline base64 data URL for embedding in Markdown."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


_LABELS = {
    "en": {"tip": "Tip", "other_themes": "Other themes you might like", "default_title": "Photo Blog"},
    "zh": {"tip": "\u5c0f\u63d0\u9192", "other_themes": "\u4f60\u53ef\u80fd\u4e5f\u559c\u6b22", "default_title": "\u56fe\u6587\u535a\u5ba2"},
}


def render_blog_richtext(blog_content: dict, highlight_paths: list[str], output_path: str) -> str:
    """Render blog content as Markdown suitable for chat agents.

    Returns the output file path.
    """
    lang = blog_content.get("_lang", "en")
    L = _LABELS.get(lang, _LABELS["en"])
    title = blog_content.get("title", L["default_title"])
    desc = blog_content.get("description", {})
    insights = blog_content.get("insights", [])
    tip = blog_content.get("tip", "")
    footer_date = blog_content.get("footer_date", "")
    suggested_themes = blog_content.get("suggested_themes", [])

    lines = []
    lines.append(f"# {title}")
    lines.append("")

    hero_idx = blog_content.get("hero_image_index", 0)
    if hero_idx < len(highlight_paths):
        lines.append(f"![hero]({highlight_paths[hero_idx]})")
        lines.append("")

    if desc.get("text"):
        lines.append(f"> {desc['text']}")
        lines.append("")

    lines.append("---")
    lines.append("")

    for i, insight in enumerate(insights):
        text = insight.get("text", "")
        img_idx = insight.get("image_index", i)
        lines.append(f"### {i+1}.")
        lines.append(f"{text}")
        if img_idx < len(highlight_paths):
            lines.append(f"![photo {i+1}]({highlight_paths[img_idx]})")
        lines.append("")

    if tip:
        lines.append("---")
        lines.append(f"**{L['tip']}**: {tip}")
        lines.append("")

    if footer_date:
        lines.append(f"*{footer_date}*")
        lines.append("")

    if suggested_themes:
        lines.append("---")
        lines.append(f"**{L['other_themes']}**: {' | '.join(suggested_themes)}")
        lines.append("")

    md = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path
