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
    token = (os.environ.get("COMPASS_CLIENT_TOKEN")
             or os.environ.get("COMPASS_API_KEY")
             or os.environ.get("ANTHROPIC_API_KEY")
             or os.environ.get("GOOGLE_API_KEY")
             or os.environ.get("GEMINI_API_KEY")
             or api_cfg.get("client_token", ""))
    base_url = (os.environ.get("COMPASS_BASE_URL")
                or os.environ.get("ANTHROPIC_BASE_URL")
                or api_cfg.get("base_url", ""))
    if not token:
        print("ERROR: API key not found.")
        print("FIX: Set one of: COMPASS_CLIENT_TOKEN, COMPASS_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GEMINI_API_KEY")
        print(f"  Or create config.json from config.json.example:")
        print(f"  cp {os.path.join(SCRIPT_DIR, 'config.json.example')} {os.path.join(SCRIPT_DIR, 'config.json')}")
        sys.exit(1)
    http_opts = types.HttpOptions(base_url=base_url) if base_url else None
    return genai.Client(api_key=token, http_options=http_opts)


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
    orientation_correct: bool = True
    score: PhotoScore = field(default_factory=PhotoScore)


ANALYSIS_PROMPT = """You are a seasoned travel photographer and lifestyle aesthete. Analyze this set of photos carefully, providing a detailed structured analysis for each one.

Your analysis must be strictly based on the visible, real content in the images. **Never fabricate or speculate** about things that are not present.

For each photo, output the following JSON format (return a JSON array):

```json
[
  {
    "index": 0,
    "scene": "Brief scene description (10-20 words)",
    "people": "Description of people (appearance, clothing, age group), or 'no people' if none",
    "action": "What people are doing / what is happening in the scene",
    "mood": "Emotional atmosphere (e.g., serene, joyful, spectacular, cozy, lively)",
    "location": "Inferred location type (e.g., mountain lookout, old-town street, restaurant)",
    "time_of_day": "Inferred time of day (e.g., dawn, afternoon, dusk, night)",
    "objects": "Key objects / food / architecture in the frame",
    "narrative_hook": "The most compelling narrative point of this photo (one sentence, evocative style)",
    "orientation_correct": true,
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

**orientation_correct**: Look at the image as displayed. Is the orientation natural and correct?
- true = the image looks correct (people standing upright, text readable, horizon level)
- false = the image appears rotated or sideways (e.g., a landscape photo displayed as portrait, people tilted 90°, food plate on its side)
This is critical for detecting photos where EXIF orientation was incorrectly applied.

Scoring criteria (1-10):
- visual_appeal: composition aesthetics, color, lighting
- story_value: narrative potential — can it spark curiosity or emotional resonance?
- emotion_intensity: emotional impact
- uniqueness: distinctiveness and information gain relative to the rest of the set
- technical_quality: sharpness, exposure, focus

Output only the JSON array, nothing else."""


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
    """Extract photo date from EXIF or filename. Returns 'YYYY-MM-DD' or None."""
    try:
        img = Image.open(path)
        exif = img.getexif()
        ifd = exif.get_ifd(0x8769)
        dt_str = ifd.get(36867, "") or ifd.get(36868, "") or exif.get(306, "")
        if dt_str:
            dt = datetime.strptime(dt_str[:19], "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    m = re.search(r"(\d{4})(\d{2})(\d{2})", os.path.basename(path))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
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
    model = cfg.get("compass_api", {}).get("understanding_model", "gemini-3-pro-preview")

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
                    orientation_correct=r.get("orientation_correct", True),
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
