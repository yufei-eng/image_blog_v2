# Image Blog & Life Comic — Agent Guidelines

## Project Overview

Two Cursor/Claude Skills: **photo-blog** and **life-comic**, powered by Gemini 3 Pro (understanding) + Gemini 3.1 Flash Image (generation).

- **Language**: Python 3
- **Dependencies**: `google-genai`, `Pillow`, `Playwright` (for screenshots)
- **Models**: Gemini 3 Pro (image analysis/scoring), Gemini 3.1 Flash Image (comic generation)

## Build & Run

```bash
# Install
bash install.sh

# Update
bash update.sh

# Run photo-blog
python3 skills/photo-blog/main.py <image_paths> [--theme THEME] [--max-highlights N] [--format all]

# Run life-comic
python3 skills/life-comic/main.py <image_paths> [--theme THEME] [--panels N] [--format all]
```

## Directory Structure

```
image_blog/
├── install.sh                    # Install script (creates symlinks to ~/.claude/skills/)
├── update.sh                     # Update script
├── skills/
│   ├── photo-blog/
│   │   ├── SKILL.md              # Skill description
│   │   ├── main.py               # CLI entry point
│   │   ├── photo_analyzer.py     # Gemini image analysis/scoring
│   │   ├── blog_generator.py     # Blog content generation
│   │   ├── html_renderer.py      # HTML output
│   │   ├── png_renderer.py       # HiDPI PNG output (Playwright)
│   │   ├── config.json.example   # Config template
│   │   └── requirements.txt
│   └── life-comic/
│       ├── SKILL.md
│       ├── main.py
│       ├── photo_analyzer.py
│       ├── comic_generator.py    # Gemini comic generation
│       ├── html_renderer.py
│       ├── png_renderer.py
│       ├── config.json.example
│       └── requirements.txt
└── README.md
```

## Key Patterns

- **Triple Output**: Each generation produces HTML + Markdown + PNG simultaneously
- **HiDPI PNG**: Screenshots HTML pages via Playwright at 2x scale
- **Image Analysis**: Gemini 3 Pro scoring (0-100), multi-dimensional evaluation
- **Diversity Optimization**: Avoids duplicate scenes during selection, covers different times/locations
- **Config**: `config.json` stores `COMPASS_CLIENT_TOKEN`, never committed to Git

## Code Conventions

- Skill source files must be **pure English**, no Chinese characters
- Runtime output adapts to user's language
- Never expose internal fields like template_id to users
- Provide helpful error messages (e.g., "try using --theme to specify a theme")

## Delivery Rules

- Display **rich text** version in chat
- Provide PNG and HTML as **download links**, never inline
- Internationalize HTML link labels ("for internal testing" / localized equivalent)
- After generation, suggest the user try the other format (blog <-> comic)
