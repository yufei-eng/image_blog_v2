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
    - batch_understand_images
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

### Sandbox Mode (Pre-analyzed Data)

When running in sandbox environment (MCP tools not accessible from Python subprocess),
Claude Code should orchestrate the workflow and pass pre-computed data to the script:

```bash
python3 <SKILL_DIR>/main.py <image_dir> \
    --pre-analyzed analysis.json \
    --storyboard storyboard.json \
    --comic-images-dir ./comic_imgs \
    --output comic.html \
    --format all
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
| `--pre-analyzed` | Load pre-analyzed moment data from JSON (skip MCP analysis) | none |
| `--storyboard` | Load pre-generated storyboard from JSON (skip MCP storyboard gen) | none |
| `--comic-images-dir` | Directory with pre-generated comic images (skip MCP image gen) | none |

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
   - Chinese: `📄 [HTML version (for internal testing)](<url>)`
3. **Do NOT** embed PNG as an inline image (`![...](<url>)`). Provide download links only.

### Panel Count Support

Supports **1 to 10** panels. The grid layout adapts automatically:
- 1 panel: 1x1 | 2: 1x2 | 3: 1x3 | 4: 2x2 | 5-6: 2x3 | 7-8: 2x4 | 9: 3x3 | 10: 2x5

### Theme / Style Keywords

Pass `--theme` to guide comic theme. Falls back to auto-detected themes if photos don't match, with `suggested_themes` providing 3 alternatives.

## Sandbox Execution Workflow

In sandbox environment, Python scripts cannot call MCP tools directly (no MCP_PROXY_TOKEN in subprocess).
Claude Code must orchestrate the workflow by calling MCP tools itself and passing results to the script.

**CRITICAL**: Use the professional prompts exported from the Python engine — do NOT improvise your own analysis criteria.

### Step-by-step:

1. **Export professional prompts** (run once per session, cache the output):
   ```bash
   python3 <SKILL_DIR>/main.py dummy --export-prompts 2>/dev/null
   ```
   This outputs JSON containing the exact `analysis_prompt` and `storyboard_prompt_template`
   used by the Python analysis engine, along with `scoring_weights` and `tier_thresholds`.

2. **Analyze images using the exported `analysis_prompt`**:
   - For each photo, use the Read tool to view it
   - Apply the `analysis_prompt` criteria exactly as specified:
     - Extract: scene_summary, character_desc, action_desc, emotion, environment, time_of_day, comic_panel_desc
     - Score each photo on 3 axes using the exported `scoring_weights`:
       comic_potential(0.35), visual_distinctness(0.30), narrative_weight(0.35)
     - Calculate weighted composite score (0-10 scale)
     - Assign tiers per `tier_thresholds`: star_moment(>=7.5), good_moment(>=6.0), average(>=4.0), skip(<4.0)
   - Select top N panels with diversity optimization (emotion + environment + time_of_day variety)
   - Save as `analysis.json`:
     ```json
     {
       "all": [
         {
           "file": "/path/to/photo.jpg",
           "scene_summary": "Friends laughing over hotpot",
           "character_desc": "Three friends, casual clothes",
           "action_desc": "Reaching for ingredients with chopsticks",
           "emotion": "joyful, warm",
           "environment": "Indoor hotpot restaurant, steamy",
           "time_of_day": "evening",
           "comic_panel_desc": "Wide shot of friends around a bubbling hotpot",
           "score": 8.5,
           "tier": "star_moment"
         }
       ],
       "selected": [ ... ]
     }
     ```

3. **Generate storyboard using the exported `storyboard_prompt_template`**:
   - Take the `storyboard_prompt_template` and fill in the variables:
     - `panels_json`: selected comic moments with index, scene, character, action, emotion, environment, time_of_day, comic_panel_desc
     - `theme_instruction`: use theme template if user specified a theme, empty string otherwise
     - `lang_instruction`: Chinese or English instruction based on user language
     - `panel_count`: number of panels
   - Generate storyboard JSON matching this **exact structure** (field names must match):
     ```json
     {
       "theme": "A 2-6 word theme",
       "emotional_arc": "Under 100 chars arc description",
       "panels": [
         {
           "panel_index": 0,
           "source_photo_index": 0,
           "scene_description": "3-5 sentence detailed visual description (in English)",
           "emotion_tag": "2-4 word emotion tag",
           "panel_composition": "Composition suggestion"
         }
       ],
       "narrative": {
         "title": "Title matching the theme",
         "body": "Under 250 chars poetic narrative"
       },
       "footer_date": "YYYY-MM-DD",
       "suggested_themes": ["theme1", "theme2", "theme3"]
     }
     ```
   - **CRITICAL**: panels array must have exactly one entry per selected moment
   - Save as `storyboard.json`

4. **Generate comic images** (optional):
   - Call `imagen_generate` MCP tool with reference photos and comic prompts
   - Download results to a directory (e.g., `./comic_imgs/`)

5. **Run the script** with pre-computed data:
   ```bash
   python3 <SKILL_DIR>/main.py <image_dir> \
       --pre-analyzed analysis.json \
       --storyboard storyboard.json \
       --comic-images-dir ./comic_imgs \
       --output comic.html \
       --format all
   ```

6. **Upload and deliver** — Upload generated files and provide download links.

## Configuration

### Sandbox (online)

No `config.json` needed. Claude Code orchestrates MCP tools directly and passes results
to the script via `--pre-analyzed`, `--storyboard`, `--comic-images-dir` parameters.

### Direct MCP mode (non-sandbox)

When running outside sandbox, the script calls MCP tools directly via HTTP.
Create `config.json` in the same directory as `main.py`:

```json
{
  "mcp_server": {
    "url": "<mcpserver_sse_endpoint>",
    "timeout": 300
  },
  "file_upload": {
    "url": "<file_upload_endpoint>",
    "timeout": 60
  }
}
```

Environment variable overrides: `MCP_SERVER_URL`, `FILE_UPLOAD_URL`.

## Capabilities

- Gemini 3 Pro comic-potential analysis (dynamism, visual distinctness, narrative weight)
- Diversity-optimized panel selection (emotion + scene + time variety)
- Warm hand-drawn illustration style comic generation via Gemini 3.1 Flash Image
- EXIF-based date extraction and orientation correction
- Theme-guided or auto-detected storyboard creation
- Triple output: HTML, rich text (Markdown), PNG composite
