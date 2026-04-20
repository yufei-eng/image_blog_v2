---
name: life-comic
description: >-
  Life comic generator. Analyze photos with Gemini 3 Pro for comic-worthy moments,
  design storyboard with emotional narrative, generate warm hand-drawn illustration
  style multi-panel comic via Gemini 3.1 Flash Image. Supports 1-10 panels with
  adaptive grid layout, theme/style keywords, and triple output (HTML, rich text, PNG).
  Triggers when users request comic strip, manga, illustrated story, visual diary,
  or comic-style summary from photos.
argument-hint: <image_directory_or_file>
metadata:
  execution_mode: sandbox
  adk_additional_tools:
    - imagen_generate
---

# Life Comic Generator

Transform a set of photos into a warm, hand-drawn style comic strip with emotional narrative. Uses Gemini 3 Pro for scene analysis and Gemini 3.1 Flash Image for comic generation.

## When to Use

Trigger this skill when the user:
- Asks to create a comic, manga, or illustrated story from photos
- Wants a **life comic**, visual diary, or memory strip
- Says "turn my photos into a comic", "make a comic strip", "illustrate my day"
- Requests a comic-style summary of recent events or travel
- Provides photos and asks for a fun / artistic / illustrated version

## After Generation

After delivering the comic, proactively suggest:
1. "Would you like a **photo blog version** instead?" (invoke photo-blog skill)
2. "Want to try a **different theme**?" and list the `suggested_themes` from the output

**Do NOT** ask format-related questions. All formats are generated and delivered automatically.

## Usage

The `main.py` script lives in the same directory as this SKILL.md. Use the directory where this file is located:

```bash
# The agent should resolve the path to this skill's directory automatically.
# Common locations after install.sh:
#   ~/.claude/skills/life-comic/main.py   (Claude Code)
#   ~/.cursor/skills/life-comic/main.py   (Cursor)

python3 <SKILL_DIR>/main.py <image_dir_or_files> \
    [--panels 6] \
    [--output comic.html] \
    [--date 2026-04-13] \
    [--output-dir ./output] \
    [--theme "food journey"] \
    [--style "adventure"] \
    [--format html|richtext|png|all] \
    [--save-analysis analysis.json] \
    [--skip-image-gen]
```

### Arguments

| Arg | Description | Default |
|-----|-------------|---------|
| `input` | Image directory or file path | required |
| `--panels` | Number of comic panels (1-10) | 6 |
| `--output` | Output file path | `comic_output.html` |
| `--date` | Date for footer (auto-detected from EXIF if omitted) | auto |
| `--output-dir` | Directory for generated comic images | `.` |
| `--theme` | Theme keyword to guide generation | auto |
| `--style` | Style keyword (alias for --theme) | auto |
| `--format` | Output format: `html` / `richtext` / `png` / `all` | `all` |
| `--save-analysis` | Save analysis JSON for debugging | none |
| `--skip-image-gen` | Skip comic image generation (storyboard only) | false |

### Output Format Selection

By default (`--format all`), all three formats are generated every time:
- **HTML**: self-contained page with comic image + narrative (best visual quality, interactive)
- **Rich Text**: Markdown for Copilot block (best for chat agents)
- **PNG**: single composite image (best for sharing / social)

### Delivering Results to User

**IMPORTANT**: After generation, upload ALL output files and provide **download links only** (no inline image preview):

1. **PNG** — upload via `mcp__proxy__upload_file` and provide a download link (e.g. "📷 [PNG download](<url>)")
2. **HTML** — upload via `mcp__proxy__upload_file` and provide a download link with i18n label:
   - English: `📄 [HTML version (for internal testing)](<url>)`
   - Chinese: `📄 [HTML 版本（供内部测试）](<url>)`
3. **Do NOT** embed PNG as an inline image (`![...](<url>)`). Provide download links only.

### Panel Count Support

Supports **1 to 10** panels. The grid layout adapts automatically:
- 1 panel: 1x1 | 2: 1x2 | 3: 1x3 | 4: 2x2 | 5-6: 2x3 | 7-8: 2x4 | 9: 3x3 | 10: 2x5

### Theme / Style Keywords

Pass `--theme` to guide comic theme. Falls back to auto-detected themes if photos don't match, with `suggested_themes` providing 3 alternatives.

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

## Capabilities

- Gemini 3 Pro comic-potential analysis (dynamism, visual distinctness, narrative weight)
- Diversity-optimized panel selection (emotion + scene + time variety)
- Warm hand-drawn illustration style comic generation via Gemini 3.1 Flash Image
- EXIF-based date extraction and orientation correction
- Theme-guided or auto-detected storyboard creation
- Triple output: HTML, rich text (Markdown), PNG composite
