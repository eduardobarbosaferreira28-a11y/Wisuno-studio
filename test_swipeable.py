"""
Test: swipeable HTML carousel for the CPI 3.8% article.

Skips Claude script generation — script is hardcoded here.
Generates a Gemini cover background image, then writes carousel.html.

USAGE:
    python test_swipeable.py              # full run (Gemini image)
    python test_swipeable.py --no-images  # skip Gemini, plain dark bg
"""
import argparse
import json
import sys
import time
from pathlib import Path

# ── Hardcoded CPI carousel script ────────────────────────────────────────────
SCRIPT = {
    "title": "The Inflation Monster Returns: CPI Hits 3.8%",
    "caption": (
        "April CPI just came in at 3.8% — hotter than expected and the "
        "highest reading in nearly three years. Energy drove 40% of the "
        "increase, but core inflation is spreading. Rate cuts for 2026? "
        "Practically dead. Follow @wisuno for daily macro breakdowns."
    ),
    "hashtags": [
        "inflation", "CPI", "FederalReserve", "interestrates",
        "macroeconomics", "trading", "forex", "CFD", "wisuno"
    ],
    "slides": [
        {
            "slide_number": 1,
            "type": "cover",
            "headline": "THE INFLATION MONSTER RETURNS",
            "subheadline": "April CPI hits 3.8% — the hottest reading in nearly three years.",
            "asset_tag": "US CPI",
            "background_image_description": (
                "Dramatic dark cinematic close-up of a crumbling US dollar bill "
                "surrounded by rising flames and embers against a pitch black background, "
                "economic crisis mood, moody editorial photography"
            ),
        },
        {
            "slide_number": 2,
            "type": "data_slide",
            "asset_tag": "US CPI",
            "section_headline": "By The Numbers",
            "data_points": [
                {"label": "April CPI (Year-over-Year)", "value": "3.8%",   "direction": "UP"},
                {"label": "Energy share of CPI increase", "value": "40%",  "direction": "UP"},
                {"label": "Gasoline (YoY)",               "value": "+28.4%","direction": "UP"},
                {"label": "Airfares (YoY)",                "value": "+21%", "direction": "UP"},
                {"label": "Core CPI (ex-food & energy)",   "value": "2.8%", "direction": "UP"},
                {"label": "Fed rate cut probability (2026)","value": "~2%",  "direction": "DOWN"},
            ],
            "takeaway_line": (
                "Energy is the primary engine — but with core at 2.8%, "
                "the heat is spreading well beyond the pump."
            ),
        },
        {
            "slide_number": 3,
            "type": "analysis_slide",
            "asset_tag": "MARKET ANALYSIS",
            "analysis_paragraphs": [
                (
                    "Energy accounted for a massive 40% of the total CPI increase. "
                    "The ongoing Iran conflict has heavily constrained global oil supplies, "
                    "pushing gasoline prices up 28.4% year-over-year — and airfares nearly 21% "
                    "as jet fuel costs skyrocket."
                ),
                (
                    "The Fed typically 'looks through' energy shocks. But Core CPI still ticked "
                    "up to 2.8%, signaling that input cost pressure is flowing through the "
                    "entire supply chain."
                ),
                (
                    "From grocery aisles — beef and tomatoes surging — to shelter costs, "
                    "the inflationary story is no longer just about energy."
                ),
            ],
        },
        {
            "slide_number": 4,
            "type": "analysis_slide",
            "asset_tag": "FED WATCH",
            "analysis_paragraphs": [
                (
                    "Rate cuts for 2026 are practically dead. Markets are now pricing a 98% "
                    "probability that the Fed holds rates steady through most of the year."
                ),
                (
                    "Even more striking: traders are pricing in a 30% chance of an actual "
                    "rate hike by December — a dramatic repricing of the entire policy path "
                    "that would have been unthinkable just weeks ago."
                ),
            ],
        },
        {
            "slide_number": 5,
            "type": "quote_slide",
            "asset_tag": "FED CHAIR",
            "quote_text": (
                "Incoming Fed Chair Kevin Warsh is walking into a hawkish nightmare. "
                "The era of compounding supply shocks is creating a deeply entrenched "
                "inflationary mindset."
            ),
            "quote_attribution": "Wisuno Market Desk",
            "rhetorical_question": (
                "Can a new Fed Chair navigate pandemic → Ukraine → tariffs → Iran "
                "without breaking the economy?"
            ),
        },
        {
            "slide_number": 6,
            "type": "cta_slide",
        },
    ],
}

# ── Output setup ──────────────────────────────────────────────────────────────
_BASE_DIR  = Path(__file__).parent
_OUT_DIR   = _BASE_DIR / "output" / "cpi-38-inflation-test"
_IMGS_DIR  = _OUT_DIR / "images"


def run(generate_images: bool = True) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _IMGS_DIR.mkdir(parents=True, exist_ok=True)

    # Save script for reference
    (_OUT_DIR / "script.json").write_text(
        json.dumps(SCRIPT, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── Step 1: Generate Gemini images ────────────────────────────────────
    slide_images: dict[int, str] = {}

    if generate_images:
        print("\n[1/2] Generating Gemini images…")
        from image_generator import bytes_to_data_uri, generate_background_image

        for slide in SCRIPT["slides"]:
            stype = slide.get("type", "")
            snum  = slide.get("slide_number", 0)

            if stype == "cover" and slide.get("background_image_description"):
                img_path = _IMGS_DIR / "cover_bg.jpg"
                if img_path.exists():
                    print(f"  -> Cover background: reusing cached {img_path.name}")
                    img_bytes = img_path.read_bytes()
                    slide_images[snum] = bytes_to_data_uri(img_bytes)
                else:
                    desc = slide["background_image_description"]
                    print(f"  -> Cover background: {desc[:70]}...")
                    try:
                        img_bytes = generate_background_image(desc, img_path)
                        slide_images[snum] = bytes_to_data_uri(img_bytes)
                        print(f"    OK Saved to {img_path.name} ({len(img_bytes)//1024} KB)")
                    except Exception as exc:
                        print(f"    WARNING Image generation failed: {exc}")
                        print("      Proceeding with plain dark background.")
                    time.sleep(1)
    else:
        print("\n[1/2] Skipping Gemini image generation (--no-images).")

    # ── Step 2: Build swipeable HTML ─────────────────────────────────────
    print("\n[2/2] Building swipeable carousel HTML…")
    from swipeable_carousel import build_swipeable_html

    html     = build_swipeable_html(SCRIPT, slide_images)
    out_path = _OUT_DIR / "carousel.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Done!")
    print(f"  Slides  : {len(SCRIPT['slides'])}")
    print(f"  Output  : {out_path}")
    if slide_images:
        print(f"  Images  : {len(slide_images)} Gemini image(s) embedded as data URIs")
    print(f"{'='*60}")
    print(f"\n  Open in browser:")
    print(f"  file:///{out_path.as_posix()}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CPI carousel test")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip Gemini image generation (faster, no API call).",
    )
    args = parser.parse_args()

    try:
        run(generate_images=not args.no_images)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
