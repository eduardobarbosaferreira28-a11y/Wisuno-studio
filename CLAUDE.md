# Wisuno Carousel Automation — Claude Code Instructions

## Project Overview
This project automates Instagram carousel creation for Wisuno (multi-regulated CFD broker). Given a news article URL or raw text, the workflow produces a self-contained swipeable HTML carousel and an Instagram caption file. **Canva MCP is no longer used.**

## Design Template (Ground Truth)

**`output/cpi-38-inflation-test/carousel.html`** is the canonical visual reference for all carousel designs. Every new carousel must match this design exactly.

The implementation of this design lives in **`swipeable_carousel.py`** — that file is the template. Only the content (text, data, images) changes per carousel topic; the layout, typography, spacing, colors, and interactive behavior are fixed.

If there is ever a visual discrepancy between a newly generated carousel and the CPI template, treat the CPI template as the source of truth and fix `swipeable_carousel.py`.

## Main Entry Point

```
python html_carousel.py --url https://...          # full run with Gemini image
python html_carousel.py --url https://... --no-images  # skip Gemini, plain dark bg
python html_carousel.py --script output/foo/script.json  # re-render from saved script
```

Output goes to `output/<slugified-title>/`.

---

## Workflow Steps

1. **Extract article** — `content_extractor.py` (`extract_from_url` or `extract_from_text`)
2. **Generate script** — Claude API with `prompts/script_prompt.txt`, substituting config values from `config.py` (MIN_SLIDES, MAX_SLIDES, DEFAULT_SLIDES, DISCLAIMER)
3. **Generate images** — Gemini Imagen 4 via `image_generator.py` (cover bg + chart slides); cached to `images/` to avoid repeat API calls
4. **Build carousel** — `swipeable_carousel.build_swipeable_html(script, slide_images)` → single self-contained `carousel.html`

---

## Key Files

| File | Role |
|---|---|
| `html_carousel.py` | Main pipeline orchestrator (CLI entry point) |
| `swipeable_carousel.py` | HTML carousel renderer + CLI for re-rendering from script.json |
| `test_swipeable.py` | Test runner with hardcoded CPI script (no Claude API call) |
| `image_generator.py` | Gemini Imagen 4 wrapper for cover + chart images |
| `content_extractor.py` | Article text extraction from URL or raw text |
| `config.py` | API keys, brand config, slide count limits, DISCLAIMER |
| `prompts/script_prompt.txt` | Claude prompt template for script generation |

---

## Brand Tokens

| Token | Value |
|---|---|
| Canvas | 1080 × 1350 px (4:5 portrait) |
| Background | `#0A0A0A` (near-black) on all slides |
| Heading font | Urbanist Bold (900 weight) — Google Fonts |
| Body font | General Sans (brand canonical) — Inter (300/400/500/600) is the Google Fonts web substitute actually loaded in rendered carousels |
| Accent / Orange | `#FF6700` |
| Primary text | `#FFFFFF` |
| Secondary text | `#CCCCCC` |
| Disclaimer text | `#888888` |
| Down / Red | `#EF4444` |
| Safe zone | 180 px all four sides |

**Exact spacing (all locked to the CPI template):**

| Element | Position |
|---|---|
| Logo | `top: 180px; right: 180px;` height 30px |
| Asset tag | `top: 180px; left: 180px;` |
| Disclaimer | `bottom: 180px; left: 180px; right: 180px;` 9px Inter |
| Content area | `top: 260px; left: 180px; right: 180px; bottom: 240px;` |
| Analysis bar | `left: 180px; width: 4px;` orange gradient |
| Analysis text | `left: 212px;` (180 + 4px bar + 28px gap) |
| Orange accent line | `width: 56px; height: 3px;` |
| Top bar (data/cta) | `height: 5px; background: #FF6700;` |

Logo: `Wisuno Logo/White-Colored.png` — embedded as base64 data URI in every slide.

---

## Slide Types

| Type | Role |
|---|---|
| `cover` | Hook — full-bleed Gemini photo + gradient overlay, large ALL CAPS headline |
| `data_slide` | Key numbers — stat list with labels, values, UP/DOWN/FLAT arrows |
| `analysis_slide` | Market mechanics — 2–3 short paragraphs explaining "why it matters" |
| `quote_slide` | Human voice — sourced quote or editorial, centered on dark bg |
| `chart_slide` | Visualization — Gemini chart image or SVG fallback |
| `cta_slide` | Convert — fixed brand copy, always the last slide |

Slide count variants (MIN_SLIDES=4, MAX_SLIDES=8, DEFAULT_SLIDES=6):
- **4 slides**: cover → data_or_analysis → analysis_or_quote → cta_slide
- **5 slides**: cover → data_slide → analysis_slide → quote_or_chart → cta_slide
- **6 slides**: cover → data_slide → analysis_slide → analysis_slide → chart_slide → cta_slide
- **8 slides**: cover → data_slide → asset_1 → asset_2 → asset_3 → macro_context → key_levels → cta_slide

---

## Script JSON Schema

```json
{
  "title": "...",
  "caption": "...",
  "hashtags": ["inflation", "CPI", ...],
  "slides": [
    { "slide_number": 1, "type": "cover",
      "headline": "...", "subheadline": "...", "asset_tag": "...",
      "background_image_description": "..." },
    { "slide_number": 2, "type": "data_slide",
      "asset_tag": "...", "section_headline": "...",
      "data_points": [{"label": "...", "value": "...", "direction": "UP|DOWN|FLAT"}],
      "takeaway_line": "..." },
    { "slide_number": 3, "type": "analysis_slide",
      "asset_tag": "...", "analysis_paragraphs": ["...", "..."] },
    { "slide_number": 4, "type": "quote_slide",
      "asset_tag": "...", "quote_text": "...", "quote_attribution": "...",
      "rhetorical_question": "..." },
    { "slide_number": 5, "type": "chart_slide",
      "asset_tag": "...", "chart_asset": "...", "chart_type": "line_chart",
      "chart_caption": "..." },
    { "slide_number": 6, "type": "cta_slide" }
  ]
}
```

---

## Key Rules
- **`swipeable_carousel.py` is the template** — never change its layout, spacing, or colors without explicit user instruction
- **`output/cpi-38-inflation-test/carousel.html` is the visual reference** — new carousels must look identical to it (only content differs)
- Never skip the disclaimer on any slide — verbatim string from `config.py DISCLAIMER`
- All slide backgrounds are `#0A0A0A`; full-bleed photos always get a gradient dark overlay
- Orange `#FF6700` is used for: asset tags, data value emphasis, quote attributions, divider lines, chart lines/bars, top accent bars
- Safe zone is 180 px on all four sides — no text, logo, or disclaimer outside this boundary
- Gemini images are cached to `images/` — re-running reuses the cached file automatically
- The carousel HTML is fully self-contained (no external assets at runtime except Google Fonts)
