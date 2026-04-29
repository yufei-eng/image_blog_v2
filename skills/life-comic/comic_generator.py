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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from mcp_client import MCPClient, extract_text_content
from file_uploader import FileUploader
from image_downloader import extract_image_urls, download_image


def _load_config() -> dict:
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    alt_path = os.path.expanduser("~/.claude/skills/life-comic/config.json")
    for p in [config_path, alt_path]:
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return {}


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
    "body": "A poetic narrative under 250 characters (roughly 30-40 words). Capture the emotional essence in one flowing impression — NOT a panel-by-panel recap."
  }},
  "footer_date": "YYYY-MM-DD",
  "suggested_themes": ["theme1", "theme2", "theme3"]
}}
```

**HARD LENGTH CONSTRAINTS (non-negotiable)**:
- narrative.body: MUST be under 250 characters. Count carefully — 250 characters is about 2 short sentences.
- emotional_arc: MUST be under 100 characters.
- If in doubt, write SHORTER. A haiku-length impression beats an essay every time.

**Notes**:
- **CRITICAL**: The panels array MUST contain exactly {panel_count} items — one panel for each input moment. Do NOT skip, merge, or omit any.
- panels array source_photo_index corresponds to the input material index
- scene_description is a detailed instruction for the comic artist — include sufficient visual detail (this is NOT shown to users)
- narrative.body should have literary quality — avoid list-style writing
- **suggested_themes**: Always provide 3 alternative theme suggestions based on actual photo content"""


def _detect_lang(text: str) -> str:
    """Detect language from text. Returns 'zh' if CJK characters dominate, else 'en'."""
    if not text:
        return "en"
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    return "zh" if cjk / max(len(text.replace(" ", "")), 1) > 0.15 else "en"


def generate_storyboard(panel_moments: List[dict], date_str: Optional[str] = None, user_theme: Optional[str] = None, lang: Optional[str] = None, target_panel_count: Optional[int] = None, mcp_client: Optional[MCPClient] = None, uploader: Optional[FileUploader] = None, panel_photo_paths: Optional[List[str]] = None) -> dict:
    """Generate storyboard script and narrative text."""
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")

    panel_count = target_panel_count if target_panel_count is not None else len(panel_moments)

    from mcp_client import create_mcp_client

    cfg = _load_config()
    own_mcp = mcp_client is None
    if own_mcp:
        mcp_client = create_mcp_client(cfg)
        mcp_client.connect()

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
**Language requirement**: The user speaks Chinese. ALL generated text (theme, emotional_arc, narrative title/body, emotion_tags, suggested_themes) MUST be written in Simplified Chinese. Use warm, literary Chinese style. Note: scene_description should remain in English as it is used for image generation prompts."""
    else:
        lang_instruction = """
**Language requirement**: Write all user-facing text in English. scene_description should also be in English."""

    prompt = STORYBOARD_PROMPT.format(
        panels_json=json.dumps(panels_detail, ensure_ascii=False, indent=2),
        theme_instruction=theme_instruction,
        lang_instruction=lang_instruction,
        panel_count=panel_count,
    )

    image_urls = []
    if panel_photo_paths and uploader:
        for pp in panel_photo_paths[:8]:
            try:
                img_data, mime = _load_image_bytes(pp)
                fname = os.path.basename(pp).rsplit(".", 1)[0] + ".jpg"
                url = uploader.upload_bytes(img_data, fname, mime)
                image_urls.append(url)
            except Exception as e:
                print(f"  [WARN] Upload failed for storyboard visual context: {e}")

    if not image_urls:
        print("  [WARN] No panel images uploaded, using fallback storyboard")
        return _fallback_storyboard(panel_moments, date_str, lang)

    try:
        try:
            result = mcp_client.call_tool("image_understand", {
                "prompt": prompt,
                "image_urls": image_urls,
            })
        except Exception as e:
            print(f"ERROR: Storyboard generation failed: {e}")
            return _fallback_storyboard(panel_moments, date_str, lang)

        text = extract_text_content(result)

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

        _enforce_narrative_limits(sb)
        return sb
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


def _enforce_narrative_limits(sb: dict):
    """Truncate narrative fields at sentence boundaries if they exceed limits."""
    narr = sb.get("narrative", {})
    body = narr.get("body", "")
    if len(body) > 250:
        narr["body"] = _truncate_at_sentence(body, 250)
    arc = sb.get("emotional_arc", "")
    if len(arc) > 100:
        sb["emotional_arc"] = _truncate_at_sentence(arc, 100)


# ── Step 2: Generate comic-style multi-panel image ──

COMIC_IMAGE_PROMPT_TEMPLATE = """Generate a warm, hand-drawn illustration style comic page with {panel_count} panels in a DYNAMIC MANGA LAYOUT. The style should be gentle watercolor-meets-digital-illustration, with soft warm tones, slightly rounded character designs, and cozy atmosphere — similar to a "slice of life" manga or children's picture book.

Overall theme: "{theme}"
Emotional arc: "{emotional_arc}"

Panel descriptions (arrange according to emotional weight, NOT in a uniform grid):
{panel_descriptions}

MANGA PANEL LAYOUT (Japanese comic composition — CRITICAL):
- VARY panel sizes dramatically — the emotional climax panel should be 2-3x LARGER than other panels
- Use IRREGULAR, asymmetric arrangements — absolutely NO uniform grids or equal-sized panels
- Include at least one of: diagonal panel borders, L-shaped panels, or a panel that breaks/overlaps conventional borders
- Panel borders: thin black lines, but vary their angles — not all perpendicular
- Leave white gutter space between panels (manga tradition)
- Mix wide HORIZONTAL panels (landscapes, establishing shots) with tall VERTICAL panels (close-ups, character focus)

EMOTIONAL PANEL SIZING:
- Quiet/transitional moments → smaller, compact panels
- Dramatic/emotional peaks → the LARGEST panel, possibly breaking conventional borders
- Opening → a wider establishing shot panel
- Climax → hero panel, at least 30% of the page area
- Create visual rhythm through dramatic size contrast between adjacent panels

CRITICAL REQUIREMENTS:
- All {panel_count} panels must be in a SINGLE image with dynamic manga-style layout
- Consistent character appearance across panels (same clothing, hair, build)
- Warm color palette: golden yellows, soft oranges, gentle greens, twilight purples
- Hand-drawn line quality with subtle texture
- No text or speech bubbles in the panels
- Aspect ratio: 3:4 portrait (for the overall page)
- The overall mood should be warm, nostalgic, and life-affirming

Style anchor: A warm slice-of-life manga page with dynamic irregular paneling and gentle watercolor illustration style, evoking the feeling of a cherished photo album rendered as art."""


def generate_comic_image(
    storyboard: dict,
    reference_photos: List[str],
    output_dir: str = ".",
    mcp_client: Optional[MCPClient] = None,
    uploader: Optional[FileUploader] = None,
) -> Optional[str]:
    """Generate the multi-panel comic image via imagen_generate MCP tool.

    Uses reference photos to maintain visual grounding in real scenes.
    """
    from mcp_client import create_mcp_client

    cfg = _load_config()
    own_mcp = mcp_client is None
    own_uploader = uploader is None

    if own_mcp:
        mcp_client = create_mcp_client(cfg)
        mcp_client.connect()
    if own_uploader:
        uploader = FileUploader(cfg)

    panels = storyboard.get("panels", [])
    panel_count = len(panels)
    theme = storyboard.get("theme", "Life Comic")
    emotional_arc = storyboard.get("emotional_arc", "")

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
    )

    image_urls = []
    ref_count = min(len(reference_photos), 10)
    for rp in reference_photos[:ref_count]:
        try:
            img_data, mime = _load_image_bytes(rp)
            filename = os.path.basename(rp).rsplit(".", 1)[0] + ".jpg"
            url = uploader.upload_bytes(img_data, filename, mime)
            image_urls.append(url)
        except Exception as e:
            print(f"  [WARN] Failed to upload reference photo {rp}: {e}")

    print(f"  Calling imagen_generate with {len(image_urls)} reference photos...")

    try:
        try:
            result = mcp_client.call_tool("imagen_generate", {
                "prompt": prompt,
                "image_urls": image_urls,
            })
        except Exception as e:
            print(f"  ERROR: Comic image generation failed: {e}")
            return None

        text = extract_text_content(result)
        urls = extract_image_urls(text)
        if not urls:
            print("  No download URLs in imagen_generate response")
            return None

        os.makedirs(output_dir, exist_ok=True)
        filename = f"comic_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join(output_dir, filename)
        download_image(urls[0], filepath)
        size_kb = os.path.getsize(filepath) / 1024
        print(f"  Comic image saved: {os.path.abspath(filepath)} ({size_kb:.1f} KB)")
        return os.path.abspath(filepath)
    finally:
        if own_mcp:
            mcp_client.close()
        if own_uploader:
            uploader.close()


def _fallback_storyboard(panels: List[dict], date_str: str, lang: str = "en") -> dict:
    """Minimal fallback storyboard."""
    panel_list = []
    for i, p in enumerate(panels[:10]):
        panel_list.append({
            "panel_index": i,
            "source_photo_index": i,
            "scene_description": p.get("comic_panel_desc", p.get("scene_summary", "")),
            "emotion_tag": p.get("emotion", "\u6e29\u6696" if lang == "zh" else "warmth"),
            "panel_composition": "medium shot",
        })
    if lang == "zh":
        return {
            "theme": "\u751f\u6d3b\u788e\u7247",
            "emotional_arc": "\u5e73\u51e1\u65e5\u5e38\u4e2d\u7684\u6e29\u67d4\u65f6\u523b",
            "panels": panel_list,
            "narrative": {"title": "\u751f\u6d3b\u788e\u7247", "body": "\u6bcf\u4e00\u4e2a\u5e73\u51e1\u7684\u65e5\u5b50\u91cc\uff0c\u90fd\u6709\u503c\u5f97\u73cd\u85cf\u7684\u6e29\u67d4\u77ac\u95f4\u3002"},
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
