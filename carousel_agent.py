"""
Wisuno Instagram Carousel Agent
================================
Main orchestrator — runs the full pipeline from article to Canva design spec.

USAGE
-----
  python carousel_agent.py "https://finance-news-url.com/article"
  python carousel_agent.py --text "Paste article text here..."
  python carousel_agent.py                          # interactive prompt

PIPELINE
--------
  1. Extract article content (URL fetch or raw text)
  2. Generate carousel script via Claude API
  3. Source a market-reaction meme via Tenor / Reddit
  4. Build Canva design spec + generate design prompt
  5. Print Claude Code instructions to execute Canva MCP tools
  6. (After Canva export) Download slides & write caption file

The Canva design steps (4b onward) require Claude Code's Canva MCP tools.
After step 4, this script prints everything Claude Code needs to complete
the design in one shot.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import OUTPUT_DIR
from content_extractor import extract_from_url, extract_from_text
from script_generator import generate_script
from canva_builder import build_design_spec, generate_canva_prompt
from exporter import write_caption_file


def _slug(title: str) -> str:
    """Convert a title to a safe folder name."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]


def run(article_input: str, is_url: bool) -> None:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  WISUNO CAROUSEL AGENT")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # ── Step 1: Extract article ───────────────────────────────────────────────
    print("▶ Step 1/4 — Extracting article content…")
    if is_url:
        print(f"  URL: {article_input}")
        article_text = extract_from_url(article_input)
    else:
        article_text = extract_from_text(article_input)
    print(f"  Extracted {len(article_text):,} characters\n")

    # ── Step 2: Generate script ───────────────────────────────────────────────
    print("▶ Step 2/4 — Generating carousel script with Claude…")
    script = generate_script(article_text)
    slug = _slug(script["title"])
    output_dir = OUTPUT_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    script_path = output_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Title:  {script['title']}")
    print(f"  Asset:  {script['asset_tag']}")
    print(f"  Slides: {len(script['slides'])}")
    print(f"  Saved:  {script_path}\n")

    # ── Step 3: Build Canva design spec ──────────────────────────────────────
    print("▶ Step 3/3 — Building Canva design spec…")
    design_spec = build_design_spec(script)
    canva_prompt = generate_canva_prompt(design_spec)

    spec_path = output_dir / "canva_spec.json"
    spec_path.write_text(design_spec.to_json(), encoding="utf-8")
    print(f"  Spec saved: {spec_path}\n")

    # ── Write caption ─────────────────────────────────────────────────────────
    write_caption_file(script, output_dir)

    # ── Print Canva instructions for Claude Code ──────────────────────────────
    _print_canva_instructions(canva_prompt, output_dir)


def _print_canva_instructions(
    canva_prompt: str,
    output_dir: Path,
) -> None:
    sep = "═" * 60

    print(sep)
    print("  CANVA DESIGN — CLAUDE CODE INSTRUCTIONS")
    print(sep)
    print("""
The script has been prepared. Now Claude Code needs to execute
the following Canva MCP tool calls to build the design.

If you are running this inside a Claude Code session, copy the
prompt below and send it to Claude Code to complete the design.
""")
    print("── CANVA PROMPT (copy everything between the markers) ──────")
    print(">>>BEGIN<<<")
    print()
    print(f"""Please build a Wisuno Instagram carousel in Canva using these steps:

1. Call `list-brand-kits` to find the Wisuno brand kit ID.

2. Call `generate-design-structured` with this design description:

{canva_prompt}

3. For the cover slide background:
   - Source a dark financial photo matching the `background_image_description` from the script.
   - Upload via `upload-asset-from-url` and set as the full-bleed background of slide 1 with a 60–80% dark overlay.

4. For the logos:
   - Upload `Wisuno Logo/White-Colored.png` via `upload-asset-from-url`.
   - Place it top-left on every slide as specified in the design prompt.

5. Call `commit-editing-transaction` to finalize.

6. Call `export-design` with format PNG to get download URLs for all pages.

7. Return the Canva design URL and the list of exported page image URLs.

Output folder for this carousel: {output_dir}
Script JSON: {output_dir / 'script.json'}
""")
    print(">>>END<<<")
    print()
    print(sep)
    print()
    print("After Claude Code completes the Canva design and returns the")
    print("exported page URLs, run:")
    print()
    print(f"  python download_slides.py '{output_dir}' URL1 URL2 URL3 ...")
    print()
    print("Or call exporter.download_slides(page_urls, output_dir) directly.")
    print()
    print(f"Caption file already written: {output_dir / 'caption.txt'}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Wisuno Instagram Carousel Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Article URL or (with --text) raw article text",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Treat input as raw text instead of a URL",
    )
    args = parser.parse_args()

    if args.input:
        article_input = args.input
        is_url = not args.text
    else:
        print("Paste article URL or text (press Enter twice when done):\n")
        lines = []
        try:
            while True:
                line = input()
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
        except EOFError:
            pass
        article_input = "\n".join(lines).strip()
        is_url = article_input.startswith("http://") or article_input.startswith("https://")

    if not article_input:
        print("Error: No article input provided.")
        sys.exit(1)

    run(article_input, is_url)


if __name__ == "__main__":
    main()
