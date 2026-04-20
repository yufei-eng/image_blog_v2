---
name: photo-blog
description: >-
  Photo blog generator with AI cover image. Analyze photos with Gemini 3 Pro, score
  and select highlights with diversity optimization, generate narrative-driven blog with
  poetic title, scene insights, and tips. Generates diverse AI cover images using a
  89-template style library matched to blog content (mood, theme, photo count).
  Supports 1-10 images, theme/style keywords, and triple output (HTML, rich text, PNG).
  Triggers when users request photo blog, life summary, travel log, photo diary, or
  visual story from images.
argument-hint: <image_directory_or_file>
metadata:
  execution_mode: sandbox
  adk_additional_tools:
    - imagen_generate
---

# Photo Blog Generator (with AI Cover)

Generate a beautiful, narrative-driven photo blog with an AI-generated cover image. Analyzes photos using Gemini 3 Pro for scene understanding, selects highlights with diversity optimization, generates a diverse cover via template-matched Gemini 3.1 Flash Image, and produces a styled blog with title, narrative, insights, and practical tips.

## When to Use

Trigger this skill when the user:
- Asks to create a photo blog, photo story, or image-based article
- Wants a **life summary**, daily recap, travel log, or memory collage from photos
- Says "summarize my recent photos", "make a photo diary", "create a visual story"
- Provides photos and asks for a narrative / writeup / summary / review
- Requests a styled blog post from a collection of images

## After Generation

After delivering the blog, proactively suggest:
1. "Would you like a **comic version** of this?" (invoke life-comic skill)
2. "Want to try a **different theme**?" and list the `suggested_themes` from the output

**Do NOT** ask format-related questions. All formats are generated and delivered automatically.

## Usage

The `main.py` script lives in the same directory as this SKILL.md. Use the directory where this file is located:

```bash
# The agent should resolve the path to this skill's directory automatically.
# Common locations after install.sh:
#   ~/.claude/skills/photo-blog/main.py   (Claude Code)
#   ~/.cursor/skills/photo-blog/main.py   (Cursor)

python3 <SKILL_DIR>/main.py <image_dir_or_files> \
    [--max-highlights 10] \
    [--output blog.html] \
    [--date 2026-04-13] \
    [--theme "food journey"] \
    [--style "minimalist"] \
    [--format html|richtext|png|all] \
    [--skip-cover] \
    [--save-analysis analysis.json]
```

### Arguments

| Arg | Description | Default |
|-----|-------------|---------|
| `input` | Image directory or file path | required |
| `--max-highlights` | Number of highlight photos (1-10) | 10 |
| `--output` | Output file path | `blog_output.html` |
| `--date` | Date for footer (auto-detected from EXIF if omitted) | auto |
| `--theme` | Theme keyword to guide generation (e.g., "food", "nightlife") | auto |
| `--style` | Style keyword (alias for --theme) | auto |
| `--format` | Output format: `html` / `richtext` / `png` / `all` | `all` |
| `--skip-cover` | Skip AI cover generation, use original photo as hero | false |
| `--save-analysis` | Save analysis JSON for debugging | none |

### Output Format Selection

By default (`--format all`), all three formats are generated every time:
- **HTML**: self-contained page with embedded images (best visual quality, interactive)
- **Rich Text**: Markdown compatible with Copilot block (`format: "markdown"`) (best for chat agents)
- **PNG**: single composite image (best for sharing / social)

### Delivering Results to User

**IMPORTANT**: After generation, upload ALL output files and provide **download links only** (no inline image preview):

1. **PNG** — upload via `mcp__proxy__upload_file` and provide a download link (e.g. "📷 [PNG download](<url>)")
2. **HTML** — upload via `mcp__proxy__upload_file` and provide a download link with i18n label:
   - English: `📄 [HTML version (for internal testing)](<url>)`
   - Chinese: `📄 [HTML 版本（供内部测试）](<url>)`
3. **Do NOT** embed PNG as an inline image (`![...](<url>)`). Provide download links only.

### Image Count Support

Supports **1 to 10** input images. Works with a single photo up to large albums (auto-selects top 10 highlights from any number of inputs).

### Theme / Style Keywords

Pass `--theme` to guide generation toward a specific angle. If the photos don't match the theme (fewer than 2 relevant photos), the skill falls back to auto-detected themes and returns `suggested_themes` with 3 alternatives.

## Configuration

The skill requires a `config.json` in the same directory as `main.py`. Copy from `config.json.example` and fill in the Compass API token:

```json
{
  "compass_api": {
    "base_url": "https://compass-api.example.com/v1",
    "service_name": "erhe-pm-aigc",
    "client_token": "<YOUR_TOKEN>",
    "understanding_model": "gemini-3-pro-preview",
    "generation_model": "gemini-3.1-flash-image-preview"
  }
}
```

Alternatively, set the `COMPASS_CLIENT_TOKEN` environment variable (takes precedence over config file).

If `config.json` is missing and the env var is not set, the script exits with `ERROR: Compass API client_token not found.` — create the config file before running.

## AI Cover Image

By default, an AI-generated cover image replaces the hero photo at the top of the blog. The cover is:

- **Template-driven**: Matched from a library of 89 analyzed reference styles
- **Content-aware**: Scoring considers photo count, mood, theme, and visual diversity
- **Style-diverse**: Diversity penalty ensures consecutive runs produce different aesthetics (kawaii, grunge, minimalist, magazine, retro, etc.)
- **Language-aware**: Text on the cover follows the blog language (English by default)

Use `--skip-cover` to fall back to the original highlight photo as hero.

## Capabilities

- Gemini 3 Pro multi-modal photo understanding (scene, mood, objects, narrative hooks)
- Multi-dimensional scoring (visual appeal, story value, emotion, uniqueness, technical quality)
- Diversity-optimized highlight selection (mood + location + scene variety)
- EXIF-based date extraction and orientation correction
- Theme-guided or auto-detected narrative generation
- AI cover image with 89-template style library and content-aware matching
- Triple output: HTML, rich text (Markdown), PNG composite
