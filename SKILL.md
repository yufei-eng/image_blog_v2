---
name: image_blog
description: >-
  Photo-to-content generation tool with two AI skills — photo-blog (narrative visual blog)
  and life-comic (hand-drawn comic strip). Analyzes photos with Gemini 3 Pro for scene
  understanding and scoring, selects highlights with diversity optimization, generates
  themed content with poetic titles and emotional narrative. Supports 1-9 images,
  theme/style keyword guidance with smart fallback, and triple output format
  (HTML, rich text Markdown, HiDPI PNG). Triggers when users request photo blog,
  life summary, travel log, comic strip, visual diary, or illustrated story from images.
argument-hint: <image_directory_or_file>
metadata:
  execution_mode: sandbox
  adk_additional_tools:
    - imagen_generate
---

# Image Blog & Life Comic Skill

Two photo-to-content generation skills powered by Gemini 3 Pro + Gemini 3.1 Flash Image.

## When to Use

- User asks to create a **photo blog**, photo story, travel log, life summary, or visual diary from photos
- User asks to create a **comic strip**, manga, illustrated story, or comic-style summary from photos
- User says "summarize my photos", "make a photo diary", "turn photos into a comic", "create a visual story"
- User provides photos and wants a narrative writeup, summary, or artistic illustration
- User wants a **life recap** or **memory collage** from recent photos

## Skill Selection

| User Intent | Skill | Script |
|-------------|-------|--------|
| Photo blog, life summary, travel log, visual diary, photo story | **photo-blog** | `skills/photo-blog/main.py` |
| Comic strip, manga, illustrated story, comic-style, fun version | **life-comic** | `skills/life-comic/main.py` |
| Ambiguous ("make something from my photos") | Default to **photo-blog**, then suggest comic version after |

## Setup (in sandbox)

**Quick-start note**: The code has a built-in API key fallback chain that automatically checks env vars in this order: `COMPASS_CLIENT_TOKEN` → `COMPASS_API_KEY` → `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` → `GEMINI_API_KEY` → config.json. If any of these env vars is already set in the sandbox environment, you can **skip the config.json setup steps** below — the code will pick up the key automatically. Just download, install dependencies, and run.

Download and install the skill:

```bash
# Download
curl -sL https://codeload.github.com/yufei-eng/image_blog_v2/zip/refs/heads/main -o /tmp/image_blog.zip
cd /tmp && unzip -qo image_blog.zip && cd image_blog_v2-main

# Install dependencies
pip install -q google-genai Pillow playwright
python -m playwright install chromium 2>/dev/null || true
```

Only if no API key env var is set, configure manually:
```bash
for skill in photo-blog life-comic; do
  cp skills/$skill/config.json.example skills/$skill/config.json
done
```

If `COMPASS_API_KEY` env var is set but you still want config.json:
```bash
for skill in photo-blog life-comic; do
  python3 -c "
import json, os
cfg = json.load(open('skills/$skill/config.json'))
cfg['compass_api']['client_token'] = os.environ.get('COMPASS_API_KEY', cfg['compass_api']['client_token'])
json.dump(cfg, open('skills/$skill/config.json', 'w'), indent=2)
"
done
```

## Running — photo-blog

```bash
python3 skills/photo-blog/main.py <image_dir_or_file> \
    [--max-highlights 6] \
    [--theme "food journey"] \
    [--format all] \
    [--output output/blog.html]
```

| Arg | Description | Default |
|-----|-------------|---------|
| `input` | Image directory or file path | required |
| `--max-highlights` | Number of highlight photos (1-9) | 9 |
| `--theme` | Theme keyword to guide generation | auto |
| `--format` | `html` / `richtext` / `png` / `all` | `all` |
| `--output` | Output file path | `blog_output.html` |

## Running — life-comic

```bash
python3 skills/life-comic/main.py <image_dir_or_file> \
    [--panels 8] \
    [--theme "city nightscape"] \
    [--format all] \
    [--output output/comic.html] \
    [--output-dir output/]
```

| Arg | Description | Default |
|-----|-------------|---------|
| `input` | Image directory or file path | required |
| `--panels` | Number of comic panels (1-9) | 8 |
| `--theme` | Theme keyword to guide generation | auto |
| `--format` | `html` / `richtext` / `png` / `all` | `all` |
| `--output` | Output file path | `comic_output.html` |
| `--output-dir` | Directory for generated comic images | `.` |

## Output Handling

Both skills generate 3 output formats by default (`--format all`):

| Format | File | Best for |
|--------|------|----------|
| **HTML** | `*.html` | Cursor / Claude Code — open in browser |
| **Rich Text** | `*_richtext.md` | Chat agents — display as Markdown in conversation |
| **PNG** | `*.png` | Sharing — pixel-perfect screenshot of the HTML, 2x HiDPI |

**Display rules**:
1. In **chat agent** context → show the Rich Text (Markdown) content inline in the conversation
2. **Always** provide **both** download links at the end:
   - PNG download link (shareable image)
   - HTML download link — append a localized label: use "(for internal testing)" in English conversations, and the equivalent localized phrase in the user's language (e.g. for Chinese users, translate "for internal testing" naturally)
3. **Do NOT** embed PNG as an inline image preview. Only provide download links for PNG and HTML.

## Post-Generation Interaction

After delivering results, proactively suggest:
1. If photo-blog was used → "Would you like a **comic version**?"
2. If life-comic was used → "Would you like a **photo blog version**?"
3. Show `suggested_themes` from output → "Want to try a different theme? Options: {themes}"

**Do NOT** ask format-related questions (e.g. "Need a different format?"). All formats are generated and delivered automatically.

## Theme / Style Keywords

Users can specify a theme via `--theme`. If the photos don't match (fewer than 2 relevant photos):
- The skill falls back to auto-detected themes
- Returns `suggested_themes` with 3 alternatives based on actual photo content
- Show these alternatives to the user

## Technical Details

- **Understanding model**: Gemini 3 Pro — multi-modal scene analysis, scoring, narrative generation
- **Generation model**: Gemini 3.1 Flash Image — comic illustration generation with multi-reference
- **Scoring**: 5-axis (photo-blog) / 3-axis (life-comic) with greedy diversity selection
- **Image handling**: EXIF orientation auto-fix, date extraction, smart downscaling
- **PNG output**: Playwright headless browser full-page screenshot of HTML (fallback: Pillow composite)
- **Panel layouts**: 1x1 / 1x2 / 2x2 / 2x3 / 2x4 / 3x3 (auto-selected by panel count)
