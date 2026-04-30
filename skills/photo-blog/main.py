#!/usr/bin/env python3
"""Photo Blog Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--max-highlights 10] [--output blog.html] [--date 2026-04-13]
        [--theme "food journey"] [--format html] [--skip-cover] [--output-dir .]

    Sandbox mode (pre-analyzed data from Claude Code):
    python3 main.py <image_dir> --pre-analyzed analysis.json --blog-content blog.json
        [--cover-path cover.png] [--output blog.html] [--format all]

Workflow:
    1. Batch analyze photos via MCP image_understand (or load from --pre-analyzed)
    2. Score and select highlight photos (diversity-optimized)
    3. Generate blog narrative via MCP (or load from --blog-content)
    4. Generate AI cover image via MCP imagen_generate (or use --cover-path)
    5. Render to selected format (HTML / rich text / PNG / all)
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "shared")
sys.path.insert(0, SCRIPT_DIR)
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from mcp_client import create_mcp_client
from file_uploader import FileUploader
from image_analyzer import analyze_photos, select_highlights, PhotoAnalysis, extract_photo_date
from blog_generator import generate_blog_content
from html_renderer import render_blog_html

try:
    from cover_generator import generate_cover_image
except ImportError:
    generate_cover_image = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def collect_images(path: str) -> list[str]:
    """Collect image file paths from a directory or file argument."""
    if os.path.isdir(path):
        files = sorted([
            os.path.join(path, f) for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        ])
        return files
    elif os.path.isfile(path):
        return [path]
    else:
        print(f"ERROR: Path not found: {path}")
        return []


def analysis_to_dict(a: PhotoAnalysis) -> dict:
    return {
        "file": a.file_path,
        "scene": a.scene,
        "people": a.people,
        "action": a.action,
        "mood": a.mood,
        "location": a.location,
        "time_of_day": a.time_of_day,
        "objects": a.objects,
        "narrative_hook": a.narrative_hook,
        "orientation_correct": a.orientation_correct,
        "score": a.score.composite,
        "tier": a.score.tier,
    }


def main():
    parser = argparse.ArgumentParser(description="Photo Blog Generator")
    parser.add_argument("input", help="Image directory or file path")
    parser.add_argument("--max-highlights", type=int, default=10, help="Max highlight photos (1-10)")
    parser.add_argument("--output", default="blog_output.html", help="Output HTML path")
    parser.add_argument("--date", default=None, help="Date string for footer")
    parser.add_argument("--save-analysis", default=None, help="Save analysis JSON to file")
    parser.add_argument("--theme", default=None, help="Theme/style keyword to guide generation")
    parser.add_argument("--style", default=None, help="Style keyword (alias for --theme)")
    parser.add_argument("--format", default="all", choices=["html", "richtext", "png", "all"],
                        help="Output format: html, richtext (markdown for chat), png, all (default)")
    parser.add_argument("--skip-cover", action="store_true",
                        help="Skip AI cover image generation, use original photo as hero")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for generated images (default: same as --output)")
    parser.add_argument("--pre-analyzed", default=None,
                        help="Pre-analyzed JSON file (skip MCP image analysis)")
    parser.add_argument("--blog-content", default=None,
                        help="Pre-generated blog content JSON (skip MCP text generation)")
    parser.add_argument("--cover-path", default=None,
                        help="Pre-generated cover image path (skip MCP cover generation)")
    parser.add_argument("--export-prompts", action="store_true",
                        help="Export prompt templates as JSON and exit (for sandbox mode)")
    parser.add_argument("--build-cover-prompt", default=None,
                        help="Build cover imagen prompt from blog content JSON and exit (for sandbox mode)")
    args = parser.parse_args()

    if args.build_cover_prompt:
        from cover_generator import _extract_cover_context, _load_template_library, _match_template, _build_cover_prompt, _build_fallback_prompt
        with open(args.build_cover_prompt, encoding="utf-8") as f:
            blog = json.load(f)
        lang = blog.get("_lang", "en")
        ctx = _extract_cover_context(blog)
        templates = _load_template_library()
        if templates:
            template = _match_template(templates, ctx)
            prompt = _build_cover_prompt(template, ctx, lang=lang)
            print(f"[TEMPLATE] {template.get('style_category', '?')} / {template.get('layout_type', '?')}", file=sys.stderr)
        else:
            prompt = _build_fallback_prompt(ctx, lang=lang)
            print("[TEMPLATE] fallback (no template library)", file=sys.stderr)
        print(prompt)
        sys.exit(0)

    if args.export_prompts:
        from image_analyzer import ANALYSIS_PROMPT
        from blog_generator import BLOG_GENERATION_PROMPT
        prompts = {
            "analysis_prompt": ANALYSIS_PROMPT,
            "blog_generation_prompt_template": BLOG_GENERATION_PROMPT,
            "blog_generation_variables": ["analysis_json", "highlights_json",
                                           "theme_instruction", "lang_instruction",
                                           "highlight_count"],
            "scoring_weights": {"visual_appeal": 0.20, "story_value": 0.25,
                               "emotion_intensity": 0.25, "uniqueness": 0.15,
                               "technical_quality": 0.15},
            "tier_thresholds": {"highlight": 8.0, "good": 6.5, "average": 4.5}
        }
        print(json.dumps(prompts, ensure_ascii=False, indent=2))
        sys.exit(0)

    user_theme = args.theme or args.style
    max_hl = min(max(args.max_highlights, 1), 10)

    print("=" * 60)
    print("  PHOTO BLOG GENERATOR v0.3")
    print("=" * 60)

    image_paths = collect_images(args.input)
    if not image_paths:
        print("No images found.")
        sys.exit(1)
    skip_cover = args.skip_cover or generate_cover_image is None or args.cover_path is not None
    needs_mcp = not args.pre_analyzed or not args.blog_content or (not skip_cover and not args.cover_path)
    total_steps = 4 if skip_cover else 5
    print(f"\n[1/{total_steps}] Found {len(image_paths)} images")

    cfg = {}
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg = json.load(f)

    mcp = None
    uploader = None
    if needs_mcp:
        mcp = create_mcp_client(cfg)
        mcp.connect()
        uploader = FileUploader(cfg)

    try:
        if args.pre_analyzed:
            print(f"\n[2/{total_steps}] Loading pre-analyzed data from {args.pre_analyzed}...")
            with open(args.pre_analyzed, encoding="utf-8") as f:
                pre_data = json.load(f)
            all_dicts = pre_data.get("all", pre_data.get("highlights", []))
            highlight_dicts = pre_data.get("highlights", all_dicts)
            highlight_paths = [h["file"] for h in highlight_dicts]
            orientation_flags = [h.get("orientation_correct", True) for h in highlight_dicts]
            print(f"  Loaded {len(all_dicts)} analyses, {len(highlight_dicts)} highlights")
        else:
            print(f"\n[2/{total_steps}] Analyzing photos via MCP image_understand...")
            analyses = analyze_photos(image_paths, mcp_client=mcp, uploader=uploader)
            print(f"  Analyzed {len(analyses)} photos")

            effective_max = min(max_hl, len(analyses))
            print(f"\n[3/{total_steps}] Selecting top {effective_max} highlights...")
            highlights = select_highlights(analyses, effective_max)
            print(f"  Selected {len(highlights)} highlights:")
            for i, h in enumerate(highlights):
                print(f"    #{i+1} [{h.score.tier}] {h.score.composite:.1f} — {h.scene}")

            all_dicts = [analysis_to_dict(a) for a in analyses]
            highlight_dicts = [analysis_to_dict(h) for h in highlights]
            highlight_paths = [h.file_path for h in highlights]
            orientation_flags = [h.orientation_correct for h in highlights]

            if args.save_analysis:
                with open(args.save_analysis, "w", encoding="utf-8") as f:
                    json.dump({"all": all_dicts, "highlights": highlight_dicts}, f, ensure_ascii=False, indent=2)
                print(f"  Analysis saved to {args.save_analysis}")

        date_str = args.date
        if not date_str:
            for p in image_paths:
                date_str = extract_photo_date(p)
                if date_str:
                    break

        def _detect_lang(text):
            if not text:
                return "en"
            cjk = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
            return "zh" if cjk / max(len(text.replace(" ", "")), 1) > 0.15 else "en"

        lang = _detect_lang(user_theme)
        if user_theme:
            print(f"\n  Theme: '{user_theme}' (lang={lang})")

        if args.blog_content:
            print(f"\n[4/{total_steps}] Loading blog content from {args.blog_content}...")
            with open(args.blog_content, encoding="utf-8") as f:
                blog_content = json.load(f)
            print(f"  Title: {blog_content.get('title', '?')}")
        else:
            print(f"\n[4/{total_steps}] Generating blog content...")
            blog_content = generate_blog_content(all_dicts, highlight_dicts, date_str=date_str, user_theme=user_theme, lang=lang, target_count=len(highlight_dicts), mcp_client=mcp, uploader=uploader, highlight_paths=highlight_paths)
            print(f"  Title: {blog_content.get('title', '?')}")
            print(f"  Insights: {len(blog_content.get('insights', []))} items")
            actual_insights = len(blog_content.get("insights", []))
            if actual_insights < len(highlight_dicts):
                print(f"  [WARN] Blog returned {actual_insights} insights, expected {len(highlight_dicts)}")

        suggested = blog_content.get("suggested_themes", [])
        if suggested:
            print(f"  Suggested themes: {', '.join(suggested)}")

        output_base = os.path.splitext(args.output)[0]
        output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.output)) or "."
        os.makedirs(output_dir, exist_ok=True)

        cover_path = args.cover_path
        if cover_path:
            print(f"\n  Using pre-generated cover: {cover_path}")
        elif not skip_cover:
            print(f"\n[5/{total_steps}] Generating AI cover image...")
            cover_path = generate_cover_image(blog_content, highlight_paths, output_dir=output_dir, lang=lang, mcp_client=mcp, uploader=uploader)
            if cover_path:
                print(f"  Cover generated: {cover_path}")
            else:
                print(f"  Cover generation failed, falling back to original photo")
        elif not args.skip_cover and not args.cover_path:
            print(f"\n  [SKIP] cover_generator not available, using original photo as hero")

        generated_files = {}
        html_output = None

        if args.format in ("html", "all"):
            html_output = render_blog_html(blog_content, highlight_paths, args.output, cover_path=cover_path, orientation_flags=orientation_flags)
            generated_files["html"] = html_output
            print(f"\n  [HTML] {html_output}")

        if args.format in ("richtext", "all"):
            from richtext_renderer import render_blog_richtext
            rt_path = output_base + "_richtext.md"
            render_blog_richtext(blog_content, highlight_paths, rt_path, cover_path=cover_path)
            generated_files["richtext"] = rt_path
            print(f"  [Rich Text] {rt_path}")

        if args.format in ("png", "all"):
            from png_renderer import render_blog_png
            png_path = output_base + ".png"
            if not html_output:
                html_output = render_blog_html(blog_content, highlight_paths, output_base + "_tmp.html", cover_path=cover_path, orientation_flags=orientation_flags)
            result = render_blog_png(blog_content, highlight_paths, png_path, html_path=html_output)
            if result:
                generated_files["png"] = png_path
                print(f"  [PNG] {png_path}")

        print(f"\n{'=' * 60}")
        print(f"  Blog generated (v0.3 — with AI cover)")
        for fmt, path in generated_files.items():
            print(f"  [{fmt.upper()}] {path}")
        if cover_path:
            print(f"  [COVER] {cover_path}")
        if "png" in generated_files:
            print(f"\n  >>> IMAGE RESULT (shareable): {generated_files['png']}")
        if "richtext" in generated_files:
            print(f"  >>> RICH TEXT (for chat): {generated_files['richtext']}")
        print(f"{'=' * 60}")

        _html_label = ("HTML 版本（供内部测试）"
                       if lang == "zh" else "HTML version (for internal testing)")
        print(f"\n>>> UPLOAD INSTRUCTIONS (follow exactly):")
        if "png" in generated_files:
            print(f"  Upload {generated_files['png']}")
            print(f'  Link text: "\U0001f4f7 [PNG download](<url>)"')
        if "html" in generated_files:
            print(f"  Upload {generated_files['html']}")
            print(f'  Link text: "\U0001f4c4 [{_html_label}](<url>)"')
        print(f"  Do NOT embed images inline with ![...]. Provide download links only.")
    finally:
        if mcp:
            mcp.close()
        if uploader:
            uploader.close()


if __name__ == "__main__":
    main()
