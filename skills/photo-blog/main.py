#!/usr/bin/env python3
"""Photo Blog Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--max-highlights 9] [--output blog.html] [--date 2026-04-13]
        [--theme "food journey"] [--format html]

Workflow:
    1. Batch analyze photos via Gemini 3 Pro (understanding)
    2. Score and select highlight photos (diversity-optimized)
    3. Generate blog narrative (title / description / insights / tips)
    4. Render to selected format (HTML / rich text / PNG / all)
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
    print(f"\n[1/4] Found {len(image_paths)} images")

    print(f"\n[2/4] Analyzing photos with Gemini 3 Pro...")
    analyses = analyze_photos(image_paths)
    print(f"  Analyzed {len(analyses)} photos")

    effective_max = min(max_hl, len(analyses))
    print(f"\n[3/4] Selecting top {effective_max} highlights...")
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

    if user_theme:
        print(f"\n  Theme: '{user_theme}'")

    print(f"\n[4/4] Generating blog content...")
    blog_content = generate_blog_content(all_dicts, highlight_dicts, date_str=date_str, user_theme=user_theme)
    print(f"  Title: {blog_content.get('title', '?')}")
    print(f"  Insights: {len(blog_content.get('insights', []))} items")

    suggested = blog_content.get("suggested_themes", [])
    if suggested:
        print(f"  Suggested themes: {', '.join(suggested)}")

    highlight_paths = [h.file_path for h in highlights]
    output_base = os.path.splitext(args.output)[0]

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
        render_blog_png(blog_content, highlight_paths, png_path, html_path=html_output)
        generated_files["png"] = png_path
        print(f"  [PNG] {png_path}")

    print(f"\n{'=' * 60}")
    print(f"  Blog generated (v0.2)")
    for fmt, path in generated_files.items():
        print(f"  [{fmt.upper()}] {path}")
    if "png" in generated_files:
        print(f"\n  >>> IMAGE RESULT (shareable): {generated_files['png']}")
    if "richtext" in generated_files:
        print(f"  >>> RICH TEXT (for chat): {generated_files['richtext']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
