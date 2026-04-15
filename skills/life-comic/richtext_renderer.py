"""Rich-text (Markdown) renderer for Life Comic.

Produces Markdown compatible with the BeeAI chat frontend (Copilot block format: markdown).
"""

import os
from typing import Optional


def render_comic_richtext(
    storyboard: dict,
    comic_image_path: Optional[str],
    reference_paths: list[str],
    output_path: str,
) -> str:
    """Render comic as Markdown for chat agents. Returns output path."""
    lang = storyboard.get("_lang", "en")
    theme = storyboard.get("theme", "生活漫画" if lang == "zh" else "Life Comic")
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

    lines.append("---")
    lines.append("")

    for i, panel in enumerate(panels):
        tag = panel.get("emotion_tag", "")
        desc = panel.get("scene_description", "")
        panel_label = f"第{i+1}格" if lang == "zh" else f"Panel {i+1}"
        lines.append(f"**{panel_label}** — _{tag}_")
        lines.append(f"{desc[:200]}")
        if i < len(reference_paths):
            lines.append(f"![ref {i+1}]({reference_paths[i]})")
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
        label = "你可能也喜欢" if lang == "zh" else "Other themes you might like"
        lines.append("---")
        lines.append(f"**{label}**: {' | '.join(suggested_themes)}")
        lines.append("")

    md = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path
