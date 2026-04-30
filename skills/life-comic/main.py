#!/usr/bin/env python3
"""Life Comic Generator — main entry point.

Usage:
    python3 main.py <image_dir_or_files> [--panels 8] [--output comic.html] [--date 2026-04-13]
        [--theme "food journey"] [--format html]

    Sandbox mode (pre-analyzed data from Claude Code):
    python3 main.py <image_dir> --pre-analyzed analysis.json --storyboard storyboard.json
        [--comic-images-dir ./comic_imgs] [--output comic.html] [--format all]

Workflow:
    1. Batch analyze photos via MCP image_understand (or load from --pre-analyzed)
    2. Select top moments with narrative diversity
    3. Generate storyboard script and emotional narrative via MCP (or load from --storyboard)
    4. Generate multi-panel comic image via MCP imagen_generate (or use --comic-images-dir)
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
    parser.add_argument("--pre-analyzed", default=None,
                        help="Pre-analyzed JSON file (skip MCP image analysis)")
    parser.add_argument("--storyboard", default=None,
                        help="Pre-generated storyboard JSON (skip MCP storyboard generation)")
    parser.add_argument("--comic-images-dir", default=None,
                        help="Directory with pre-generated comic images (skip MCP image generation)")
    parser.add_argument("--export-prompts", action="store_true",
                        help="Export prompt templates as JSON and exit (for sandbox mode)")
    parser.add_argument("--build-comic-prompt", default=None,
                        help="Build imagen prompt from storyboard JSON and exit (for sandbox mode)")
    args = parser.parse_args()

    if args.build_comic_prompt:
        from comic_generator import COMIC_IMAGE_PROMPT_TEMPLATE
        with open(args.build_comic_prompt, encoding="utf-8") as f:
            sb = json.load(f)
        panels = sb.get("panels", [])
        panel_descs = ""
        for i, p in enumerate(panels):
            desc = p.get("scene_description", "")
            emotion_tag = p.get("emotion_tag", "")
            composition = p.get("panel_composition", "")
            panel_descs += f"\nPanel {i+1} ({emotion_tag}): {desc} Composition: {composition}."
        prompt = COMIC_IMAGE_PROMPT_TEMPLATE.format(
            panel_count=len(panels),
            theme=sb.get("theme", "Life Comic"),
            emotional_arc=sb.get("emotional_arc", ""),
            panel_descriptions=panel_descs,
        )
        print(prompt)
        sys.exit(0)

    if args.export_prompts:
        from image_analyzer import COMIC_ANALYSIS_PROMPT
        from comic_generator import STORYBOARD_PROMPT, COMIC_IMAGE_PROMPT_TEMPLATE
        prompts = {
            "analysis_prompt": COMIC_ANALYSIS_PROMPT,
            "storyboard_prompt_template": STORYBOARD_PROMPT,
            "storyboard_variables": ["panels_json", "theme_instruction",
                                      "lang_instruction", "panel_count"],
            "comic_image_prompt_template": COMIC_IMAGE_PROMPT_TEMPLATE,
            "comic_image_prompt_variables": ["panel_count", "theme",
                                              "emotional_arc", "panel_descriptions"],
            "scoring_weights": {"comic_potential": 0.35, "visual_distinctness": 0.30,
                               "narrative_weight": 0.35},
            "tier_thresholds": {"star_moment": 7.5, "good_moment": 6.0, "average": 4.0}
        }
        print(json.dumps(prompts, ensure_ascii=False, indent=2))
        sys.exit(0)

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

    skip_image_gen = args.skip_image_gen or args.comic_images_dir is not None
    needs_mcp = not args.pre_analyzed or not args.storyboard or (not skip_image_gen and not args.comic_images_dir)

    cfg = {}
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    alt_path = os.path.expanduser("~/.claude/skills/life-comic/config.json")
    for p in [config_path, alt_path]:
        if os.path.exists(p):
            with open(p) as f:
                cfg = json.load(f)
            break

    mcp = None
    uploader = None
    if needs_mcp:
        mcp = create_mcp_client(cfg)
        mcp.connect()
        uploader = FileUploader(cfg)

    try:
        if args.pre_analyzed:
            print(f"\n[2/5] Loading pre-analyzed data from {args.pre_analyzed}...")
            with open(args.pre_analyzed, encoding="utf-8") as f:
                pre_data = json.load(f)
            all_moments = pre_data.get("all", pre_data.get("selected", []))
            selected_dicts = pre_data.get("selected", all_moments)
            ref_paths = [m["file"] for m in selected_dicts]
            print(f"  Loaded {len(all_moments)} analyses, {len(selected_dicts)} selected")
        else:
            print(f"\n[2/5] Analyzing photos for comic moments via MCP...")
            moments = analyze_photos(image_paths, mcp_client=mcp, uploader=uploader)
            print(f"  Analyzed {len(moments)} photos")

            effective_panels = min(panel_count, len(moments))
            print(f"\n[3/5] Selecting top {effective_panels} comic panels...")
            selected = select_comic_panels(moments, effective_panels)
            print(f"  Selected {len(selected)} panels:")
            for i, m in enumerate(selected):
                print(f"    #{i+1} [{m.tier}] {m.composite_score:.1f} — {m.scene_summary}")

            selected_dicts = [moment_to_dict(m) for m in selected]
            ref_paths = [m.file_path for m in selected]

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

        if args.storyboard:
            print(f"\n[4/5] Loading storyboard from {args.storyboard}...")
            with open(args.storyboard, encoding="utf-8") as f:
                storyboard = json.load(f)
            print(f"  Title: {storyboard.get('narrative', {}).get('title', '?')}")
        else:
            effective_panels = len(selected_dicts)
            print(f"\n[4/5] Generating storyboard and narrative...")
            storyboard = generate_storyboard(selected_dicts, date_str=date_str, user_theme=user_theme, lang=lang, target_panel_count=effective_panels, mcp_client=mcp, uploader=uploader, panel_photo_paths=ref_paths)
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
        if args.comic_images_dir:
            imgs = sorted([
                os.path.join(args.comic_images_dir, f)
                for f in os.listdir(args.comic_images_dir)
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS
            ])
            if imgs:
                comic_image_path = imgs[0]
                print(f"\n[5/5] Using pre-generated comic image: {comic_image_path}")
            else:
                print(f"\n[5/5] No comic images found in {args.comic_images_dir}")
        elif not skip_image_gen:
            print(f"\n[5/5] Generating comic image via MCP imagen_generate...")
            os.makedirs(args.output_dir, exist_ok=True)
            comic_image_path = generate_comic_image(storyboard, ref_paths, args.output_dir, mcp_client=mcp, uploader=uploader)
            if comic_image_path:
                print(f"  Comic image: {comic_image_path}")
            else:
                print(f"  [WARN] Comic image generation failed, using photo fallback")
        else:
            print(f"\n[5/5] Skipping comic image generation (--skip-image-gen)")

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
        if mcp:
            mcp.close()
        if uploader:
            uploader.close()


if __name__ == "__main__":
    main()
