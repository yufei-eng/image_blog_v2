#!/usr/bin/env python3
"""Photo Blog Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--max-highlights 8] [--output blog.html] [--date 2026年4月13日]

Workflow:
    1. Batch analyze photos via Gemini 3 Pro (understanding)
    2. Score and select highlight photos (diversity-optimized)
    3. Generate blog narrative (title / description / insights / tips)
    4. Render to self-contained HTML
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
    parser.add_argument("--max-highlights", type=int, default=8, help="Max highlight photos")
    parser.add_argument("--output", default="blog_output.html", help="Output HTML path")
    parser.add_argument("--date", default=None, help="Date string for footer")
    parser.add_argument("--save-analysis", default=None, help="Save analysis JSON to file")
    args = parser.parse_args()

    print("=" * 60)
    print("  PHOTO BLOG GENERATOR")
    print("=" * 60)

    # Step 1: Collect images
    image_paths = collect_images(args.input)
    if not image_paths:
        print("No images found.")
        sys.exit(1)
    print(f"\n[1/4] Found {len(image_paths)} images")

    # Step 2: Analyze
    print(f"\n[2/4] Analyzing photos with Gemini 3 Pro...")
    analyses = analyze_photos(image_paths)
    print(f"  Analyzed {len(analyses)} photos")

    # Step 3: Select highlights
    print(f"\n[3/4] Selecting top {args.max_highlights} highlights...")
    highlights = select_highlights(analyses, args.max_highlights)
    print(f"  Selected {len(highlights)} highlights:")
    for i, h in enumerate(highlights):
        print(f"    #{i+1} [{h.score.tier}] {h.score.composite:.1f} — {h.scene}")

    # Save analysis if requested
    all_dicts = [analysis_to_dict(a) for a in analyses]
    highlight_dicts = [analysis_to_dict(h) for h in highlights]

    if args.save_analysis:
        with open(args.save_analysis, "w", encoding="utf-8") as f:
            json.dump({"all": all_dicts, "highlights": highlight_dicts}, f, ensure_ascii=False, indent=2)
        print(f"  Analysis saved to {args.save_analysis}")

    # Auto-detect date from photos if not provided
    date_str = args.date
    if not date_str:
        for p in image_paths:
            date_str = extract_photo_date(p)
            if date_str:
                break

    # Step 4: Generate blog content
    print(f"\n[4/4] Generating blog content...")
    blog_content = generate_blog_content(all_dicts, highlight_dicts, date_str=date_str)
    print(f"  Title: {blog_content.get('title', '?')}")
    print(f"  Insights: {len(blog_content.get('insights', []))} items")
    print(f"  Tip: {blog_content.get('tip', '?')[:50]}...")

    # Step 5: Render HTML
    highlight_paths = [h.file_path for h in highlights]
    output_path = render_blog_html(blog_content, highlight_paths, args.output)
    print(f"\n{'=' * 60}")
    print(f"  Blog generated: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
