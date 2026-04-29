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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from mcp_client import MCPClient, extract_text_content
from file_uploader import FileUploader
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


COMIC_ANALYSIS_PROMPT = """You are a comic storyboard artist and life-story curator. Analyze this set of photos to identify "highlight moments" suitable for adaptation into life comic panels.

**Core requirements**:
1. Analyze strictly based on visible, real content in the photos — never fabricate
2. Focus on identifying moments with "comic appeal": dynamism, emotional contrast, environmental shifts, humor
3. Evaluate each photo from a narrative perspective — can it stand as an independent comic panel?

For each photo, output the following JSON format (return a JSON array):

```json
[
  {
    "index": 0,
    "scene_summary": "One-sentence scene summary (10-20 words)",
    "character_desc": "Character appearance (clothing/hair/features), or 'none' if no people",
    "action_desc": "Action happening, emphasizing dynamism",
    "emotion": "Core emotion (e.g., surprise, serenity, excitement, focus, warmth)",
    "environment": "Environment description (weather/lighting/color tone/terrain)",
    "time_of_day": "Time of day",
    "comic_panel_desc": "How this scene should look as a comic panel (20-40 words, including composition/angle/effect line suggestions)",
    "scores": {
      "comic_potential": 8.0,
      "visual_distinctness": 7.5,
      "narrative_weight": 7.0
    }
  }
]
```

Scoring criteria (1-10):
- comic_potential: potential for comic adaptation (dynamism, drama, visual tension)
- visual_distinctness: visual distinctiveness (color, composition, uniqueness)
- narrative_weight: narrative significance (is it a key story node, an emotional turning point?)

Output only the JSON array."""


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


def analyze_batch(mcp_client: MCPClient, uploader: FileUploader, image_paths: List[str]) -> List[dict]:
    try:
        image_urls = []
        for p in image_paths:
            data, mime = _load_image_bytes_fixed(p)
            filename = os.path.basename(p).rsplit(".", 1)[0] + ".jpg"
            url = uploader.upload_bytes(data, filename, mime)
            image_urls.append(url)
    except Exception as e:
        print(f"  [WARN] Image upload failed: {e}")
        return []

    try:
        result = mcp_client.call_tool("image_understand", {
            "prompt": COMIC_ANALYSIS_PROMPT,
            "image_urls": image_urls,
        })
    except Exception as e:
        print(f"  [WARN] Batch analysis failed: {e}")
        return []

    text = extract_text_content(result)

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


def analyze_photos(image_paths: List[str], batch_size: int = BATCH_SIZE,
                    mcp_client: Optional[MCPClient] = None,
                    uploader: Optional[FileUploader] = None) -> List[ComicMoment]:
    from mcp_client import create_mcp_client

    cfg = _load_config()
    own_mcp = mcp_client is None
    own_uploader = uploader is None

    if own_mcp:
        mcp_client = create_mcp_client(cfg)
        mcp_client.connect()
    if own_uploader:
        uploader = FileUploader(cfg)

    try:
        all_moments: List[ComicMoment] = []
        total_batches = math.ceil(len(image_paths) / batch_size)

        for bi in range(total_batches):
            start = bi * batch_size
            end = min(start + batch_size, len(image_paths))
            batch = image_paths[start:end]

            print(f"  Analyzing batch {bi+1}/{total_batches} ({len(batch)} photos)...")
            raw = analyze_batch(mcp_client, uploader, batch)

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
    finally:
        if own_mcp:
            mcp_client.close()
        if own_uploader:
            uploader.close()


def select_comic_panels(moments: List[ComicMoment], panel_count: int = 8) -> List[ComicMoment]:
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
    panels = int(sys.argv[2]) if len(sys.argv) > 2 else 8

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
