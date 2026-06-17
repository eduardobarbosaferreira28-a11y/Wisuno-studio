"""
Canva design builder — generates the design spec that Claude Code executes
using Canva MCP tools (list-brand-kits, generate-design-structured,
start-editing-transaction, perform-editing-operations, commit-editing-transaction,
upload-asset-from-url).

HOW THIS WORKS
──────────────
This module does NOT call Canva directly. It produces a structured
`CanvaDesignSpec` object. The main orchestrator (carousel_agent.py) prints
this spec and instructs you (Claude Code running in this session) to execute
the Canva MCP tool calls described in it.

When running inside a Claude Code session, paste the printed spec into the
prompt and Claude Code will execute the Canva MCP calls automatically.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json

from config import CANVAS_SIZE, SLIDE_LAYOUTS, BRAND_COLORS, FONTS, FONT_SIZES, DISCLAIMER, LOGO_DIR

# Canvas dimensions
CANVAS_WIDTH  = 1080
CANVAS_HEIGHT = 1350

# Safe zone — text must stay inside these insets
SAFE_ZONE = {
    "left":   50,
    "right":  50,
    "top":    180,
    "bottom": 180,
}
# Derived safe-area bounds
SAFE_LEFT   = SAFE_ZONE["left"]
SAFE_RIGHT  = CANVAS_WIDTH  - SAFE_ZONE["right"]
SAFE_TOP    = SAFE_ZONE["top"]
SAFE_BOTTOM = CANVAS_HEIGHT - SAFE_ZONE["bottom"]
SAFE_WIDTH  = SAFE_RIGHT  - SAFE_LEFT    # 980 px
SAFE_HEIGHT = SAFE_BOTTOM - SAFE_TOP     # 990 px


@dataclass
class SlideSpec:
    slide_number: int
    slide_type: str          # cover | data_slide | analysis_slide | quote_slide | chart_slide | cta_slide
    layout: dict             # from SLIDE_LAYOUTS
    text_elements: list[dict] = field(default_factory=list)
    background_image_description: str | None = None   # cover slide image description
    data_points: list[dict] | None = None             # data_slide stats


@dataclass
class CanvaDesignSpec:
    title: str
    asset_tag: str
    num_pages: int
    canvas_width: int
    canvas_height: int
    slides: list[SlideSpec]

    def to_dict(self) -> dict:
        return {
            "title":       self.title,
            "asset_tag":   self.asset_tag,
            "num_pages":   self.num_pages,
            "canvas_size": f"{self.canvas_width}x{self.canvas_height}",
            "slides": [
                {
                    "slide_number":              s.slide_number,
                    "type":                      s.slide_type,
                    "text_elements":             s.text_elements,
                    "background_image_description": s.background_image_description,
                    "data_points":               s.data_points,
                }
                for s in self.slides
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def build_design_spec(script: dict) -> CanvaDesignSpec:
    """
    Convert a carousel script dict (from script_generator.py) into a CanvaDesignSpec.
    """
    slides_data = script["slides"]
    slide_specs: list[SlideSpec] = []

    for slide in slides_data:
        stype = slide["type"]
        layout = SLIDE_LAYOUTS.get(stype, SLIDE_LAYOUTS["analysis_slide"])
        spec = SlideSpec(
            slide_number=slide["slide_number"],
            slide_type=stype,
            layout=layout,
        )

        if stype == "cover":
            spec.background_image_description = slide.get("background_image_description")
            spec.text_elements = [
                _text("asset_tag",    slide.get("asset_tag", script["asset_tag"]),
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Medium", "upper"),
                _text("headline",     slide["headline"],
                      FONT_SIZES["cover_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold", "upper"),
                _text("subheadline",  slide.get("subheadline", ""),
                      FONT_SIZES["cover_subheadline"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("disclaimer",   DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        elif stype == "data_slide":
            spec.data_points = slide.get("data_points", [])
            spec.text_elements = [
                _text("asset_tag",       slide.get("asset_tag", script["asset_tag"]),
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Medium", "upper"),
                _text("section_headline", slide.get("section_headline", ""),
                      FONT_SIZES["data_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("takeaway_line",   slide.get("takeaway_line", ""),
                      FONT_SIZES["analysis_body"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("disclaimer",      DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        elif stype == "analysis_slide":
            paragraphs = slide.get("analysis_paragraphs", [])
            spec.text_elements = [
                _text("asset_tag",  slide.get("asset_tag", script["asset_tag"]),
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Medium", "upper"),
                _text("body",       "\n\n".join(paragraphs),
                      FONT_SIZES["analysis_body"], BRAND_COLORS["text_primary"], FONTS["body"], "Regular"),
                _text("disclaimer", DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        elif stype == "quote_slide":
            spec.text_elements = [
                _text("asset_tag",           slide.get("asset_tag", script["asset_tag"]),
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Medium", "upper"),
                _text("rhetorical_question",  slide.get("rhetorical_question") or "",
                      FONT_SIZES["analysis_body"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("quote_text",           f'"{slide.get("quote_text", "")}"',
                      FONT_SIZES["quote_text"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("quote_attribution",    slide.get("quote_attribution", ""),
                      FONT_SIZES["quote_attribution"], BRAND_COLORS["orange"], FONTS["body"], "Regular"),
                _text("disclaimer",           DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        elif stype == "chart_slide":
            spec.text_elements = [
                _text("asset_tag",     slide.get("asset_tag", script["asset_tag"]),
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Medium", "upper"),
                _text("chart_asset",   slide.get("chart_asset", ""),
                      FONT_SIZES["data_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("chart_caption", slide.get("chart_caption", ""),
                      FONT_SIZES["chart_caption"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("disclaimer",    DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        elif stype == "cta_slide":
            spec.text_elements = [
                _text("platform_label", "Trading Platform",
                      FONT_SIZES["asset_tag"], BRAND_COLORS["orange"], FONTS["body"], "Regular"),
                _text("domain",         "Wisuno.com",
                      FONT_SIZES["cta_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("cta_headline",   "Start trading with Wisuno.",
                      FONT_SIZES["data_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("cta_body",       "Start with a free demo to explore markets risk-free, then upgrade to live trading for full access, advanced tools, and exclusive benefits.",
                      FONT_SIZES["cta_body"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("follow_prompt",  "FOLLOW FOR MORE",
                      FONT_SIZES["data_headline"], BRAND_COLORS["text_primary"], FONTS["headline"], "Bold"),
                _text("follow_subtext", "Daily market breakdowns so you never miss a macro move",
                      FONT_SIZES["cta_body"], BRAND_COLORS["text_secondary"], FONTS["body"], "Regular"),
                _text("disclaimer",     DISCLAIMER,
                      FONT_SIZES["disclaimer"], BRAND_COLORS["light_grey"], FONTS["body"], "Regular"),
            ]

        slide_specs.append(spec)

    return CanvaDesignSpec(
        title=script["title"],
        asset_tag=script["asset_tag"],
        num_pages=len(slide_specs),
        canvas_width=CANVAS_SIZE["width"],
        canvas_height=CANVAS_SIZE["height"],
        slides=slide_specs,
    )


def _text(role: str, content: str, size: int, color: str,
          font: str, weight: str, transform: str = "none") -> dict:
    return {
        "role":      role,
        "content":   content,
        "font":      font,
        "size":      size,
        "color":     color,
        "weight":    weight,
        "transform": transform,
    }


def generate_canva_prompt(spec: CanvaDesignSpec) -> str:
    """
    Generate the natural-language prompt to pass to Canva's
    `generate-design-structured` MCP tool.
    """
    slide_descriptions = []
    for s in spec.slides:
        texts = {el["role"]: el["content"] for el in s.text_elements}

        if s.slide_type == "cover":
            img_note = f" Background image theme: {s.background_image_description}." if s.background_image_description else ""
            desc = (
                f"Slide {s.slide_number} (COVER): Full-bleed dark financial photo with 60–80% dark overlay.{img_note} "
                f"Logo from local file '{LOGO_DIR / 'White-Colored.png'}' (upload via upload-asset-from-url) top-left corner. "
                f"Orange uppercase asset tag '{texts.get('asset_tag', '')}' — top-left or above headline. "
                f"Very large bold white headline ALL CAPS: '{texts.get('headline', '')}'. "
                f"Below headline: thin orange (#FF6700) horizontal divider line ~180px. "
                f"White subheadline: '{texts.get('subheadline', '')}'. "
                f"Tiny disclaimer text at very bottom, color #888888."
            )

        elif s.slide_type == "data_slide":
            dp_lines = ""
            if s.data_points:
                dp_lines = " | ".join(
                    f"{dp['label']}: {dp['value']} ({dp.get('direction', '')})"
                    for dp in s.data_points
                )
            desc = (
                f"Slide {s.slide_number} (DATA): Solid dark background #0A0A0A. "
                f"Orange asset tag pill '{texts.get('asset_tag', '')}' top-left. "
                f"Large bold white section headline: '{texts.get('section_headline', '')}'. "
                f"Vertical list of 3–5 data points, each on its own line — label in #CCCCCC, value in white or #FF6700 for emphasis. "
                f"Data: {dp_lines}. "
                f"Takeaway line in italic grey at bottom of data block: '{texts.get('takeaway_line', '')}'. "
                f"Tiny disclaimer at very bottom."
            )

        elif s.slide_type == "analysis_slide":
            desc = (
                f"Slide {s.slide_number} (ANALYSIS): Solid dark background #0A0A0A. "
                f"Optional faint background graphic at 10–20% opacity. "
                f"Orange asset tag top-left: '{texts.get('asset_tag', '')}'. "
                f"Body copy paragraphs in white/light grey, General Sans regular, 1.6x line height: '{texts.get('body', '')}'. "
                f"Tiny disclaimer at very bottom."
            )

        elif s.slide_type == "quote_slide":
            rhetorical = texts.get("rhetorical_question", "")
            rhetorical_line = f"Rhetorical framing text above quote: '{rhetorical}'. " if rhetorical else ""
            desc = (
                f"Slide {s.slide_number} (QUOTE): Dark background, optionally a blurred/darkened photo of the speaker or a relevant scene. "
                f"Orange asset tag top-left: '{texts.get('asset_tag', '')}'. "
                f"{rhetorical_line}"
                f"Large bold white quote centered: {texts.get('quote_text', '')}. "
                f"Orange attribution below quote: '{texts.get('quote_attribution', '')}'. "
                f"Tiny disclaimer at very bottom."
            )

        elif s.slide_type == "chart_slide":
            desc = (
                f"Slide {s.slide_number} (CHART): Dark background #0A0A0A. "
                f"Orange asset tag top-left: '{texts.get('asset_tag', '')}'. "
                f"Chart or graph occupying 60–75% of slide — dark-themed, minimal grid, "
                f"orange (#FF6700) chart line or bars, white axis labels. "
                f"Chart subject: '{texts.get('chart_asset', '')}'. "
                f"Grey caption below chart: '{texts.get('chart_caption', '')}'. "
                f"Tiny disclaimer at very bottom."
            )

        elif s.slide_type == "cta_slide":
            desc = (
                f"Slide {s.slide_number} (CTA): Solid dark background #0A0A0A, subtle upward-trending chart graphic at low opacity. "
                f"Logo from local file '{LOGO_DIR / 'White-Colored.png'}' (upload via upload-asset-from-url) top-center. "
                f"Orange label 'Trading Platform' above domain. "
                f"Large bold white 'Wisuno.com' center. "
                f"Bold white CTA headline: 'Start trading with Wisuno.' "
                f"Light grey body copy: '{texts.get('cta_body', '')}'. "
                f"Bold white 'FOLLOW FOR MORE' with grey subtext below. "
                f"Tiny disclaimer text at very bottom in #888888."
            )
        else:
            desc = f"Slide {s.slide_number}: {s.slide_type}"

        slide_descriptions.append(desc)

    slides_block = "\n".join(f"  - {d}" for d in slide_descriptions)

    return f"""Create a {spec.num_pages}-page Instagram carousel design for Wisuno, \
a financial/CFD trading brand.

CANVAS SIZE: {CANVAS_WIDTH} x {CANVAS_HEIGHT} pixels (4:5 portrait, Instagram format)

TEXT SAFE ZONE: All text elements must be placed within the safe zone only.
- Left edge:   {SAFE_LEFT} px from canvas left
- Right edge:  {SAFE_RIGHT} px from canvas left  (i.e. {SAFE_ZONE["right"]} px margin from right)
- Top edge:    {SAFE_TOP} px from canvas top
- Bottom edge: {SAFE_BOTTOM} px from canvas top  (i.e. {SAFE_ZONE["bottom"]} px margin from bottom)
- Safe area:   {SAFE_WIDTH} × {SAFE_HEIGHT} px
No text, label, or disclaimer may extend outside these bounds.

BRAND IDENTITY:
- Background: Near-black #0A0A0A on all slides
- Accent color: Orange #FF6700
- Primary text: #FFFFFF | Secondary text: #CCCCCC
- Heading font: Urbanist Bold (all headlines, dominant text)
- Body font: General Sans (body copy, labels, captions)
- Logo: Use local logo files (White-Colored.png on dark backgrounds)
- Visual style: Dark, bold, financial — minimal dark backgrounds with orange accents
- All full-bleed background images get a 60–80% dark overlay for text legibility

CAROUSEL TITLE: {spec.title}
ASSET: {spec.asset_tag}

SLIDES:
{slides_block}

DESIGN RULES:
- Every slide must feel like part of the same dark brand system
- ALL text must stay inside the safe zone: {SAFE_LEFT}px left, {SAFE_RIGHT}px right, {SAFE_TOP}px top, {SAFE_BOTTOM}px bottom
- Text must be large enough to read on mobile
- Orange (#FF6700) is used for: asset tags, data value emphasis, quote attributions, divider lines, chart lines
- Disclaimer text is always the smallest element, #888888, at the very bottom of each slide
- Never use white or light backgrounds — every slide background is #0A0A0A or a darkened photo
"""
