"""
Wisuno HTML Carousel Generator.

Given a news article URL or raw text, this script:
  1. Extracts article text              content_extractor.py
  2. Calls Claude API -> script.json    prompts/script_prompt.txt
  3. Calls Gemini Imagen -> bg images   image_generator.py
  4. Translates script into 3 languages via Claude
  5. Renders 4 swipeable carousels     swipeable_carousel.py
     carousel_en.html / carousel_zh-TW.html / carousel_zh-CN.html / carousel_th.html

USAGE:
  python html_carousel.py --url https://...  [--slides 6] [--no-images]
  python html_carousel.py --text "raw text"  [--slides 6] [--no-images]
  python html_carousel.py --script output/some-folder/script.json [--no-images]

OUTPUT:
  output/<slugified-title>/
    script.json               (English source)
    script_zh-TW.json
    script_zh-CN.json
    script_th.json
    caption_en.txt
    caption_zh-TW.txt
    caption_zh-CN.txt
    caption_th.txt
    images/cover_bg.jpg
    carousel_en.html
    carousel_zh-TW.html
    carousel_zh-CN.html
    carousel_th.html
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

# Ensure stdout/stderr can handle Unicode on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DEFAULT_SLIDES,
    DISCLAIMER,
    MAX_SLIDES,
    MIN_SLIDES,
    OUTPUT_DIR,
    PROMPTS_DIR,
)
from content_extractor import extract_from_text, extract_from_url
from image_generator import (
    bytes_to_data_uri,
    generate_background_image,
    generate_chart_image,
)
from swipeable_carousel import build_swipeable_html


# ── Language config ───────────────────────────────────────────────────────────

LANGUAGES: dict[str, str] = {
    "en":    "English",
    "zh-TW": "Traditional Chinese (繁體中文)",
    "zh-CN": "Simplified Chinese (简体中文)",
    "th":    "Thai (ภาษาไทย)",
    "sw":    "Kiswahili",
    "pt-BR": "Brazilian Portuguese (Português do Brasil)",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int = 48) -> str:
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:max_len]


def _load_prompt(num_slides: int, content_type: str = "market_insight") -> str:
    if content_type == "educational":
        fname = "educational_prompt.txt"
    elif content_type == "promotional":
        fname = "promotional_prompt.txt"
    else:
        fname = "script_prompt.txt"
    template = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
    return template.replace("{min_slides}", str(MIN_SLIDES)) \
                   .replace("{max_slides}", str(MAX_SLIDES)) \
                   .replace("{default_slides}", str(num_slides)) \
                   .replace("{disclaimer}", DISCLAIMER)


def _save_caption(script: dict, path: Path) -> None:
    caption  = script.get("caption", "")
    hashtags = script.get("hashtags", [])
    text     = caption
    if hashtags:
        text += "\n\n" + " ".join(f"#{h}" for h in hashtags)
    path.write_text(text, encoding="utf-8")


# ── Step 2: Generate English script via Claude ───────────────────────────────

def generate_script(article_text: str, num_slides: int = DEFAULT_SLIDES,
                    content_type: str = "market_insight") -> dict:
    print("\n[2/5] Generating carousel script via Claude...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _load_prompt(num_slides, content_type) + f"\n\nARTICLE:\n{article_text}"

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        script = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    script.setdefault("content_type", content_type)
    print(f"     -> {len(script.get('slides', []))} slides: {script.get('title', '?')}")
    return script


# ── Step 3: Generate images via Gemini ───────────────────────────────────────

def generate_slide_images(
    script: dict, images_dir: Path, use_higgsfield: bool = False
) -> dict[int, str]:
    """Return slide_number -> data URI for slides that need images."""
    if use_higgsfield:
        from higgsfield_generator import generate_background_image as _gen_bg
        print("\n[3/5] Generating images via Higgsfield Seedream v4...")
    else:
        _gen_bg = generate_background_image
        print("\n[3/5] Generating images via Gemini Imagen...")
    slide_images: dict[int, str] = {}

    for slide in script.get("slides", []):
        stype = slide.get("type", "")
        snum  = slide.get("slide_number", 0)

        if slide.get("background_image_description"):
            desc     = slide["background_image_description"]
            img_name = "cover_bg.jpg" if stype == "cover" else f"slide_{snum}_bg.jpg"
            img_path = images_dir / img_name
            label    = "Cover bg" if stype == "cover" else f"Slide {snum} bg"
            if img_path.exists():
                print(f"     -> {label}: reusing cached {img_path.name}")
                slide_images[snum] = bytes_to_data_uri(img_path.read_bytes())
            else:
                print(f"     -> {label}: {desc[:60]}...")
                try:
                    img_bytes = _gen_bg(desc, img_path)
                    slide_images[snum] = bytes_to_data_uri(img_bytes)
                    print(f"        OK ({len(img_bytes)//1024} KB)")
                except Exception as exc:
                    print(f"        WARNING: {exc} -- using plain dark background.")
                time.sleep(1)

        elif stype == "chart_slide":
            chart_asset = slide.get("chart_asset", "price action")
            chart_type  = slide.get("chart_type", "line_chart")
            img_path    = images_dir / f"chart_{snum}.jpg"
            if img_path.exists():
                print(f"     -> Chart {snum}: reusing cached {img_path.name}")
                slide_images[snum] = bytes_to_data_uri(img_path.read_bytes())
            else:
                print(f"     -> Chart: {chart_asset}")
                try:
                    img_bytes = generate_chart_image(chart_asset, chart_type, img_path)
                    slide_images[snum] = bytes_to_data_uri(img_bytes)
                except Exception as exc:
                    print(f"        WARNING: {exc} -- using SVG fallback.")
                time.sleep(1)

    return slide_images


# ── Step 4: Translate script via Claude ──────────────────────────────────────

_TRANSLATE_PROMPT = """\
Translate the following Instagram financial carousel script from English to {lang_name}.

TRANSLATION RULES:
- Translate EVERY human-readable text value in the JSON into {lang_name} — every headline, label,
  sentence, paragraph, quote, term, definition, list item, table cell, caption, and eyebrow. Do not
  leave any visible text in English. This includes (non-exhaustively): title, caption, headline,
  subheadline, section_headline, takeaway_line, analysis_paragraphs[], quote_text, quote_attribution,
  rhetorical_question, chart_caption, data_points[].label, data_points[].value, asset_tag, term,
  definition, why_it_matters, steps[], col_a_label, col_b_label, rows[].col_a, rows[].col_b, scenario,
  number_label, narrative, outcome, pillars[].title, pillars[].detail, feature_name, feature_detail,
  benefits[], and any other text field present.
- For values that mix numbers with words (e.g. data_points[].value, rows[] cells, featured_number),
  KEEP the numerals, currency symbols, percentages, and ticker symbols exactly as-is, but TRANSLATE
  any surrounding words/phrases into {lang_name}. Examples:
    "Near 2 month high" → translate the words (the "2 month high" phrasing), keep the digit "2".
    "~$4,310/oz" → keep "~$4,310", translate the unit "/oz" (e.g. "/onça" in pt-BR) if it has a
    natural local form; otherwise keep it. "10:1" or "$1,000" with no words → keep byte-for-byte.
  Never leave an English word like "Near", "high", "low", "above", "below", "per" untranslated.
- Keep these keys UNCHANGED (return their values byte-for-byte, do NOT translate):
    slide_number, type, direction, background_image_description, chart_type, chart_asset, content_type.
- For hashtags: translate the meaning of each hashtag into the target language, keeping them as single lowercase words with no spaces (e.g. "inflation" → "通货膨胀" or "เงินเฟ้อ"). Always keep "wisuno" unchanged.
- Keep financial abbreviations in English: CPI, Fed, GDP, USD, EUR, CFD, YoY, etc. Keep "wisuno" / "@wisuno" unchanged.
- Maintain a professional financial tone.
- EXTREMELY IMPORTANT: Return ONLY valid JSON with the exact same structure and keys. No markdown, no conversational text. You MUST properly escape any double quotes inside your translated text strings as \\".

SCRIPT:
{script_json}"""


def translate_script(script: dict, lang_code: str, retries: int = 2) -> dict:
    lang_name = LANGUAGES[lang_code]
    print(f"\n     Translating to {lang_name}...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    prompt = _TRANSLATE_PROMPT.format(
        lang_name=lang_name,
        script_json=json.dumps(script, ensure_ascii=False, indent=2),
    )

    messages = [{"role": "user", "content": prompt}]
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"        Retry {attempt}/{retries} (invalid JSON from Claude)...")
            time.sleep(2)
            messages.append({
                "role": "user", 
                "content": f"The JSON you returned was invalid. Error: {last_exc}\nPlease fix the syntax errors (such as unescaped double quotes inside strings or trailing commas) and return ONLY the raw corrected JSON."
            })
            
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=messages,
        )
        raw = message.content[0].text.strip()
        messages.append({"role": "assistant", "content": raw})
        
        # Robustly extract JSON block if wrapped in markdown
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()
        else:
            # Fallback: find first { and last }
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1:
                raw = raw[start:end+1]

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            last_exc = exc

    raise ValueError(
        f"Claude translation ({lang_code}) returned invalid JSON after {retries + 1} attempts: {last_exc}"
    ) from last_exc


# ── Step 5: Build all 4 language carousels ────────────────────────────────────

def build_all_carousels(
    scripts: dict[str, dict],
    slide_images: dict[int, str],
    output_dir: Path,
) -> None:
    print("\n[5/5] Building swipeable carousel HTML (4 languages)...")
    for lang_code, script in scripts.items():
        html      = build_swipeable_html(script, slide_images, language=lang_code)
        filename  = f"carousel_{lang_code}.html"
        out_path  = output_dir / filename
        out_path.write_text(html, encoding="utf-8")
        print(f"     -> {filename}  ({len(html)//1024} KB)  [{LANGUAGES[lang_code]}]")


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(
    url: str | None = None,
    text: str | None = None,
    script_path: Path | None = None,
    num_slides: int = DEFAULT_SLIDES,
    skip_images: bool = False,
    content_type: str = "market_insight",
    use_higgsfield: bool = False,
) -> Path:
    """Full pipeline. Returns the output directory path."""

    # ── Step 1: Extract article ───────────────────────────────────────────────
    if script_path:
        print(f"\n[1/5] Loading existing script: {script_path}")
        en_script = json.loads(script_path.read_text(encoding="utf-8"))
        print(f"     -> {len(en_script.get('slides', []))} slides loaded from disk.")
    elif url:
        print(f"\n[1/5] Fetching article: {url}")
        article_text = extract_from_url(url)
        print(f"     -> {len(article_text)} characters extracted.")
        en_script = None
    elif text:
        print("\n[1/5] Using provided article text.")
        article_text = extract_from_text(text)
        en_script = None
    else:
        raise ValueError("Provide --url, --text, or --script.")

    # ── Step 2: Generate English script ──────────────────────────────────────
    if en_script is None:
        en_script = generate_script(article_text, num_slides, content_type=content_type)

    # ── Set up output directory ───────────────────────────────────────────────
    slug       = _slugify(en_script.get("title", "carousel"))
    output_dir = OUTPUT_DIR / slug
    images_dir = output_dir / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "script.json").write_text(
        json.dumps(en_script, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _save_caption(en_script, output_dir / "caption_en.txt")
    print(f"\n     Output folder: {output_dir}")

    # ── Step 3: Gemini images ─────────────────────────────────────────────────
    if skip_images:
        print("\n[3/5] Skipping image generation (--no-images).")
        slide_images: dict[int, str] = {}
    else:
        images_dir.mkdir(parents=True, exist_ok=True)
        slide_images = generate_slide_images(en_script, images_dir, use_higgsfield=use_higgsfield)

    # ── Step 4: Translate to zh-TW, zh-CN, th ────────────────────────────────
    print("\n[4/5] Translating script into 3 languages...")
    scripts: dict[str, dict] = {"en": en_script}

    for lang_code in ("zh-TW", "zh-CN", "th"):
        translated = translate_script(en_script, lang_code)
        scripts[lang_code] = translated
        (output_dir / f"script_{lang_code}.json").write_text(
            json.dumps(translated, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _save_caption(translated, output_dir / f"caption_{lang_code}.txt")

    # ── Step 5: Build 4 carousels ─────────────────────────────────────────────
    build_all_carousels(scripts, slide_images, output_dir)

    return output_dir


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wisuno HTML Carousel Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url",    help="News article URL to fetch and process.")
    src.add_argument("--text",   help="Raw article text (paste directly).")
    src.add_argument("--script", type=Path,
                     help="Path to an existing script.json to skip Claude generation.")
    parser.add_argument(
        "--slides",
        type=int, default=DEFAULT_SLIDES, metavar="N",
        help=f"Target slide count (default: {DEFAULT_SLIDES}, range {MIN_SLIDES}-{MAX_SLIDES}).",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip Gemini image generation (plain dark backgrounds).",
    )
    parser.add_argument(
        "--type",
        choices=["market_insight", "market_update", "educational"],
        default="market_insight",
        dest="content_type",
        help="Carousel content type (default: market_insight).",
    )
    parser.add_argument(
        "--higgsfield",
        action="store_true",
        help="Use Higgsfield Seedream v4 instead of Gemini Imagen for cover background.",
    )
    args   = parser.parse_args()
    slides = max(MIN_SLIDES, min(MAX_SLIDES, args.slides))

    try:
        out_dir = run(
            url=args.url,
            text=args.text,
            script_path=args.script,
            num_slides=slides,
            skip_images=args.no_images,
            content_type=args.content_type,
            use_higgsfield=args.higgsfield,
        )
        print(f"\n{'='*60}")
        print(f"  Carousels ready!")
        print(f"  Output : {out_dir}")
        for lang_code, lang_name in LANGUAGES.items():
            f = out_dir / f"carousel_{lang_code}.html"
            print(f"  [{lang_code:5s}] file:///{f.as_posix()}")
        print(f"{'='*60}\n")
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
