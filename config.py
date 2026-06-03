"""
Wisuno Carousel Automation — Brand & Pipeline Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
PROMPTS_DIR = BASE_DIR / "prompts"

BRAND_DIR = BASE_DIR / "Wisuno Logo"
LOGO_DIR = BRAND_DIR

# ── Brand Colors ────────────────────────────────────────────────────────────
# Source: Wisuno Brand Guidelines 7.pdf
BRAND_COLORS = {
    # Primary palette
    "orange":         "#FF6700",   # Neon Orange (primary accent)
    "black":          "#0A0A0A",   # Obsidian Black (background)
    "cloud_mist":     "#FAFAFA",   # Cloud Mist (light bg / contrast)
    # Secondary palette
    "velvet_noir":    "#2D1421",   # Velvet Noir (depth)
    "mint_whisper":   "#C1E8E2",   # Mint Whisper (fresh contrast)
    "vanilla_dusk":   "#F5ECC6",   # Vanilla Dusk (warmth)
    # Text
    "white":          "#FFFFFF",
    "text_primary":   "#FFFFFF",
    "text_secondary": "#CCCCCC",
    "light_grey":     "#888888",
    "dark_grey":      "#555555",
    "body_text":      "#CCCCCC",
}

# ── Typography ───────────────────────────────────────────────────────────────
# Source: Wisuno Brand Guidelines 7.pdf
# Primary font: Urbanist (headings) — Secondary font: General Sans (body)
FONTS = {
    "headline": "Urbanist",
    "body":     "General Sans",
}

FONT_SIZES = {
    "cover_headline":     60,
    "cover_subheadline":  22,
    "data_headline":      36,
    "data_value":         28,
    "data_label":         16,
    "analysis_body":      16,
    "quote_text":         28,
    "quote_attribution":  14,
    "chart_caption":      14,
    "cta_headline":       32,
    "cta_body":           16,
    "asset_tag":          13,
    "disclaimer":          9,
    # Educational slide types
    "concept_term":       44,
    "concept_definition": 18,
    "concept_why":        16,
    "steps_headline":     36,
    "steps_body":         16,
    "comparison_headline": 36,
    "comparison_header":  13,
    "comparison_body":    16,
    "example_headline":   36,
    "example_number":     52,
    "example_body":       16,
}

# ── Canvas ───────────────────────────────────────────────────────────────────
CANVAS_SIZE = {"width": 1080, "height": 1350}   # 4:5 portrait for Instagram

# ── Slide Defaults ───────────────────────────────────────────────────────────
MIN_SLIDES = 4
MAX_SLIDES = 8
DEFAULT_SLIDES = 6   # cover + 3 content + meme + CTA

# ── Disclaimer ───────────────────────────────────────────────────────────────
DISCLAIMER = (
    "CFD trading carries a high level of risk and may not be suitable for all investors. "
    "This content is for educational purposes only and does not constitute financial or investment advice. "
    "Wisuno Capital is regulated by CMA, CySEC, FSA & FSC. Trade responsibly."
)

# ── APIs ─────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID      = os.getenv("GOOGLE_CSE_ID", "")
HIGGSFIELD_API_KEY = os.getenv("HIGGSFIELD_API_KEY", "")
ANTHROPIC_MODEL    = "claude-sonnet-4-6"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# ── Article extraction ────────────────────────────────────────────────────────
MAX_ARTICLE_CHARS = 8_000
REQUEST_TIMEOUT   = 15   # seconds

# ── Slide layouts (for Canva builder reference) ───────────────────────────────
# All slides use a dark background (#0A0A0A) per the Carousel Design Template.
SLIDE_LAYOUTS = {
    "cover": {
        "background":        BRAND_COLORS["black"],
        "overlay_opacity":   0.65,
        "headline_font":     FONTS["headline"],
        "headline_size":     FONT_SIZES["cover_headline"],
        "headline_color":    BRAND_COLORS["text_primary"],
        "headline_weight":   "Bold",
        "subheadline_font":  FONTS["body"],
        "subheadline_size":  FONT_SIZES["cover_subheadline"],
        "subheadline_color": BRAND_COLORS["text_secondary"],
        "tag_color":         BRAND_COLORS["orange"],
        "tag_size":          FONT_SIZES["asset_tag"],
    },
    "data_slide": {
        "background":       BRAND_COLORS["black"],
        "headline_font":    FONTS["headline"],
        "headline_size":    FONT_SIZES["data_headline"],
        "headline_color":   BRAND_COLORS["text_primary"],
        "headline_weight":  "Bold",
        "label_font":       FONTS["body"],
        "label_size":       FONT_SIZES["data_label"],
        "label_color":      BRAND_COLORS["text_secondary"],
        "value_font":       FONTS["body"],
        "value_size":       FONT_SIZES["data_value"],
        "value_color":      BRAND_COLORS["text_primary"],
        "value_accent":     BRAND_COLORS["orange"],
        "takeaway_color":   BRAND_COLORS["text_secondary"],
    },
    "analysis_slide": {
        "background":    BRAND_COLORS["black"],
        "body_font":     FONTS["body"],
        "body_size":     FONT_SIZES["analysis_body"],
        "body_color":    BRAND_COLORS["text_primary"],
        "support_color": BRAND_COLORS["text_secondary"],
        "line_height":   1.6,
    },
    "quote_slide": {
        "background":          BRAND_COLORS["black"],
        "overlay_opacity":     0.60,
        "quote_font":          FONTS["headline"],
        "quote_size":          FONT_SIZES["quote_text"],
        "quote_color":         BRAND_COLORS["text_primary"],
        "quote_weight":        "Bold",
        "attribution_font":    FONTS["body"],
        "attribution_size":    FONT_SIZES["quote_attribution"],
        "attribution_color":   BRAND_COLORS["orange"],
        "rhetorical_color":    BRAND_COLORS["text_secondary"],
    },
    "chart_slide": {
        "background":       BRAND_COLORS["black"],
        "chart_line_color": BRAND_COLORS["orange"],
        "axis_color":       BRAND_COLORS["light_grey"],
        "caption_font":     FONTS["body"],
        "caption_size":     FONT_SIZES["chart_caption"],
        "caption_color":    BRAND_COLORS["text_secondary"],
    },
    "cta_slide": {
        "background":       BRAND_COLORS["black"],
        "headline_font":    FONTS["headline"],
        "headline_size":    FONT_SIZES["cta_headline"],
        "headline_color":   BRAND_COLORS["text_primary"],
        "headline_weight":  "Bold",
        "body_font":        FONTS["body"],
        "body_size":        FONT_SIZES["cta_body"],
        "body_color":       BRAND_COLORS["text_secondary"],
        "disclaimer_font":  FONTS["body"],
        "disclaimer_size":  FONT_SIZES["disclaimer"],
        "disclaimer_color": BRAND_COLORS["light_grey"],
    },
    # ── Educational slide layouts ─────────────────────────────────────────────
    "concept_slide": {
        "background":         BRAND_COLORS["black"],
        "term_font":          FONTS["headline"],
        "term_size":          FONT_SIZES["concept_term"],
        "term_color":         BRAND_COLORS["orange"],
        "term_weight":        "Bold",
        "definition_font":    FONTS["body"],
        "definition_size":    FONT_SIZES["concept_definition"],
        "definition_color":   BRAND_COLORS["text_primary"],
        "why_matters_color":  BRAND_COLORS["text_secondary"],
        "line_height":        1.65,
    },
    "steps_slide": {
        "background":         BRAND_COLORS["black"],
        "headline_font":      FONTS["headline"],
        "headline_size":      FONT_SIZES["steps_headline"],
        "headline_color":     BRAND_COLORS["text_primary"],
        "step_num_color":     BRAND_COLORS["orange"],
        "step_body_font":     FONTS["body"],
        "step_body_size":     FONT_SIZES["steps_body"],
        "step_body_color":    BRAND_COLORS["text_primary"],
        "connector_color":    BRAND_COLORS["dark_grey"],
    },
    "comparison_slide": {
        "background":         BRAND_COLORS["black"],
        "headline_font":      FONTS["headline"],
        "headline_size":      FONT_SIZES["comparison_headline"],
        "headline_color":     BRAND_COLORS["text_primary"],
        "header_color":       BRAND_COLORS["orange"],
        "col_b_color":        BRAND_COLORS["text_secondary"],
        "row_body_font":      FONTS["body"],
        "row_body_size":      FONT_SIZES["comparison_body"],
        "row_body_color":     BRAND_COLORS["text_primary"],
        "divider_color":      BRAND_COLORS["dark_grey"],
    },
    "example_slide": {
        "background":         BRAND_COLORS["black"],
        "headline_font":      FONTS["headline"],
        "headline_size":      FONT_SIZES["example_headline"],
        "headline_color":     BRAND_COLORS["text_primary"],
        "number_font":        FONTS["headline"],
        "number_size":        FONT_SIZES["example_number"],
        "number_color":       BRAND_COLORS["orange"],
        "body_font":          FONTS["body"],
        "body_size":          FONT_SIZES["example_body"],
        "body_color":         BRAND_COLORS["text_secondary"],
        "highlight_color":    BRAND_COLORS["white"],
    },
}
