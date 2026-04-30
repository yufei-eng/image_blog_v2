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
  sandbox_tools:
    - imagen_generate
    - image_understand
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

### Sandbox Mode (Pre-analyzed Data)

When running in sandbox environment (MCP tools not accessible from Python subprocess),
Claude Code should orchestrate the workflow and pass pre-computed data to the script:

```bash
python3 <SKILL_DIR>/main.py <image_dir> \
    --pre-analyzed analysis.json \
    --blog-content blog.json \
    --cover-path cover.png \
    --output blog.html \
    --format all
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
| `--pre-analyzed` | Load pre-analyzed photo data from JSON (skip MCP analysis) | none |
| `--blog-content` | Load pre-generated blog content from JSON (skip MCP text gen) | none |
| `--cover-path` | Use pre-generated cover image (skip MCP cover gen) | none |

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
   - Chinese: `📄 [HTML version (for internal testing)](<url>)`
3. **Do NOT** embed PNG as an inline image (`![...](<url>)`). Provide download links only.

### Image Count Support

Supports **1 to 10** input images. Works with a single photo up to large albums (auto-selects top 10 highlights from any number of inputs).

### Theme / Style Keywords

Pass `--theme` to guide generation toward a specific angle. If the photos don't match the theme (fewer than 2 relevant photos), the skill falls back to auto-detected themes and returns `suggested_themes` with 3 alternatives.

## Sandbox Execution Workflow

In sandbox, Python cannot call MCP tools. You must orchestrate the workflow yourself.

### ABSOLUTE PROHIBITIONS (violating these produces garbage output):
- **NEVER use `Read` on image files** — Read-based self-analysis is far below Gemini 3 Pro. You MUST use `image_understand`.
- **NEVER hand-write analysis JSON yourself** — analysis MUST come from `image_understand` (Gemini 3 Pro).
- **NEVER call `imagen_generate` without `image_urls`** — pass the photo download URLs so the cover is based on real photos.
- **NEVER write your own cover prompt** — use `--build-cover-prompt` to get the correct prompt with template-matched style.
- **NEVER shorten or summarize the cover prompt** — the prompt is precisely engineered from a 89-template library. Pass it COMPLETE.
- **NEVER call `TodoWrite`** — wastes turns.
- **NEVER run `main.py` without `--pre-analyzed`** — crashes (no MCP_PROXY_TOKEN).

### Step-by-step:

1. **Download images** — use `download_file` to get each image's download URL, then `curl` to save locally.
   **Save the download URLs** — you need them for steps 3 and 5.

2. **Export professional prompts** (run once, cache the output):
   ```bash
   python3 <SKILL_DIR>/main.py dummy --export-prompts 2>/dev/null
   ```
   Outputs JSON with `analysis_prompt`, `blog_generation_prompt_template`, `scoring_weights`, `tier_thresholds`.

3. **Analyze images using `image_understand` tool** (MANDATORY — do NOT skip):
   - Call `image_understand` with:
     - `prompt`: the `analysis_prompt` from step 2
     - `image_urls`: array of the download URLs from step 1 (NOT local file paths)
   - Parse the Gemini response and structure it into `analysis.json`:
     - Extract: scene, people, action, mood, location, time_of_day, objects, narrative_hook
     - Score on 5 axes per `scoring_weights`:
       visual_appeal(0.20), story_value(0.25), emotion_intensity(0.25),
       uniqueness(0.15), technical_quality(0.15)
     - Composite score (0-10), tiers per `tier_thresholds`: highlight(>=8.0), good(>=6.5), average(>=4.5), skip(<4.5)
   - Select top N highlights with diversity (vary mood, location, scene)
   - Save as `analysis.json`:
     ```json
     {
       "all": [
         {
           "file": "/path/to/photo.jpg",
           "scene": "A bustling night market with neon lights",
           "people": "A couple browsing food stalls",
           "action": "Selecting skewers from a vendor",
           "mood": "lively, excited",
           "location": "Night market street",
           "time_of_day": "evening",
           "objects": ["neon signs", "food stalls", "skewers"],
           "narrative_hook": "The glow of neon against their smiles",
           "orientation_correct": true,
           "score": 8.5,
           "tier": "highlight"
         }
       ],
       "highlights": [ ... ]
     }
     ```

4. **Generate blog content using the exported `blog_generation_prompt_template`**:
   - Fill in: `analysis_json`, `highlights_json`, `theme_instruction`, `lang_instruction`, `highlight_count`
   - Generate blog JSON matching this **exact structure**:
     ```json
     {
       "title": "A poetic 3-6 word title",
       "hero_image_index": 0,
       "description": { "text": "Under 150 chars atmospheric sentence", "image_index": 0 },
       "insights": [
         { "text": "Under 150 chars evocative caption", "image_index": 0 }
       ],
       "tip": "Under 150 chars practical tip",
       "footer_date": "YYYY-MM-DD",
       "suggested_themes": ["theme1", "theme2", "theme3"]
     }
     ```
   - **CRITICAL**: insights array must have exactly one entry per highlight photo
   - Save as `blog.json`

5. **Generate cover image** (MANDATORY — do NOT skip):
   - First, build the cover prompt using the template matching system:
     ```bash
     python3 <SKILL_DIR>/main.py dummy --build-cover-prompt blog.json 2>/dev/null
     ```
     This outputs the exact prompt to use. **NEVER write your own cover prompt** — the template system selects the correct style (photographic, not illustration).
   - Call `imagen_generate` MCP tool with:
     - `prompt`: the **COMPLETE, UNMODIFIED** output from the command above. Do NOT shorten or summarize — the prompt contains precisely-matched style instructions from a 89-template library.
     - `image_urls`: the SAME download URLs from step 1 (REQUIRED — so the cover reflects real photo content)
   - **Download via signed URL** (do NOT `curl` the imagen_generate URL directly — it requires auth and will return a Google OAuth HTML page):
     1. Extract the numeric file ID from the returned URL (e.g. `1312563282387555` from `.../media/file/1312563282387555.png`)
     2. Call `download_file` with `{"file_id": "<extracted_id>"}` to get a signed URL
     3. `curl` the signed URL to save as `cover.png`
     4. Verify the file is a real image (`file cover.png` should show PNG/JPEG, not HTML)
   - If `imagen_generate` fails or is cancelled, **retry it** — do NOT fall back to `--skip-cover`

6. **Run the script** with pre-computed data:
   ```bash
   python3 <SKILL_DIR>/main.py <image_dir> \
       --pre-analyzed analysis.json \
       --blog-content blog.json \
       --cover-path cover.png \
       --output blog.html \
       --format all
   ```

7. **Upload and deliver** — Upload generated files and provide download links.

## Configuration

### Sandbox (online)

No `config.json` needed. Claude Code orchestrates MCP tools directly and passes results
to the script via `--pre-analyzed`, `--blog-content`, `--cover-path` parameters.

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
