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

STORYBOARD_PROMPT = """你是一位温暖治愈系的漫画编剧。基于以下照片分析数据（从真实照片中提取），创作一个生活漫画的分镜脚本和情感叙事。

**核心要求**：
1. 所有漫画场景必须基于真实照片内容改编，不可凭空虚构不存在的场景
2. 情感基调：温暖治愈，可以温情也可以激情，避免过度理性
3. 漫画风格：温暖的手绘插画风格，色彩柔和但有层次

**主题创意要求（极其重要）**：
- 主题必须有创意和个性，不要使用"烟火""烟火气""人间烟火"等过于常见的词汇
- 从照片场景中提炼独特的情感主题，例如：探索与发现、味蕾的旅行、光与影的对话、城市呼吸、漫步者日记、味觉地图、屋檐下的故事等
- 标题风格可以诗意、可以俏皮、可以哲理，但不要千篇一律

**精选漫画素材**（按评分排序的高光时刻）：
{panels_json}

**请输出以下 JSON 结构**：

```json
{{
  "theme": "2-6字主题（如'陪你走过四季'、'烟火人间'）",
  "emotional_arc": "一句话描述情感弧线（如：从城市到山野，从忙碌到从容）",
  "panels": [
    {{
      "panel_index": 0,
      "source_photo_index": 0,
      "scene_description": "这个漫画分镜的详细画面描述（50-80字），包含人物、动作、环境、光线、色调",
      "emotion_tag": "2-4字情感标签（如'暮色漫步'、'山顶远眺'）",
      "panel_composition": "构图建议（如'俯视角/远景/特写'）"
    }}
  ],
  "narrative": {{
    "title": "《标题》（与theme一致，用书名号包裹）",
    "body": "100-200字的情感叙事正文。与分镜一一呼应，为每个场景赋予情感价值。结尾要升华核心价值，引发情感共鸣。不要分段标注对应哪个分镜，而是写成连贯的散文。"
  }},
  "footer_date": "YYYY年MM月DD日"
}}
```

**注意**：
- panels 数组的 source_photo_index 对应输入素材的索引
- scene_description 是给漫画画师的详细指令，要包含足够的视觉细节
- narrative.body 要有文学性，避免列清单式叙述"""


def generate_storyboard(panel_moments: List[dict], date_str: Optional[str] = None) -> dict:
    """Generate storyboard script and narrative text."""
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y年%m月%d日")

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

    prompt = STORYBOARD_PROMPT.format(
        panels_json=json.dumps(panels_detail, ensure_ascii=False, indent=2),
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(response_modalities=["TEXT"], temperature=0.7),
        )
    except Exception as e:
        print(f"ERROR: Storyboard generation failed: {e}")
        return _fallback_storyboard(panel_moments, date_str)

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
                return _fallback_storyboard(panel_moments, date_str)
        else:
            return _fallback_storyboard(panel_moments, date_str)

    sb["footer_date"] = date_str
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
    theme = storyboard.get("theme", "生活漫画")
    emotional_arc = storyboard.get("emotional_arc", "")

    if panel_count <= 4:
        grid_layout = "2x2"
    elif panel_count <= 6:
        grid_layout = "2x3"
    else:
        grid_layout = "2x4"

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

    ref_count = min(len(reference_photos), 6)
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


def _fallback_storyboard(panels: List[dict], date_str: str) -> dict:
    """Minimal fallback storyboard."""
    panel_list = []
    for i, p in enumerate(panels[:6]):
        panel_list.append({
            "panel_index": i,
            "source_photo_index": i,
            "scene_description": p.get("comic_panel_desc", p.get("scene_summary", "")),
            "emotion_tag": p.get("emotion", "温暖"),
            "panel_composition": "中景",
        })
    return {
        "theme": "生活片段",
        "emotional_arc": "日常中的美好",
        "panels": panel_list,
        "narrative": {
            "title": "《生活片段》",
            "body": "每一个平凡的日子里，都藏着值得铭记的温柔时刻。"
        },
        "footer_date": date_str,
    }
