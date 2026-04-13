#!/usr/bin/env python3
"""Photo analysis for life comic — scene extraction, moment detection, storyboard scoring.

Focuses on identifying "story-worthy" moments for comic panel adaptation.
"""

import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps
from google import genai
from google.genai import types

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATHS = [
    os.path.join(SCRIPT_DIR, "config.json"),
    os.path.expanduser("~/.claude/skills/life-comic/config.json"),
]

BATCH_SIZE = 5


def _load_config() -> dict:
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def _get_client(cfg: dict):
    api_cfg = cfg.get("compass_api", {})
    token = os.environ.get("COMPASS_CLIENT_TOKEN", api_cfg.get("client_token", ""))
    base_url = api_cfg.get("base_url", "http://beeai.test.shopee.io/inbeeai/compass-api/v1")
    if not token:
        print("ERROR: Compass API client_token not found.")
        sys.exit(1)
    return genai.Client(api_key=token, http_options=types.HttpOptions(base_url=base_url))


@dataclass
class ComicMoment:
    """A moment extracted from a photo, suitable for comic panel adaptation."""
    file_path: str
    scene_summary: str = ""
    character_desc: str = ""
    action_desc: str = ""
    emotion: str = ""
    environment: str = ""
    time_of_day: str = ""
    comic_potential: float = 5.0
    visual_distinctness: float = 5.0
    narrative_weight: float = 5.0
    comic_panel_desc: str = ""
    composite_score: float = 0.0
    tier: str = ""

    def __post_init__(self):
        self.composite_score = (
            self.comic_potential * 0.35 +
            self.visual_distinctness * 0.30 +
            self.narrative_weight * 0.35
        )
        if self.composite_score >= 7.5:
            self.tier = "star_moment"
        elif self.composite_score >= 6.0:
            self.tier = "good_moment"
        elif self.composite_score >= 4.0:
            self.tier = "average"
        else:
            self.tier = "skip"


COMIC_ANALYSIS_PROMPT = """你是一位漫画分镜师和生活故事策展人。请分析这组照片，从中识别适合改编为生活漫画分镜的"精彩时刻"。

**核心要求**：
1. 严格基于照片中可见的真实内容分析，绝不虚构
2. 重点识别有"漫画感"的时刻：动态感、情感冲突、环境转换、趣味性
3. 从叙事角度评估每张照片能否成为漫画中的一个独立分镜

请为每张照片输出如下 JSON 格式（返回 JSON 数组）：

```json
[
  {
    "index": 0,
    "scene_summary": "一句话概括场景（15-25字）",
    "character_desc": "人物外观描述（穿着/发型/特征），无人写'无'",
    "action_desc": "正在发生的动作，强调动态感",
    "emotion": "核心情感（如：惊喜、宁静、兴奋、专注、温馨）",
    "environment": "环境描述（天气/光线/色调/地形）",
    "time_of_day": "时间段",
    "comic_panel_desc": "如果把这个场景画成漫画分镜，应该是什么样子（30-50字，包含构图/视角/效果线建议）",
    "scores": {
      "comic_potential": 8.0,
      "visual_distinctness": 7.5,
      "narrative_weight": 7.0
    }
  }
]
```

评分标准（1-10分）：
- comic_potential: 改编为漫画的潜力（动态感、戏剧性、画面张力）
- visual_distinctness: 视觉区分度（色彩、构图、独特性）
- narrative_weight: 叙事分量（是否为故事的关键节点、情感转折点）

请只输出 JSON 数组。"""


def _fix_orientation(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation tag — fixes rotated/flipped photos."""
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def _load_image_bytes_fixed(path: str, max_pixels: int = 1200 * 1200) -> Tuple[bytes, str]:
    """Load image with EXIF orientation fix, resize, return JPEG bytes."""
    import io
    img = Image.open(path)
    img = _fix_orientation(img)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    w, h = img.size
    if w * h > max_pixels:
        ratio = math.sqrt(max_pixels / (w * h))
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue(), "image/jpeg"


def extract_photo_date(path: str) -> str | None:
    """Extract photo date from EXIF or filename."""
    try:
        img = Image.open(path)
        exif = img.getexif()
        ifd = exif.get_ifd(0x8769)
        dt_str = ifd.get(36867, "") or ifd.get(36868, "") or exif.get(306, "")
        if dt_str:
            dt = datetime.strptime(dt_str[:19], "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%Y年%m月%d日")
    except Exception:
        pass
    m = re.search(r"(\d{4})(\d{2})(\d{2})", os.path.basename(path))
    if m:
        return f"{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return None


def analyze_batch(client, model: str, image_paths: List[str]) -> List[dict]:
    parts: list[types.Part] = []
    for p in image_paths:
        data, mime = _load_image_bytes_fixed(p)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    parts.append(types.Part.from_text(text=COMIC_ANALYSIS_PROMPT))

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(response_modalities=["TEXT"], temperature=0.3),
        )
    except Exception as e:
        print(f"  [WARN] Batch analysis failed: {e}")
        return []

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
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        print(f"  [WARN] Failed to parse JSON. Raw: {text[:300]}...")
        return []


def analyze_photos(image_paths: List[str], batch_size: int = BATCH_SIZE) -> List[ComicMoment]:
    cfg = _load_config()
    client = _get_client(cfg)
    model = cfg.get("compass_api", {}).get("understanding_model", "gemini-3-pro-image-preview")

    all_moments: List[ComicMoment] = []
    total_batches = math.ceil(len(image_paths) / batch_size)

    for bi in range(total_batches):
        start = bi * batch_size
        end = min(start + batch_size, len(image_paths))
        batch = image_paths[start:end]

        print(f"  Analyzing batch {bi+1}/{total_batches} ({len(batch)} photos)...")
        raw = analyze_batch(client, model, batch)

        for i, path in enumerate(batch):
            if i < len(raw):
                r = raw[i]
                scores = r.get("scores", {})
                moment = ComicMoment(
                    file_path=path,
                    scene_summary=r.get("scene_summary", ""),
                    character_desc=r.get("character_desc", ""),
                    action_desc=r.get("action_desc", ""),
                    emotion=r.get("emotion", ""),
                    environment=r.get("environment", ""),
                    time_of_day=r.get("time_of_day", ""),
                    comic_potential=scores.get("comic_potential", 5.0),
                    visual_distinctness=scores.get("visual_distinctness", 5.0),
                    narrative_weight=scores.get("narrative_weight", 5.0),
                    comic_panel_desc=r.get("comic_panel_desc", ""),
                )
            else:
                moment = ComicMoment(file_path=path)
            all_moments.append(moment)

    return all_moments


def select_comic_panels(moments: List[ComicMoment], panel_count: int = 6) -> List[ComicMoment]:
    """Select the best moments for comic panels with narrative flow and diversity."""
    sorted_moments = sorted(moments, key=lambda m: m.composite_score, reverse=True)

    if len(sorted_moments) <= panel_count:
        return sorted_moments

    selected: List[ComicMoment] = [sorted_moments[0]]
    candidates = sorted_moments[1:]

    while len(selected) < panel_count and candidates:
        best = None
        best_val = -1.0

        for c in candidates:
            emotion_div = 1.0 if c.emotion not in {s.emotion for s in selected} else 0.3
            env_div = 1.0 if c.environment not in {s.environment for s in selected} else 0.3
            time_div = 1.0 if c.time_of_day not in {s.time_of_day for s in selected} else 0.5
            diversity = emotion_div * 3 + env_div * 4 + time_div * 3
            value = c.composite_score * 0.55 + diversity * 0.45
            if value > best_val:
                best_val = value
                best = c

        if best:
            selected.append(best)
            candidates.remove(best)

    return selected


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: image_analyzer.py <image_dir_or_file> [panel_count]")
        sys.exit(1)

    target = sys.argv[1]
    panels = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    exts = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    if os.path.isdir(target):
        paths = sorted([os.path.join(target, f) for f in os.listdir(target)
                        if os.path.splitext(f)[1].lower() in exts])
    else:
        paths = [target]

    print(f"Found {len(paths)} photos. Analyzing for comic moments...")
    moments = analyze_photos(paths)
    selected = select_comic_panels(moments, panels)

    print(f"\n{'='*60}")
    print(f"TOP {len(selected)} COMIC PANELS:")
    print(f"{'='*60}")
    for i, m in enumerate(selected, 1):
        print(f"\n#{i} [{m.tier}] Score={m.composite_score:.1f}")
        print(f"  File: {os.path.basename(m.file_path)}")
        print(f"  Scene: {m.scene_summary}")
        print(f"  Emotion: {m.emotion}")
        print(f"  Panel: {m.comic_panel_desc}")
