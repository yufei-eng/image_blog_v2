#!/usr/bin/env python3
"""Blog content generation — transforms photo analysis into structured blog narrative.

Generates: title, description, insights (photo+text pairs), tips, and footer.
All content must be grounded in actual photo content — no fabrication allowed.
"""

import json
import os
import sys
from typing import Dict, List, Optional

from google import genai
from google.genai import types

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_config() -> dict:
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def _get_client(cfg: dict):
    api_cfg = cfg.get("compass_api", {})
    token = os.environ.get("COMPASS_CLIENT_TOKEN", api_cfg.get("client_token", ""))
    base_url = api_cfg.get("base_url", "")
    return genai.Client(api_key=token, http_options=types.HttpOptions(base_url=base_url))


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
    "text": "A coherent 2-4 sentence narrative covering time, place, actions, and atmosphere, in an evocative, warm style",
    "image_index": 0
  }},
  "insights": [
    {{
      "text": "A 2-3 sentence insight for this photo, describing scene details and reflections with vivid imagery",
      "image_index": 0
    }}
  ],
  "tip": "A 1-2 sentence personalized practical tip based on the scene (outdoor/indoor/food/travel etc.)",
  "footer_date": "YYYY-MM-DD",
  "suggested_themes": ["theme1", "theme2", "theme3"]
}}
```

**Notes**:
- The insights array should contain one item per highlight photo (up to 9), each mapped by image_index
- hero_image_index points to the best hero photo in the highlights array
- description.image_index also points to the highlights array
- Title should be concise and evocative — not too long
- Each insight text must be unique, with different focus areas covering various scene dimensions
- **Important**: Titles must be creative and distinctive. Avoid overused clichés. Draw unique imagery from the photo scenes — landscapes, culinary memories, light and shadow, travel moods, etc.
- **suggested_themes**: Always provide 3 alternative theme suggestions based on actual photo content (short phrases). These help the user explore different angles."""


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

    cfg = _load_config()
    client = _get_client(cfg)
    model = cfg.get("compass_api", {}).get("understanding_model", "gemini-3-pro-image-preview")

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
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(response_modalities=["TEXT"], temperature=0.7),
        )
    except Exception as e:
        print(f"ERROR: Blog generation failed: {e}")
        return _fallback_content(highlights, date_str, lang)

    text = ""
    for part in response.candidates[0].content.parts:
        if part.text:
            text += part.text

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
    return blog


def _fallback_content(highlights: List[dict], date_str: str, lang: str = "en") -> dict:
    """Minimal fallback when LLM generation fails."""
    insights = []
    for i, h in enumerate(highlights[:9]):
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
