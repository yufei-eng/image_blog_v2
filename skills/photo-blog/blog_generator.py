#!/usr/bin/env python3
"""Blog content generation — transforms photo analysis into structured blog narrative.

Generates: title, description, insights (photo+text pairs), tips, and footer.
All content must be grounded in actual photo content — no fabrication allowed.
"""

import json
import os
import sys
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from mcp_client import MCPClient, extract_text_content


def _load_config() -> dict:
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


BLOG_GENERATION_PROMPT = """You are a content creator with both artistic sensibility and lifestyle aesthetics. Based on the following photo analysis data, generate a "Photo Blog" post.

**Core requirements**:
1. All content must be strictly based on real scenes described in the photo analysis — never fabricate
2. Writing style: warm, evocative, with literary flair — avoid dry, chronological recounting
3. Emphasize emotional resonance — let readers feel the warmth and atmosphere of the scenes
{theme_instruction}
{lang_instruction}

**Photo analysis data**:
{analysis_json}

**Selected highlight photos** (sorted by score, for the insights section):
{highlights_json}

**Output the following JSON structure**:

```json
{{
  "title": "A poetic title of 3-6 words (e.g., 'Afternoon Among the Peaks', 'Rainy Lanes & Red Broth')",
  "hero_image_index": 0,
  "description": {{
    "text": "One short atmospheric sentence, MUST be under 150 characters.",
    "image_index": 0
  }},
  "insights": [
    {{
      "text": "A short, evocative caption for this photo, MUST be under 150 characters. Think magazine caption, not paragraph.",
      "image_index": 0
    }}
  ],
  "tip": "One practical tip sentence, MUST be under 150 characters.",
  "footer_date": "YYYY-MM-DD",
  "suggested_themes": ["theme1", "theme2", "theme3"]
}}
```

**Notes**:
- **CRITICAL**: The insights array MUST contain exactly {highlight_count} items — one per highlight photo, each mapped by image_index. Do NOT skip any.
- hero_image_index points to the best hero photo in the highlights array
- description.image_index also points to the highlights array
- Title should be concise and evocative — not too long
- Each insight text must be unique, covering different dimensions of the scene
- **Important**: Titles must be creative and distinctive. Avoid overused clichés.
- **suggested_themes**: Always provide 3 alternative theme suggestions based on actual photo content (short phrases).

**HARD LENGTH CONSTRAINT (non-negotiable)**:
- description.text: MUST be under 150 characters
- Each insight text: MUST be under 150 characters
- tip: MUST be under 150 characters
- Write like a magazine caption — punchy and evocative, never an essay."""


def _detect_lang(text: str) -> str:
    """Detect language from text. Returns 'zh' if CJK characters dominate, else 'en'."""
    if not text:
        return "en"
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    return "zh" if cjk / max(len(text.replace(" ", "")), 1) > 0.15 else "en"


def generate_blog_content(
    all_analyses: List[dict],
    highlights: List[dict],
    date_str: Optional[str] = None,
    user_theme: Optional[str] = None,
    lang: Optional[str] = None,
    target_count: Optional[int] = None,
    mcp_client: Optional[MCPClient] = None,
    uploader=None,
    highlight_paths: Optional[List[str]] = None,
) -> dict:
    """Generate blog content from photo analyses and selected highlights.

    Args:
        all_analyses: Full analysis list (for context)
        highlights: Selected highlight photos with analysis
        date_str: Date string for footer (defaults to today)
        user_theme: Optional user-specified theme/style keyword
        lang: Output language ('zh' or 'en'). Auto-detected from user_theme if None.

    Returns:
        Blog content dict with title, description, insights, tip, footer
    """
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")

    highlight_count = target_count if target_count is not None else len(highlights)

    from mcp_client import create_mcp_client

    cfg = _load_config()
    own_mcp = mcp_client is None
    if own_mcp:
        mcp_client = create_mcp_client(cfg)
        mcp_client.connect()

    analysis_summary = []
    for a in all_analyses[:30]:
        analysis_summary.append({
            "scene": a.get("scene", ""),
            "mood": a.get("mood", ""),
            "location": a.get("location", ""),
            "action": a.get("action", ""),
        })

    highlights_detail = []
    for i, h in enumerate(highlights):
        highlights_detail.append({
            "index": i,
            "scene": h.get("scene", ""),
            "people": h.get("people", ""),
            "action": h.get("action", ""),
            "mood": h.get("mood", ""),
            "location": h.get("location", ""),
            "objects": h.get("objects", ""),
            "narrative_hook": h.get("narrative_hook", ""),
            "score": h.get("score", 0),
        })

    if lang is None:
        lang = _detect_lang(user_theme or "")

    theme_instruction = ""
    if user_theme:
        theme_instruction = f"""
4. **User requested theme**: '{user_theme}'. Prioritize this theme in the title and narrative.
   If fewer than 2 photos match this theme, ignore it and use the best theme from the actual content.
   In that case, the suggested_themes field becomes especially important — offer 3 themes that DO match the photos."""

    lang_instruction = ""
    if lang == "zh":
        lang_instruction = """
**Language requirement**: The user speaks Chinese. ALL generated text (title, description, insights, tip, suggested_themes) MUST be written in Simplified Chinese. Use warm, literary Chinese style."""
    else:
        lang_instruction = """
**Language requirement**: Write all text in English."""

    prompt = BLOG_GENERATION_PROMPT.format(
        analysis_json=json.dumps(analysis_summary, ensure_ascii=False, indent=2),
        highlights_json=json.dumps(highlights_detail, ensure_ascii=False, indent=2),
        theme_instruction=theme_instruction,
        lang_instruction=lang_instruction,
        highlight_count=highlight_count,
    )

    image_urls = []
    if highlight_paths and uploader:
        from image_analyzer import _load_image_bytes_fixed
        for hp in highlight_paths[:5]:
            try:
                img_data, mime = _load_image_bytes_fixed(hp)
                fname = os.path.basename(hp).rsplit(".", 1)[0] + ".jpg"
                url = uploader.upload_bytes(img_data, fname, mime)
                image_urls.append(url)
            except Exception as e:
                print(f"  [WARN] Upload failed for blog visual context: {e}")

    if not image_urls:
        print("  [WARN] No highlight images uploaded, using fallback content")
        return _fallback_content(highlights, date_str, lang)

    try:
        try:
            result = mcp_client.call_tool("batch_understand_images", {
                "prompt": prompt,
                "image_urls": image_urls,
            })
        except Exception as e:
            print(f"ERROR: Blog generation failed: {e}")
            return _fallback_content(highlights, date_str, lang)

        text = extract_text_content(result)

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            blog = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    blog = json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    print(f"  [WARN] Failed to parse blog JSON, using fallback")
                    return _fallback_content(highlights, date_str, lang)
            else:
                return _fallback_content(highlights, date_str, lang)

        blog["footer_date"] = date_str
        blog["_lang"] = lang

        _enforce_char_limits(blog)
        return blog
    finally:
        if own_mcp:
            mcp_client.close()


def _truncate_at_sentence(text: str, limit: int) -> str:
    """Truncate text at the last complete sentence within the limit."""
    if len(text) <= limit:
        return text
    candidate = text[:limit]
    for sep in [". ", "。", "! ", "? ", "！", "？"]:
        pos = candidate.rfind(sep)
        if pos > 0:
            return candidate[:pos + len(sep)].rstrip()
    return candidate.rsplit(" ", 1)[0] + "…"


def _enforce_char_limits(blog: dict, limit: int = 150):
    """Truncate text fields at sentence boundaries if they exceed the limit."""
    desc = blog.get("description", {})
    if isinstance(desc, dict) and len(desc.get("text", "")) > limit:
        desc["text"] = _truncate_at_sentence(desc["text"], limit)
    for ins in blog.get("insights", []):
        if len(ins.get("text", "")) > limit:
            ins["text"] = _truncate_at_sentence(ins["text"], limit)
    if len(blog.get("tip", "")) > limit:
        blog["tip"] = _truncate_at_sentence(blog["tip"], limit)


def _fallback_content(highlights: List[dict], date_str: str, lang: str = "en") -> dict:
    """Minimal fallback when LLM generation fails."""
    insights = []
    for i, h in enumerate(highlights[:10]):
        insights.append({
            "text": h.get("narrative_hook", h.get("scene", "\u7cbe\u5f69\u77ac\u95f4" if lang == "zh" else "A wonderful moment")),
            "image_index": i,
        })
    if lang == "zh":
        return {
            "title": "\u4eca\u65e5\u4e00\u7a25",
            "hero_image_index": 0,
            "description": {"text": "\u6355\u6349\u751f\u6d3b\u4e2d\u7684\u7f8e\u597d\u77ac\u95f4\u2014\u2014\u6bcf\u4e00\u5e27\u90fd\u503c\u5f97\u73cd\u85cf\u3002", "image_index": 0},
            "insights": insights,
            "tip": "\u73cd\u60dc\u5f53\u4e0b\uff0c\u8bb0\u5f55\u7f8e\u597d\u2014\u2014\u6e29\u6696\u85cf\u5728\u7ec6\u8282\u91cc\u3002",
            "footer_date": date_str,
            "_lang": lang,
        }
    return {
        "title": "Today's Glimpse",
        "hero_image_index": 0,
        "description": {"text": "Capturing life's beautiful moments — every frame is worth treasuring.", "image_index": 0},
        "insights": insights,
        "tip": "Savor the present, capture the beauty — warmth lives in the details.",
        "footer_date": date_str,
        "_lang": lang,
    }
