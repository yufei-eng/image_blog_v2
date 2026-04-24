#!/usr/bin/env python3
"""AI cover image generator for Photo Blog — template-driven diverse styles.

Uses a library of 89 analyzed reference templates to produce visually diverse
cover images. Each generation matches a template based on blog content (mood,
theme, photo count) and passes the template image as a style reference to
Gemini 3.1 Flash Image, achieving "style reference + content personalization".

Architecture:
1. Load template_library.json (pre-built via build_template_library.py)
2. Extract mood/theme signals from blog content
3. Score & select best-matching template (with diversity dedup)
4. Build dynamic prompt from template metadata
5. Call Gemini with [style_ref_image, blog_photos..., prompt]
"""

import json
import math
import os
import random
import sys
import time
import uuid
from typing import List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from mcp_client import MCPClient, extract_text_content
from file_uploader import FileUploader
from image_downloader import extract_image_urls, download_image

TEMPLATE_LIB_PATH = os.path.join(SCRIPT_DIR, "template_library.json")

_RECENT_STYLES: list[str] = []
_RECENT_STYLES_MAX = 5


def _load_config() -> dict:
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def _load_image_bytes(path: str, max_pixels: int = 800 * 800) -> Tuple[bytes, str]:
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


def _load_template_library() -> list[dict]:
    if not os.path.exists(TEMPLATE_LIB_PATH):
        print(f"  [WARN] Template library not found at {TEMPLATE_LIB_PATH}")
        return []
    with open(TEMPLATE_LIB_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Blog content analysis — extract mood & theme signals
# ---------------------------------------------------------------------------

MOOD_KEYWORDS = {
    "playful": ["fun", "game", "play", "laugh", "silly", "cute", "adorable"],
    "warm": ["warm", "cozy", "comfort", "home", "family", "gather", "together"],
    "adventurous": ["adventure", "explore", "discover", "journey", "wander", "hike", "climb"],
    "energetic": ["energy", "active", "sport", "run", "dance", "vibrant", "exciting"],
    "serene": ["calm", "peace", "quiet", "serene", "gentle", "still", "tranquil"],
    "nostalgic": ["memory", "remember", "past", "old", "vintage", "retro", "classic"],
    "romantic": ["love", "romance", "couple", "date", "heart", "kiss", "sweet"],
    "artistic": ["art", "paint", "gallery", "museum", "creative", "design", "aesthetic"],
    "elegant": ["elegant", "refined", "luxury", "sophisticated", "classy", "chic"],
    "bold": ["bold", "strong", "power", "fierce", "dramatic", "intense", "striking"],
    "dreamy": ["dream", "fantasy", "magic", "wonder", "fairy", "ethereal", "mystical"],
    "cheerful": ["happy", "joy", "bright", "sunny", "cheerful", "celebrate", "party"],
    "cool": ["cool", "chill", "urban", "street", "grunge", "edgy", "rebel"],
    "youthful": ["young", "youth", "fresh", "new", "spring", "bloom", "grow"],
    "minimalist": ["minimal", "simple", "clean", "pure", "less", "zen", "sparse"],
    "whimsical": ["whimsical", "curious", "quirky", "unusual", "surprise", "wonder"],
}

THEME_KEYWORDS = {
    "food": ["food", "eat", "cook", "meal", "dish", "restaurant", "cafe", "spice", "flavor",
             "broth", "noodle", "dumpling", "hot pot", "feast", "culinary", "taste", "kitchen"],
    "travel": ["travel", "trip", "journey", "destination", "hotel", "flight", "suitcase",
               "passport", "tourist", "scenic", "view", "explore", "wander"],
    "nature": ["nature", "forest", "mountain", "river", "lake", "ocean", "sea", "flower",
               "tree", "garden", "sunset", "sunrise", "sky", "cloud", "rain"],
    "urban": ["city", "street", "building", "night", "neon", "traffic", "downtown",
              "metro", "skyline", "cafe", "shop", "market"],
    "family": ["family", "parent", "child", "baby", "mother", "father", "home", "together"],
    "friends": ["friend", "group", "hang", "party", "gathering", "crew", "squad"],
    "culture": ["temple", "buddha", "statue", "ancient", "history", "tradition", "heritage",
                "museum", "artifact", "pottery", "carving", "monument"],
    "romance": ["love", "couple", "date", "romantic", "valentine", "wedding", "anniversary"],
    "fashion": ["fashion", "style", "outfit", "clothes", "dress", "model", "portrait"],
    "daily_life": ["daily", "routine", "morning", "everyday", "life", "moment", "slice"],
    "celebration": ["celebrate", "birthday", "holiday", "festival", "christmas", "new year"],
    "seasons": ["spring", "summer", "autumn", "winter", "season", "snow", "leaf"],
    "pets": ["cat", "dog", "pet", "animal", "puppy", "kitten"],
    "sports": ["sport", "run", "swim", "ball", "game", "fitness", "gym", "exercise"],
}


def _extract_cover_context(blog_content: dict) -> dict:
    """Extract rich signals from blog content for template matching."""
    title = blog_content.get("title", "Photo Blog")
    insights = blog_content.get("insights", [])
    desc = blog_content.get("description", {})
    desc_text = desc.get("text", "") if isinstance(desc, dict) else str(desc)
    suggested_themes = blog_content.get("suggested_themes", [])

    all_text = (title + " " + desc_text + " " +
                " ".join(ins.get("text", "") for ins in insights[:6])).lower()

    mood_tags = []
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(kw in all_text for kw in keywords):
            mood_tags.append(mood)
    if not mood_tags:
        mood_tags = ["warm", "cheerful"]

    theme_tags = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(kw in all_text for kw in keywords):
            theme_tags.append(theme)
    if not theme_tags:
        theme_tags = ["daily_life"]

    scene_keywords = []
    for ins in insights[:6]:
        text = ins.get("text", "")
        scene_keywords.append(text[:80])
    scene_summary = "; ".join(scene_keywords[:4]) if scene_keywords else "various life moments"

    return {
        "title": title,
        "description": desc_text[:200],
        "scene_summary": scene_summary,
        "photo_count": len(insights),
        "mood_tags": mood_tags,
        "theme_tags": theme_tags,
        "suggested_themes": suggested_themes,
    }


# ---------------------------------------------------------------------------
# Template Matcher
# ---------------------------------------------------------------------------

def _score_template(template: dict, ctx: dict) -> float:
    score = 0.0

    # Photo count fit (30%)
    pc_range = template.get("photo_count_range", [1, 10])
    pc = ctx["photo_count"]
    if pc_range[0] <= pc <= pc_range[1]:
        score += 30.0
    elif abs(pc - pc_range[0]) <= 1 or abs(pc - pc_range[1]) <= 1:
        score += 15.0
    else:
        score += 5.0

    # Mood match (25%)
    tmood = set(template.get("mood", []))
    cmood = set(ctx["mood_tags"])
    overlap = len(tmood & cmood)
    if tmood:
        score += 25.0 * min(overlap / max(len(cmood), 1), 1.0)

    # Theme match (25%)
    tthemes = set(template.get("theme_affinity", []))
    cthemes = set(ctx["theme_tags"])
    overlap = len(tthemes & cthemes)
    if tthemes:
        score += 25.0 * min(overlap / max(len(cthemes), 1), 1.0)

    # Diversity penalty (20%) — penalize recently used styles
    style = template.get("style_category", "")
    if style in _RECENT_STYLES:
        recency = len(_RECENT_STYLES) - _RECENT_STYLES.index(style)
        score -= 20.0 * (recency / len(_RECENT_STYLES))
    else:
        score += 10.0

    # Small random jitter to break ties and add variety
    score += random.uniform(0, 5.0)

    return score


def _match_template(templates: list[dict], ctx: dict) -> dict:
    """Select the best-matching template for the blog context."""
    if not templates:
        return {}

    scored = [(t, _score_template(t, ctx)) for t in templates]
    scored.sort(key=lambda x: -x[1])

    best = scored[0][0]
    style = best.get("style_category", "unknown")

    global _RECENT_STYLES
    _RECENT_STYLES.append(style)
    if len(_RECENT_STYLES) > _RECENT_STYLES_MAX:
        _RECENT_STYLES = _RECENT_STYLES[-_RECENT_STYLES_MAX:]

    return best


# ---------------------------------------------------------------------------
# Dynamic Prompt Builder
# ---------------------------------------------------------------------------

def _build_cover_prompt(template: dict, ctx: dict, lang: str = "en") -> str:
    """Build a personalized cover generation prompt based on the matched template."""

    style_cat = template.get("style_category", "scrapbook")
    layout = template.get("layout_type", "scattered_polaroid")
    typo = template.get("typography_style", "handwritten_script")
    deco = template.get("decoration_level", "moderate")
    bg = template.get("background_type", "solid_color")
    palette = ", ".join(template.get("color_palette", ["warm tones"]))
    temp = template.get("color_temperature", "warm")
    vis_desc = template.get("visual_description", "")

    photo_count = min(ctx["photo_count"], 5)

    lang_rule = ""
    if lang != "zh":
        lang_rule = "\n7. **Language**: ALL text in the cover image MUST be in English. Do NOT include any Chinese, Japanese, or Korean characters."

    prompt = f"""Generate a blog cover image that closely follows the visual style of the FIRST reference image (the style template).

**STYLE TEMPLATE TO MATCH**:
The first uploaded image is your style reference. Reproduce its aesthetic:
- Visual style: {vis_desc}
- Layout approach: {layout} (arrange photos in this manner)
- Typography: {typo} font style
- Decoration level: {deco}
- Background: {bg}
- Color palette: {palette} ({temp} temperature)
- Overall category: {style_cat}

**BLOG CONTENT TO PERSONALIZE WITH**:
- Blog title: "{ctx['title']}"
- Blog story: {ctx['description']}
- Key scenes: {ctx['scene_summary']}
- Number of blog photos provided: {photo_count} (the images after the style template)

**GENERATION RULES**:

1. **Style Fidelity**: Match the style template's aesthetic as closely as possible — its layout structure, color scheme, decoration approach, and typography feel. This is the PRIMARY directive.

2. **Content Personalization**: Replace the template's placeholder content with this blog's actual content:
   - Use the blog title as the main heading text
   - Feature the blog's photos (images 2 onward) as the photo content within the template's layout
   - Adapt decorative elements to match the blog's theme (e.g. food icons for food blogs, travel stamps for travel)

3. **Creative Variation**: While matching the template's style category, freely vary:
   - Exact color shades (shift the palette to complement the blog photos' tones)
   - Specific decorative details (different doodles, icons, stickers that fit the theme)
   - Text placement and exact layout proportions
   - The goal is "same style family, unique execution"

4. **Photo Integration**: The blog photos (images after the style template) MUST appear as clearly visible, recognizable photo thumbnails/frames within the cover. Do NOT replace them with illustrations.

5. **Aspect Ratio**: 16:9 landscape (wide blog header format).

6. **Title Text**: Display "{ctx['title']}" prominently in the {typo} style.{lang_rule}"""

    return prompt


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_cover_image(
    blog_content: dict,
    highlight_paths: list[str],
    output_dir: str = ".",
    ref_images_dir: str = "",
    lang: str = "en",
    mcp_client: Optional[MCPClient] = None,
    uploader: Optional[FileUploader] = None,
) -> Optional[str]:
    """Generate a diverse, template-driven cover image for the blog.

    Args:
        blog_content: Blog content dict (title, description, insights, etc.)
        highlight_paths: Paths to highlight photos (will use top 3-5)
        output_dir: Where to save the generated cover
        ref_images_dir: Directory containing reference template images
        lang: Language for cover text ('en' or 'zh')
        mcp_client: Optional shared MCP client
        uploader: Optional shared FileUploader

    Returns:
        Path to generated cover PNG, or None if generation failed.
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

    templates = _load_template_library()
    ctx = _extract_cover_context(blog_content)

    if not ref_images_dir:
        ref_images_dir = os.path.join(SCRIPT_DIR, "cover_references")

    if templates:
        template = _match_template(templates, ctx)
        template_file = template.get("file", "")
        template_path = os.path.join(ref_images_dir, template_file) if template_file else ""

        print(f"  Template matched: [{template.get('style_category', '?')}] "
              f"{template.get('id', '?')} — {template_file[:40]}...")
        print(f"    Mood: {template.get('mood', [])[:3]}, "
              f"Layout: {template.get('layout_type', '?')}, "
              f"Palette: {template.get('color_palette', [])[:3]}")

        prompt = _build_cover_prompt(template, ctx, lang=lang)
    else:
        template_path = ""
        prompt = _build_fallback_prompt(ctx, lang=lang)
        print("  [WARN] No template library found, using fallback prompt")

    ref_count = min(len(highlight_paths), 5)

    image_urls = []

    if template_path and os.path.exists(template_path):
        try:
            tpl_data, tpl_mime = _load_image_bytes(template_path, max_pixels=1000 * 1000)
            tpl_url = uploader.upload_bytes(tpl_data, "template.jpg", tpl_mime)
            image_urls.append(tpl_url)
        except Exception as e:
            print(f"  [WARN] Failed to upload template image: {e}")

    for rp in highlight_paths[:ref_count]:
        try:
            img_data, mime = _load_image_bytes(rp)
            filename = os.path.basename(rp).rsplit(".", 1)[0] + ".jpg"
            url = uploader.upload_bytes(img_data, filename, mime)
            image_urls.append(url)
        except Exception as e:
            print(f"  [WARN] Failed to upload photo {rp}: {e}")

    tpl_label = "1 template + " if template_path else ""
    print(f"  Generating cover with {tpl_label}{ref_count} photos via imagen_generate...")

    max_retries = 2
    try:
        for attempt in range(max_retries + 1):
            try:
                result = mcp_client.call_tool("imagen_generate", {
                    "prompt": prompt,
                    "image_urls": image_urls,
                })
            except Exception as e:
                if attempt < max_retries:
                    print(f"  [RETRY {attempt+1}/{max_retries}] Error: {e}")
                    time.sleep(2)
                    continue
                print(f"  ERROR: Cover generation failed after {max_retries+1} attempts: {e}")
                return None

            text = extract_text_content(result)
            urls = extract_image_urls(text)

            if not urls:
                if attempt < max_retries:
                    print(f"  [RETRY {attempt+1}/{max_retries}] No download URL in response, retrying...")
                    time.sleep(2)
                    continue
                print("  No download URLs in cover generation response after retries")
                return None

            os.makedirs(output_dir, exist_ok=True)
            filename = f"cover_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
            filepath = os.path.join(output_dir, filename)
            download_image(urls[0], filepath)
            size_kb = os.path.getsize(filepath) / 1024
            print(f"  Cover saved: {os.path.abspath(filepath)} ({size_kb:.1f} KB)")
            return os.path.abspath(filepath)

        return None
    finally:
        if own_mcp:
            mcp_client.close()
        if own_uploader:
            uploader.close()


def _build_fallback_prompt(ctx: dict, lang: str = "en") -> str:
    """Fallback prompt when no template library is available."""
    lang_rule = " All text must be in English." if lang != "zh" else ""
    return f"""Create a visually stunning blog cover image.

**Blog title**: "{ctx['title']}"
**Blog story**: {ctx['description']}
**Key scenes**: {ctx['scene_summary']}

Design a creative, eye-catching cover that features the uploaded photos as visible
thumbnails within the design. Use a 16:9 landscape format. Display the title prominently.
Make it personal and share-worthy.{lang_rule}"""
