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


BLOG_GENERATION_PROMPT = """你是一位兼具文艺气质和生活美学的内容创作者。基于以下照片分析数据，生成一篇"图文Blog"。

**核心要求**：
1. 所有内容必须严格基于照片分析中描述的真实场景，绝不虚构
2. 文风温暖感性，带有文艺气息，避免流水账式平铺直叙
3. 强化情感共鸣，让读者感受到场景的温度

**照片分析数据**：
{analysis_json}

**精选高光照片**（按评分排序，用于洞察模块）：
{highlights_json}

**请输出以下 JSON 结构**：

```json
{{
  "title": "4-8字的诗意标题（如'峰林间午后'、'烟火小城记'）",
  "hero_image_index": 0,
  "description": {{
    "text": "60-100字的连贯叙事，包含时间、地点、人物动作、环境氛围，文艺感性风格，强化情感共鸣",
    "image_index": 0
  }},
  "insights": [
    {{
      "text": "40-80字的洞察文本，描述这张照片的场景细节和感悟，要有画面感",
      "image_index": 0
    }}
  ],
  "tip": "30-60字的个性化实用建议，根据场景特征（户外/室内/美食等）提供关怀性建议",
  "footer_date": "YYYY年MM月DD日"
}}
```

**注意**：
- insights 数组最多8条，每条对应一张高光照片（image_index 对应 highlights 数组的索引）
- hero_image_index 指向 highlights 数组中最适合做头图的照片
- description.image_index 也指向 highlights 数组
- title 要凝练有意境，不要太长
- 每条 insight 的文本要互不重复，各有侧重，覆盖不同场景维度
- **重要**：标题必须有创意和个性，禁止使用"烟火""烟火气""人间烟火"等过于常见的词汇。请从照片场景中提炼独特的意象，如自然景观、味觉记忆、光影变化、旅途心境等"""


def generate_blog_content(
    all_analyses: List[dict],
    highlights: List[dict],
    date_str: Optional[str] = None,
) -> dict:
    """Generate blog content from photo analyses and selected highlights.

    Args:
        all_analyses: Full analysis list (for context)
        highlights: Selected highlight photos with analysis
        date_str: Date string for footer (defaults to today)

    Returns:
        Blog content dict with title, description, insights, tip, footer
    """
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y年%m月%d日")

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

    prompt = BLOG_GENERATION_PROMPT.format(
        analysis_json=json.dumps(analysis_summary, ensure_ascii=False, indent=2),
        highlights_json=json.dumps(highlights_detail, ensure_ascii=False, indent=2),
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(response_modalities=["TEXT"], temperature=0.7),
        )
    except Exception as e:
        print(f"ERROR: Blog generation failed: {e}")
        return _fallback_content(highlights, date_str)

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
                return _fallback_content(highlights, date_str)
        else:
            return _fallback_content(highlights, date_str)

    blog["footer_date"] = date_str
    return blog


def _fallback_content(highlights: List[dict], date_str: str) -> dict:
    """Minimal fallback when LLM generation fails."""
    insights = []
    for i, h in enumerate(highlights[:8]):
        insights.append({
            "text": h.get("narrative_hook", h.get("scene", "精彩瞬间")),
            "image_index": i,
        })
    return {
        "title": "今日掠影",
        "hero_image_index": 0,
        "description": {
            "text": "记录生活中的美好瞬间，每一帧都值得珍藏。",
            "image_index": 0,
        },
        "insights": insights,
        "tip": "享受当下，记录美好，生活因细节而温暖。",
        "footer_date": date_str,
    }
