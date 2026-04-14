---
name: photo-blog
description: >-
  Photo blog generator. Analyze photos with Gemini 3 Pro, score and select highlights
  with diversity optimization, generate narrative-driven blog with poetic title, scene
  insights, and tips. Supports 1-9 images, theme/style keywords, and triple output
  (HTML, rich text, PNG). Triggers when users request photo blog, life summary, travel
  log, photo diary, or visual story from images.
argument-hint: <image_directory_or_file>
metadata:
  execution_mode: sandbox
  adk_additional_tools:
    - imagen_generate
---

# Photo Blog Generator

Generate a beautiful, narrative-driven photo blog from a set of images. Analyzes photos using Gemini 3 Pro for scene understanding, selects highlights with diversity optimization, and produces a styled blog with title, narrative, insights, and practical tips.

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
3. "Need a different format? I can provide **PNG image / HTML / rich text**."

## Usage

The `main.py` script lives in the same directory as this SKILL.md. Use the directory where this file is located:

```bash
# The agent should resolve the path to this skill's directory automatically.
# Common locations after install.sh:
#   ~/.claude/skills/photo-blog/main.py   (Claude Code)
#   ~/.cursor/skills/photo-blog/main.py   (Cursor)

python3 <SKILL_DIR>/main.py <image_dir_or_files> \
    [--max-highlights 9] \
    [--output blog.html] \
    [--date 2026-04-13] \
    [--theme "food journey"] \
    [--style "minimalist"] \
    [--format html|richtext|png|all] \
    [--save-analysis analysis.json]
```

### Arguments

| Arg | Description | Default |
|-----|-------------|---------|
| `input` | Image directory or file path | required |
| `--max-highlights` | Number of highlight photos (1-9) | 9 |
| `--output` | Output file path | `blog_output.html` |
| `--date` | Date for footer (auto-detected from EXIF if omitted) | auto |
| `--theme` | Theme keyword to guide generation (e.g., "food", "nightlife") | auto |
| `--style` | Style keyword (alias for --theme) | auto |
| `--format` | Output format: `html` / `richtext` / `png` / `all` | `all` |
| `--save-analysis` | Save analysis JSON for debugging | none |

### Output Format Selection

By default (`--format all`), all three formats are generated every time:
- **HTML**: self-contained page with embedded images (best for Cursor / Claude Code)
- **Rich Text**: Markdown compatible with Copilot block (`format: "markdown"`) (best for chat agents)
- **PNG**: single composite image (best for sharing / social)

The agent should pick the most appropriate format to display based on context, and always mention the PNG image path at the end.

### Image Count Support

Supports **1 to 9** input images. Works with a single photo up to large albums (auto-selects top 9 highlights from any number of inputs).

### Theme / Style Keywords

Pass `--theme` to guide generation toward a specific angle. If the photos don't match the theme (fewer than 2 relevant photos), the skill falls back to auto-detected themes and returns `suggested_themes` with 3 alternatives.

## Capabilities

- Gemini 3 Pro multi-modal photo understanding (scene, mood, objects, narrative hooks)
- Multi-dimensional scoring (visual appeal, story value, emotion, uniqueness, technical quality)
- Diversity-optimized highlight selection (mood + location + scene variety)
- EXIF-based date extraction and orientation correction
- Theme-guided or auto-detected narrative generation
- Triple output: HTML, rich text (Markdown), PNG composite
