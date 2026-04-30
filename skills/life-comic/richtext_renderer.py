"""Rich-text (Markdown) renderer for Life Comic.

Produces Markdown compatible with the BeeAI chat frontend (Copilot block format: markdown).
"""

import os
from typing import Optional


def _normalize_storyboard(d: dict) -> dict:
    """Normalize alternative field names from LLM output to canonical format."""
    narrative = d.get("narrative", {})
    if "body" not in narrative:
        parts = []
        for key in ("opening", "subtitle", "summary"):
            if narrative.get(key):
                parts.append(narrative[key])
        if narrative.get("closing"):
            parts.append(narrative["closing"])
        if parts:
            narrative["body"] = " ".join(parts)
    if "footer_date" not in d:
        for alt in ("date_line", "date", "dateLine"):
            if alt in d:
                d["footer_date"] = d[alt]
                break
    for panel in d.get("panels", []):
        if "panel_index" not in panel and "panel_number" in panel:
            panel["panel_index"] = panel["panel_number"] - 1
        if "emotion_tag" not in panel:
            for alt in ("emotion", "mood", "tag"):
                if alt in panel:
                    panel["emotion_tag"] = panel[alt]
                    break
    return d


def render_comic_richtext(
    storyboard: dict,
    comic_image_path: Optional[str],
    reference_paths: list[str],
    output_path: str,
) -> str:
    """Render comic as Markdown for chat agents. Returns output path."""
    storyboard = _normalize_storyboard(storyboard)
    lang = storyboard.get("_lang", "en")
    theme = storyboard.get("theme", "\u751f\u6d3b\u6f2b\u753b" if lang == "zh" else "Life Comic")
    narrative = storyboard.get("narrative", {})
    title = narrative.get("title", theme)
    body = narrative.get("body", "")
    emotional_arc = storyboard.get("emotional_arc", "")
    panels = storyboard.get("panels", [])
    footer_date = storyboard.get("footer_date", "")
    suggested_themes = storyboard.get("suggested_themes", [])

    lines = []
    lines.append(f"# {title}")
    lines.append(f"*{theme}*")
    lines.append("")

    if comic_image_path and os.path.exists(comic_image_path):
        lines.append(f"![comic]({comic_image_path})")
        lines.append("")

    if emotional_arc:
        lines.append(f"> {emotional_arc}")
        lines.append("")

    if body:
        lines.append("---")
        lines.append("")
        lines.append(body)
        lines.append("")

    if footer_date:
        lines.append(f"*{footer_date}*")
        lines.append("")

    if suggested_themes:
        label = "\u4f60\u53ef\u80fd\u4e5f\u559c\u6b22" if lang == "zh" else "Other themes you might like"
        lines.append("---")
        lines.append(f"**{label}**: {' | '.join(suggested_themes)}")
        lines.append("")

    md = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path
