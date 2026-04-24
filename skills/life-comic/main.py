#!/usr/bin/env python3
"""Life Comic Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--panels 8] [--output comic.html] [--date 2026-04-13]
        [--theme "food journey"] [--format html]

Workflow:
    1. Batch analyze photos via MCP batch_understand_images (identify comic-worthy moments)
    2. Select top moments with narrative diversity
    3. Generate storyboard script and emotional narrative via MCP
    4. Generate multi-panel comic image via MCP imagen_generate
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
from image_analyzer import analyze_photos, select_comic_panels, ComicMoment, extract_photo_date
from comic_generator import generate_storyboard, generate_comic_image
from html_renderer import render_comic_html

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def collect_images(path: str) -> list[str]:
    if os.path.isdir(path):
        return sorted([
            os.path.join(path, f) for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        ])
    elif os.path.isfile(path):
        return [path]
    else:
        print(f"ERROR: Path not found: {path}")
        return []


def moment_to_dict(m: ComicMoment) -> dict:
    return {
        "file": m.file_path,
        "scene_summary": m.scene_summary,
        "character_desc": m.character_desc,
        "action_desc": m.action_desc,
        "emotion": m.emotion,
        "environment": m.environment,
        "time_of_day": m.time_of_day,
        "comic_panel_desc": m.comic_panel_desc,
        "score": m.composite_score,
        "tier": m.tier,
    }


def main():
    parser = argparse.ArgumentParser(description="Life Comic Generator")
    parser.add_argument("input", help="Image directory or file path")
    parser.add_argument("--panels", type=int, default=8, help="Number of comic panels (1-10)")
    parser.add_argument("--output", default="comic_output.html", help="Output HTML path")
    parser.add_argument("--date", default=None, help="Date string for footer")
    parser.add_argument("--output-dir", default=".", help="Directory for generated images")
    parser.add_argument("--save-analysis", default=None, help="Save analysis JSON")
    parser.add_argument("--skip-image-gen", action="store_true", help="Skip comic image generation")
    parser.add_argument("--theme", default=None, help="Theme/style keyword to guide generation")
    parser.add_argument("--style", default=None, help="Style keyword (alias for --theme)")
    parser.add_argument("--format", default="all", choices=["html", "richtext", "png", "all"],
                        help="Output format: html, richtext (markdown for chat), png, all (default)")
    args = parser.parse_args()

    user_theme = args.theme or args.style
    panel_count = min(max(args.panels, 1), 10)

    print("=" * 60)
    print("  LIFE COMIC GENERATOR v0.3")
    print("=" * 60)

    image_paths = collect_images(args.input)
    if not image_paths:
        print("No images found.")
        sys.exit(1)
    print(f"\n[1/5] Found {len(image_paths)} images")

    print(f"\n[2/5] Analyzing photos for comic moments via MCP...")

    cfg = {}
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    alt_path = os.path.expanduser("~/.claude/skills/life-comic/config.json")
    for p in [config_path, alt_path]:
        if os.path.exists(p):
            with open(p) as f:
                cfg = json.load(f)
            break

    mcp = create_mcp_client(cfg)
    mcp.connect()
    uploader = FileUploader(cfg)

    try:
        moments = analyze_photos(image_paths, mcp_client=mcp, uploader=uploader)
        print(f"  Analyzed {len(moments)} photos")

        effective_panels = min(panel_count, len(moments))
        print(f"\n[3/5] Selecting top {effective_panels} comic panels...")
        selected = select_comic_panels(moments, effective_panels)
        print(f"  Selected {len(selected)} panels:")
        for i, m in enumerate(selected):
            print(f"    #{i+1} [{m.tier}] {m.composite_score:.1f} — {m.scene_summary}")

        selected_dicts = [moment_to_dict(m) for m in selected]

        if args.save_analysis:
            all_dicts = [moment_to_dict(m) for m in moments]
            with open(args.save_analysis, "w", encoding="utf-8") as f:
                json.dump({"all": all_dicts, "selected": selected_dicts}, f, ensure_ascii=False, indent=2)
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

        print(f"\n[4/5] Generating storyboard and narrative...")
        storyboard = generate_storyboard(selected_dicts, date_str=date_str, user_theme=user_theme, lang=lang, target_panel_count=effective_panels, mcp_client=mcp)
        print(f"  Theme: {storyboard.get('theme', '?')}")
        print(f"  Title: {storyboard.get('narrative', {}).get('title', '?')}")
        print(f"  Panels: {len(storyboard.get('panels', []))}")
        actual_panels = len(storyboard.get("panels", []))
        if actual_panels < effective_panels:
            print(f"  [WARN] Storyboard returned {actual_panels} panels, expected {effective_panels}")

        suggested = storyboard.get("suggested_themes", [])
        if suggested:
            print(f"  Suggested themes: {', '.join(suggested)}")

        comic_image_path = None
        if not args.skip_image_gen:
            print(f"\n[5/5] Generating comic image via MCP imagen_generate...")
            os.makedirs(args.output_dir, exist_ok=True)
            ref_paths = [m.file_path for m in selected]
            comic_image_path = generate_comic_image(storyboard, ref_paths, args.output_dir, mcp_client=mcp, uploader=uploader)
            if comic_image_path:
                print(f"  Comic image: {comic_image_path}")
            else:
                print(f"  [WARN] Comic image generation failed, using photo fallback")
        else:
            print(f"\n[5/5] Skipping comic image generation (--skip-image-gen)")

        ref_paths = [m.file_path for m in selected]
        output_base = os.path.splitext(args.output)[0]

        generated_files = {}
        html_output = None

        if args.format in ("html", "all"):
            html_output = render_comic_html(storyboard, comic_image_path, ref_paths, args.output)
            generated_files["html"] = html_output
            print(f"\n  [HTML] {html_output}")

        if args.format in ("richtext", "all"):
            from richtext_renderer import render_comic_richtext
            rt_path = output_base + "_richtext.md"
            render_comic_richtext(storyboard, comic_image_path, ref_paths, rt_path)
            generated_files["richtext"] = rt_path
            print(f"  [Rich Text] {rt_path}")

        if args.format in ("png", "all"):
            from png_renderer import render_comic_png
            png_path = output_base + ".png"
            if not html_output:
                html_output = render_comic_html(storyboard, comic_image_path, ref_paths, output_base + "_tmp.html")
            result = render_comic_png(storyboard, comic_image_path, ref_paths, png_path, html_path=html_output)
            if result:
                generated_files["png"] = png_path
                print(f"  [PNG] {png_path}")

        print(f"\n{'=' * 60}")
        print(f"  Comic generated (v0.3)")
        for fmt, path in generated_files.items():
            print(f"  [{fmt.upper()}] {path}")
        if comic_image_path:
            print(f"\n  >>> COMIC IMAGE: {comic_image_path}")
        if "png" in generated_files:
            print(f"  >>> COMPOSITE IMAGE (shareable): {generated_files['png']}")
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
        if comic_image_path:
            print(f"  Upload {comic_image_path}")
            print(f'  Link text: "\U0001f3a8 [Comic art](<url>)"')
        print(f"  Do NOT embed images inline with ![...]. Provide download links only.")
    finally:
        mcp.close()
        uploader.close()


if __name__ == "__main__":
    main()
