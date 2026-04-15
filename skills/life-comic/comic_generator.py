#!/usr/bin/env python3
"""Comic generator — storyboard script + Gemini 3.1 Flash Image comic generation.

Generates:
1. Narrative theme and emotional arc
2. Per-panel comic descriptions
3. Multi-panel comic image via Gemini 3.1 Flash Image (with reference photos)
4. Emotional narrative text (title + body)
"""

import json
import math
import os
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

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


def _load_image_bytes(path: str, max_pixels: int = 800 * 800) -> Tuple[bytes, str]:
    """Load image with EXIF orientation fix, resize, return JPEG bytes."""
    try:
        from PIL import Image, ImageOps
        import io
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w, h = img.size
        if w * h > max_pixels:
            ratio = math.sqrt(max_pixels / (w * h))
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        with open(path, "rb") as f:
            return f.read(), "image/jpeg"


# ── Step 1: Generate storyboard and narrative ──

STORYBOARD_PROMPT = """You are a warm, heartfelt comic scriptwriter. Based on the following photo analysis data (extracted from real photos), create a life-comic storyboard script and emotional narrative.

**Core requirements**:
1. All comic scenes must be adapted from real photo content — never fabricate scenes that don't exist
2. Emotional tone: warm and heartfelt, can be tender or passionate, avoid being overly detached
3. Comic style: warm hand-drawn illustration, soft but layered colors
{theme_instruction}
{lang_instruction}

**Theme creativity requirements (extremely important)**:
- The theme must be creative and distinctive. Avoid generic clichés
- Extract unique emotional themes from the photo scenes, for example: discovery & wonder, a culinary journey, dialogue of light & shadow, city rhythms, a wanderer's diary, flavor atlas, stories under the eaves, etc.
- Title style can be poetic, playful, or philosophical, but never repetitive

**Selected comic material** (highlight moments sorted by score):
{panels_json}

**Output the following JSON structure**:

```json
{{
  "theme": "A 2-6 word theme (e.g., 'Through the Seasons Together', 'Spice & Starlight')",
  "emotional_arc": "One sentence describing the emotional arc (e.g., from city to wilderness, from hustle to calm)",
  "panels": [
    {{
      "panel_index": 0,
      "source_photo_index": 0,
      "scene_description": "Detailed visual description for this comic panel (3-5 sentences), including characters, actions, environment, lighting, color tone",
      "emotion_tag": "A 2-4 word emotion tag (e.g., 'dusk stroll', 'summit gaze')",
      "panel_composition": "Composition suggestion (e.g., 'bird's-eye view / wide shot / close-up')"
    }}
  ],
  "narrative": {{
    "title": "Title (matching the theme)",
    "body": "A 100-200 word emotional narrative. Correspond to each panel, giving each scene emotional value. End with an uplifting reflection that resonates. Write as cohesive prose, not a labeled list."
  }},
  "footer_date": "YYYY-MM-DD",
  "suggested_themes": ["theme1", "theme2", "theme3"]
}}
```

**Notes**:
- panels array source_photo_index corresponds to the input material index
- scene_description is a detailed instruction for the comic artist — include sufficient visual detail
- narrative.body should have literary quality — avoid list-style writing
- **suggested_themes**: Always provide 3 alternative theme suggestions based on actual photo content"""


def _detect_lang(text: str) -> str:
    """Detect language from text. Returns 'zh' if CJK characters dominate, else 'en'."""
    if not text:
        return "en"
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    return "zh" if cjk / max(len(text.replace(" ", "")), 1) > 0.15 else "en"


def generate_storyboard(panel_moments: List[dict], date_str: Optional[str] = None, user_theme: Optional[str] = None, lang: Optional[str] = None) -> dict:
    """Generate storyboard script and narrative text."""
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")

    cfg = _load_config()
    client = _get_client(cfg)
    model = cfg.get("compass_api", {}).get("understanding_model", "gemini-3-pro-image-preview")

    panels_detail = []
    for i, m in enumerate(panel_moments):
        panels_detail.append({
            "index": i,
            "scene": m.get("scene_summary", ""),
            "character": m.get("character_desc", ""),
            "action": m.get("action_desc", ""),
            "emotion": m.get("emotion", ""),
            "environment": m.get("environment", ""),
            "time_of_day": m.get("time_of_day", ""),
            "comic_panel_desc": m.get("comic_panel_desc", ""),
        })

    if lang is None:
        lang = _detect_lang(user_theme or "")

    theme_instruction = ""
    if user_theme:
        theme_instruction = f"""
4. **User requested theme**: '{user_theme}'. Use this as the comic's central theme if the photos support it.
   If fewer than 2 photos match, ignore and use the best theme from actual content.
   Provide helpful alternative themes in suggested_themes."""

    lang_instruction = ""
    if lang == "zh":
        lang_instruction = """
**Language requirement**: The user speaks Chinese. ALL generated text (theme, emotional_arc, narrative title/body, emotion_tags, suggested_themes) MUST be written in Chinese (简体中文). Use warm, literary Chinese style. Note: scene_description should remain in English as it is used for image generation prompts."""
    else:
        lang_instruction = """
**Language requirement**: Write all user-facing text in English. scene_description should also be in English."""

    prompt = STORYBOARD_PROMPT.format(
        panels_json=json.dumps(panels_detail, ensure_ascii=False, indent=2),
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
        print(f"ERROR: Storyboard generation failed: {e}")
        return _fallback_storyboard(panel_moments, date_str, lang)

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
        sb = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                sb = json.loads(text[start:end+1])
            except json.JSONDecodeError:
                return _fallback_storyboard(panel_moments, date_str, lang)
        else:
            return _fallback_storyboard(panel_moments, date_str, lang)

    sb["footer_date"] = date_str
    sb["_lang"] = lang
    return sb


# ── Step 2: Generate comic-style multi-panel image ──

COMIC_IMAGE_PROMPT_TEMPLATE = """Generate a warm, hand-drawn illustration style comic strip with {panel_count} panels arranged in a grid layout. The style should be gentle watercolor-meets-digital-illustration, with soft warm tones, slightly rounded character designs, and cozy atmosphere — similar to a "slice of life" manga or children's picture book.

Overall theme: "{theme}"
Emotional arc: "{emotional_arc}"

Panel descriptions (in order, left-to-right, top-to-bottom):
{panel_descriptions}

CRITICAL REQUIREMENTS:
- All {panel_count} panels must be in a SINGLE image, arranged as a {grid_layout} grid
- Each panel should have a thin white border/frame separating it
- Consistent character appearance across panels (same clothing, hair, build)
- Warm color palette: golden yellows, soft oranges, gentle greens, twilight purples
- Hand-drawn line quality with subtle texture
- No text or speech bubbles in the panels
- Aspect ratio: 3:4 portrait (for the overall grid image)
- The overall mood should be warm, nostalgic, and life-affirming

Style anchor: A warm slice-of-life comic strip with gentle watercolor illustration style, evoking the feeling of a cherished photo album rendered as art."""


def generate_comic_image(
    storyboard: dict,
    reference_photos: List[str],
    output_dir: str = ".",
) -> Optional[str]:
    """Generate the multi-panel comic image using Gemini 3.1 Flash Image.

    Uses reference photos to maintain visual grounding in real scenes.
    """
    cfg = _load_config()
    client = _get_client(cfg)
    gen_model = cfg.get("compass_api", {}).get("generation_model", "gemini-3.1-flash-image-preview")

    panels = storyboard.get("panels", [])
    panel_count = len(panels)
    theme = storyboard.get("theme", "Life Comic")
    emotional_arc = storyboard.get("emotional_arc", "")

    grid_map = {1: "1x1", 2: "1x2", 3: "1x3", 4: "2x2", 5: "2x3", 6: "2x3", 7: "2x4", 8: "2x4", 9: "3x3"}
    grid_layout = grid_map.get(panel_count, "2x3")

    panel_descs = ""
    for i, p in enumerate(panels):
        desc = p.get("scene_description", "")
        emotion_tag = p.get("emotion_tag", "")
        composition = p.get("panel_composition", "")
        panel_descs += f"\nPanel {i+1} ({emotion_tag}): {desc} Composition: {composition}."

    prompt = COMIC_IMAGE_PROMPT_TEMPLATE.format(
        panel_count=panel_count,
        theme=theme,
        emotional_arc=emotional_arc,
        panel_descriptions=panel_descs,
        grid_layout=grid_layout,
    )

    parts: list[types.Part] = []

    ref_count = min(len(reference_photos), 9)
    for rp in reference_photos[:ref_count]:
        try:
            img_data, mime = _load_image_bytes(rp)
            parts.append(types.Part.from_bytes(data=img_data, mime_type=mime))
        except Exception as e:
            print(f"  [WARN] Failed to load reference photo {rp}: {e}")

    parts.append(types.Part.from_text(text=prompt))

    print(f"  Calling {gen_model} with {ref_count} reference photos...")

    try:
        response = client.models.generate_content(
            model=gen_model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
    except Exception as e:
        print(f"  ERROR: Comic image generation failed: {e}")
        return None

    if not response.candidates:
        print("  No candidates returned")
        return None

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            mime = part.inline_data.mime_type or "image/png"
            ext_map = {"image/png": ".png", "image/webp": ".webp"}
            ext = ext_map.get(mime, ".png")
            filename = f"comic_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(part.inline_data.data)
            size_kb = len(part.inline_data.data) / 1024
            print(f"  Comic image saved: {os.path.abspath(filepath)} ({size_kb:.1f} KB)")
            return os.path.abspath(filepath)

    print("  No image in response")
    return None


def _fallback_storyboard(panels: List[dict], date_str: str, lang: str = "en") -> dict:
    """Minimal fallback storyboard."""
    panel_list = []
    for i, p in enumerate(panels[:9]):
        panel_list.append({
            "panel_index": i,
            "source_photo_index": i,
            "scene_description": p.get("comic_panel_desc", p.get("scene_summary", "")),
            "emotion_tag": p.get("emotion", "温暖" if lang == "zh" else "warmth"),
            "panel_composition": "medium shot",
        })
    if lang == "zh":
        return {
            "theme": "生活碎片",
            "emotional_arc": "平凡日常中的温柔时刻",
            "panels": panel_list,
            "narrative": {"title": "生活碎片", "body": "每一个平凡的日子里，都有值得珍藏的温柔瞬间。"},
            "footer_date": date_str,
            "_lang": lang,
        }
    return {
        "theme": "Life Fragments",
        "emotional_arc": "Beauty found in the everyday",
        "panels": panel_list,
        "narrative": {"title": "Life Fragments", "body": "In every ordinary day, there are gentle moments worth remembering."},
        "footer_date": date_str,
        "_lang": lang,
    }
