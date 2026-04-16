#!/usr/bin/env python3
"""Photo Blog Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--max-highlights 9] [--output blog.html] [--date 2026-04-13]
        [--theme "food journey"] [--format html] [--skip-cover] [--output-dir .]

Workflow:
    1. Batch analyze photos via Gemini 3 Pro (understanding)
    2. Score and select highlight photos (diversity-optimized)
    3. Generate blog narrative (title / description / insights / tips)
    4. Generate AI cover image (Gemini 3.1 Flash Image)
    5. Render to selected format (HTML / rich text / PNG / all)
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

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
        "score": a.score.composite,
        "tier": a.score.tier,
    }


def main():
    parser = argparse.ArgumentParser(description="Photo Blog Generator")
    parser.add_argument("input", help="Image directory or file path")
    parser.add_argument("--max-highlights", type=int, default=9, help="Max highlight photos (1-9)")
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
    args = parser.parse_args()

    user_theme = args.theme or args.style
    max_hl = min(max(args.max_highlights, 1), 9)

    print("=" * 60)
    print("  PHOTO BLOG GENERATOR v0.2")
    print("=" * 60)

    image_paths = collect_images(args.input)
    if not image_paths:
        print("No images found.")
        sys.exit(1)
    skip_cover = args.skip_cover or generate_cover_image is None
    total_steps = 4 if skip_cover else 5
    print(f"\n[1/{total_steps}] Found {len(image_paths)} images")

    print(f"\n[2/{total_steps}] Analyzing photos with Gemini 3 Pro...")
    analyses = analyze_photos(image_paths)
    print(f"  Analyzed {len(analyses)} photos")

    effective_max = min(max_hl, len(analyses))
    print(f"\n[3/{total_steps}] Selecting top {effective_max} highlights...")
    highlights = select_highlights(analyses, effective_max)
    print(f"  Selected {len(highlights)} highlights:")
    for i, h in enumerate(highlights):
        print(f"    #{i+1} [{h.score.tier}] {h.score.composite:.1f} — {h.scene}")

    all_dicts = [analysis_to_dict(a) for a in analyses]
    highlight_dicts = [analysis_to_dict(h) for h in highlights]

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
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
        return "zh" if cjk / max(len(text.replace(" ", "")), 1) > 0.15 else "en"

    lang = _detect_lang(user_theme)
    if user_theme:
        print(f"\n  Theme: '{user_theme}' (lang={lang})")

    print(f"\n[4/{total_steps}] Generating blog content...")
    blog_content = generate_blog_content(all_dicts, highlight_dicts, date_str=date_str, user_theme=user_theme, lang=lang)
    print(f"  Title: {blog_content.get('title', '?')}")
    print(f"  Insights: {len(blog_content.get('insights', []))} items")

    suggested = blog_content.get("suggested_themes", [])
    if suggested:
        print(f"  Suggested themes: {', '.join(suggested)}")

    highlight_paths = [h.file_path for h in highlights]
    output_base = os.path.splitext(args.output)[0]
    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.output)) or "."
    os.makedirs(output_dir, exist_ok=True)

    cover_path = None
    if not skip_cover:
        print(f"\n[5/{total_steps}] Generating AI cover image...")
        cover_path = generate_cover_image(blog_content, highlight_paths, output_dir=output_dir)
        if cover_path:
            print(f"  Cover generated: {cover_path}")
        else:
            print(f"  Cover generation failed, falling back to original photo")
    elif not args.skip_cover:
        print(f"\n  [SKIP] cover_generator not available, using original photo as hero")

    generated_files = {}
    html_output = None

    if args.format in ("html", "all"):
        html_output = render_blog_html(blog_content, highlight_paths, args.output)
        generated_files["html"] = html_output
        print(f"\n  [HTML] {html_output}")

    if args.format in ("richtext", "all"):
        from richtext_renderer import render_blog_richtext
        rt_path = output_base + "_richtext.md"
        render_blog_richtext(blog_content, highlight_paths, rt_path)
        generated_files["richtext"] = rt_path
        print(f"  [Rich Text] {rt_path}")

    if args.format in ("png", "all"):
        from png_renderer import render_blog_png
        png_path = output_base + ".png"
        if not html_output:
            html_output = render_blog_html(blog_content, highlight_paths, output_base + "_tmp.html")
        result = render_blog_png(blog_content, highlight_paths, png_path, html_path=html_output)
        if result:
            generated_files["png"] = png_path
            print(f"  [PNG] {png_path}")

    print(f"\n{'=' * 60}")
    print(f"  Blog generated (v0.3 \u2014 with AI cover)")
    for fmt, path in generated_files.items():
        print(f"  [{fmt.upper()}] {path}")
    if cover_path:
        print(f"  [COVER] {cover_path}")
    if "png" in generated_files:
        print(f"\n  >>> IMAGE RESULT (shareable): {generated_files['png']}")
    if "richtext" in generated_files:
        print(f"  >>> RICH TEXT (for chat): {generated_files['richtext']}")
    print(f"{'=' * 60}")

    _html_label = ("HTML \u7248\u672c\uff08\u4f9b\u5185\u90e8\u6d4b\u8bd5\uff09"
                   if lang == "zh" else "HTML version (for internal testing)")
    print(f"\n>>> UPLOAD INSTRUCTIONS (follow exactly):")
    if "png" in generated_files:
        print(f"  Upload {generated_files['png']}")
        print(f'  Link text: "\U0001f4f7 [PNG download](<url>)"')
    if "html" in generated_files:
        print(f"  Upload {generated_files['html']}")
        print(f'  Link text: "\U0001f4c4 [{_html_label}](<url>)"')
    print(f"  Do NOT embed images inline with ![...]. Provide download links only.")


if __name__ == "__main__":
    main()
