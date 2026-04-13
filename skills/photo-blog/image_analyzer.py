#!/usr/bin/env python3
"""Photo analysis via Gemini 3 Pro — batch understanding, scoring, and highlight selection.

Architecture inspired by:
- ai-instagram-organizer's multi-dimensional PhotoScore system
- gemimg's clean API wrapper pattern
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
    os.path.expanduser("~/.claude/skills/photo-blog/config.json"),
]

BATCH_SIZE = 5  # Gemini 3 Pro supports up to 14 images; use 5 for richer per-image analysis


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
class PhotoScore:
    """Multi-dimensional scoring inspired by ai-instagram-organizer."""
    visual_appeal: float = 5.0
    story_value: float = 5.0
    emotion_intensity: float = 5.0
    uniqueness: float = 5.0
    technical_quality: float = 5.0
    composite: float = 0.0
    tier: str = ""

    WEIGHTS = {
        "visual_appeal": 0.20,
        "story_value": 0.25,
        "emotion_intensity": 0.25,
        "uniqueness": 0.15,
        "technical_quality": 0.15,
    }

    def __post_init__(self):
        self.composite = sum(
            getattr(self, k) * w for k, w in self.WEIGHTS.items()
        )
        if self.composite >= 8.0:
            self.tier = "highlight"
        elif self.composite >= 6.5:
            self.tier = "good"
        elif self.composite >= 4.5:
            self.tier = "average"
        else:
            self.tier = "skip"


@dataclass
class PhotoAnalysis:
    """Structured analysis result for a single photo."""
    file_path: str
    scene: str = ""
    people: str = ""
    action: str = ""
    mood: str = ""
    location: str = ""
    time_of_day: str = ""
    objects: str = ""
    narrative_hook: str = ""
    score: PhotoScore = field(default_factory=PhotoScore)


ANALYSIS_PROMPT = """你是一位资深旅行摄影师和生活美学家。请仔细分析这组照片，为每一张照片提供详细的结构化分析。

你的分析必须严格基于图片中可见的真实内容，**绝对不可以虚构或推测**图片中不存在的事物。

请为每张照片输出如下 JSON 格式（返回一个 JSON 数组）：

```json
[
  {
    "index": 0,
    "scene": "简要描述整体场景（10-20字）",
    "people": "人物描述（外貌、穿着、年龄段），没有人则写'无人物'",
    "action": "人物正在做什么/场景中正在发生什么",
    "mood": "情感氛围（如：宁静、欢快、壮观、温馨、热闹等）",
    "location": "推测的地点类型（如：山顶观景台、古镇街道、餐厅等）",
    "time_of_day": "推测的时间段（如：清晨、午后、傍晚、夜晚）",
    "objects": "画面中的关键物体/食物/建筑",
    "narrative_hook": "这张照片最打动人的叙事点（一句话，文艺感性风格）",
    "scores": {
      "visual_appeal": 7.5,
      "story_value": 8.0,
      "emotion_intensity": 7.0,
      "uniqueness": 6.5,
      "technical_quality": 7.0
    }
  }
]
```

评分标准（1-10分）：
- visual_appeal: 构图美感、色彩、光影
- story_value: 叙事潜力，能否引发读者好奇或共鸣
- emotion_intensity: 情感冲击力
- uniqueness: 在同组照片中的独特性/信息增量
- technical_quality: 清晰度、曝光、对焦

请只输出 JSON 数组，不要输出其他内容。"""


def _fix_orientation(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation tag and strip it — the SOTA fix for rotated photos."""
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def _load_image_bytes_fixed(path: str, max_pixels: int = 1200 * 1200) -> Tuple[bytes, str]:
    """Load image, fix EXIF orientation, resize if needed, return JPEG bytes."""
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


def extract_photo_date(path: str) -> Optional[str]:
    """Extract photo date from EXIF or filename. Returns 'YYYY年MM月DD日' or None."""
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
    """Send a batch of images to Gemini 3 Pro for analysis."""
    parts: list[types.Part] = []

    for p in image_paths:
        data, mime = _load_image_bytes_fixed(p)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    parts.append(types.Part.from_text(text=ANALYSIS_PROMPT))

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
        print(f"  [WARN] Failed to parse analysis JSON. Raw: {text[:300]}...")
        return []


def analyze_photos(image_paths: List[str], batch_size: int = BATCH_SIZE) -> List[PhotoAnalysis]:
    """Analyze all photos in batches and return scored/structured results."""
    cfg = _load_config()
    client = _get_client(cfg)
    model = cfg.get("compass_api", {}).get("understanding_model", "gemini-3-pro-image-preview")

    all_results: List[PhotoAnalysis] = []
    total_batches = math.ceil(len(image_paths) / batch_size)

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(image_paths))
        batch_paths = image_paths[start:end]

        print(f"  Analyzing batch {batch_idx + 1}/{total_batches} ({len(batch_paths)} photos)...")
        raw_results = analyze_batch(client, model, batch_paths)

        for i, path in enumerate(batch_paths):
            if i < len(raw_results):
                r = raw_results[i]
                scores = r.get("scores", {})
                score = PhotoScore(
                    visual_appeal=scores.get("visual_appeal", 5.0),
                    story_value=scores.get("story_value", 5.0),
                    emotion_intensity=scores.get("emotion_intensity", 5.0),
                    uniqueness=scores.get("uniqueness", 5.0),
                    technical_quality=scores.get("technical_quality", 5.0),
                )
                analysis = PhotoAnalysis(
                    file_path=path,
                    scene=r.get("scene", ""),
                    people=r.get("people", ""),
                    action=r.get("action", ""),
                    mood=r.get("mood", ""),
                    location=r.get("location", ""),
                    time_of_day=r.get("time_of_day", ""),
                    objects=r.get("objects", ""),
                    narrative_hook=r.get("narrative_hook", ""),
                    score=score,
                )
            else:
                analysis = PhotoAnalysis(file_path=path)
            all_results.append(analysis)

    return all_results


def select_highlights(analyses: List[PhotoAnalysis], max_count: int = 8) -> List[PhotoAnalysis]:
    """Select top highlights with diversity optimization (inspired by SmartPostCreator)."""
    sorted_by_score = sorted(analyses, key=lambda a: a.score.composite, reverse=True)

    if len(sorted_by_score) <= max_count:
        return sorted_by_score

    selected: List[PhotoAnalysis] = [sorted_by_score[0]]
    candidates = sorted_by_score[1:]

    while len(selected) < max_count and candidates:
        best_candidate = None
        best_diversity = -1.0

        for c in candidates:
            diversity = _diversity_bonus(selected, c)
            combined = c.score.composite * 0.6 + diversity * 0.4
            if combined > best_diversity:
                best_diversity = combined
                best_candidate = c

        if best_candidate:
            selected.append(best_candidate)
            candidates.remove(best_candidate)
        else:
            break

    return selected


def _diversity_bonus(selected: List[PhotoAnalysis], candidate: PhotoAnalysis) -> float:
    """Calculate diversity bonus for a candidate relative to already selected photos."""
    if not selected:
        return 10.0

    mood_bonus = 1.0 if candidate.mood not in {s.mood for s in selected} else 0.3
    location_bonus = 1.0 if candidate.location not in {s.location for s in selected} else 0.3
    scene_bonus = 1.0 if candidate.scene not in {s.scene for s in selected} else 0.3

    return (mood_bonus * 3 + location_bonus * 4 + scene_bonus * 3)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: image_analyzer.py <image_dir_or_file> [max_highlights]")
        sys.exit(1)

    target = sys.argv[1]
    max_hl = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    if os.path.isdir(target):
        exts = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
        paths = sorted([
            os.path.join(target, f) for f in os.listdir(target)
            if os.path.splitext(f)[1].lower() in exts
        ])
    else:
        paths = [target]

    print(f"Found {len(paths)} photos. Analyzing...")
    results = analyze_photos(paths)

    print(f"\nAll {len(results)} photos analyzed. Selecting top {max_hl} highlights...")
    highlights = select_highlights(results, max_hl)

    print(f"\n{'='*60}")
    print(f"TOP {len(highlights)} HIGHLIGHTS:")
    print(f"{'='*60}")
    for i, h in enumerate(highlights, 1):
        print(f"\n#{i} [{h.score.tier}] Score={h.score.composite:.1f}")
        print(f"  File: {os.path.basename(h.file_path)}")
        print(f"  Scene: {h.scene}")
        print(f"  Mood: {h.mood} | Location: {h.location}")
        print(f"  Hook: {h.narrative_hook}")

    out_json = json.dumps([{
        "file": h.file_path,
        "scene": h.scene,
        "mood": h.mood,
        "location": h.location,
        "hook": h.narrative_hook,
        "score": h.score.composite,
        "tier": h.score.tier,
    } for h in highlights], ensure_ascii=False, indent=2)
    print(f"\n{out_json}")
