"""
HTML slide renderer for Wisuno Instagram carousels.

Each public function returns a complete, self-contained HTML string at 1080×1350 px
(Instagram 4:5 portrait) that Playwright can screenshot directly to PNG.

Brand tokens
  Background  #0A0A0A
  Orange      #FF6700
  White       #FFFFFF
  Secondary   #CCCCCC
  Disclaimer  #888888
  Headline    Urbanist Bold (Google Fonts)
  Body        Inter (Google Fonts — substitute for General Sans)
"""
import base64
import html as _esc
from pathlib import Path

from config import BASE_DIR, DISCLAIMER

# ── Logo ─────────────────────────────────────────────────────────────────────
_LOGO_PATH = BASE_DIR / "Wisuno Logo" / "White-Colored.png"
_LOGO_URI: str | None = None


def _logo() -> str:
    global _LOGO_URI
    if _LOGO_URI is None:
        data = _LOGO_PATH.read_bytes()
        b64 = base64.b64encode(data).decode()
        _LOGO_URI = f"data:image/png;base64,{b64}"
    return _LOGO_URI


def _e(text: object) -> str:
    return _esc.escape(str(text))


# ── Shared CSS injected into every slide ─────────────────────────────────────
_CSS = """\
@import url('https://fonts.googleapis.com/css2?family=Urbanist:wght@400;600;700;900&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

body {
  width: 1080px;
  height: 1350px;
  overflow: hidden;
  background: #0A0A0A;
  font-family: 'Inter', sans-serif;
  color: #FFFFFF;
}

.slide {
  width: 1080px;
  height: 1350px;
  position: relative;
  overflow: hidden;
  background: #0A0A0A;
}

.logo {
  position: absolute;
  top: 52px;
  right: 56px;
  height: 30px;
  width: auto;
  object-fit: contain;
  z-index: 20;
}

.asset-tag {
  display: inline-block;
  font-family: 'Urbanist', sans-serif;
  font-size: 13px;
  font-weight: 700;
  color: #FF6700;
  letter-spacing: 3px;
  text-transform: uppercase;
  padding: 7px 16px;
  border: 1.5px solid #FF6700;
  border-radius: 3px;
}

.disclaimer {
  position: absolute;
  bottom: 36px;
  left: 56px;
  right: 56px;
  font-family: 'Inter', sans-serif;
  font-size: 9px;
  font-weight: 400;
  color: #888888;
  line-height: 1.55;
}

.o-line { width: 56px; height: 3px; background: #FF6700; border-radius: 2px; }
"""


def _doc(title: str, body: str) -> str:
    """Wrap slide body in a complete HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1080, initial-scale=1">
  <title>{_e(title)}</title>
  <style>
{_CSS}
  </style>
</head>
<body>
{body}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# COVER SLIDE
# ─────────────────────────────────────────────────────────────────────────────
def render_cover(slide: dict, bg_data_uri: str | None = None) -> str:
    """
    Full-bleed dark photo + gradient overlay.
    Large ALL-CAPS headline in the bottom third.
    """
    headline = _e(slide.get("headline", ""))
    sub = _e(slide.get("subheadline", ""))
    tag = _e(slide.get("asset_tag", ""))

    bg_css = ""
    overlay = ""
    if bg_data_uri:
        bg_css = f"background-image:url('{bg_data_uri}');background-size:cover;background-position:center;"
        overlay = (
            '<div style="position:absolute;inset:0;'
            'background:linear-gradient('
            'to bottom,'
            'rgba(10,10,10,0.45) 0%,'
            'rgba(10,10,10,0.55) 40%,'
            'rgba(10,10,10,0.82) 70%,'
            'rgba(10,10,10,0.96) 100%'
            ');z-index:1;"></div>'
        )

    body = f"""\
<div class="slide" style="{bg_css}">
  {overlay}

  <!-- Top bar -->
  <div style="position:absolute;top:52px;left:56px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">

  <!-- Bottom content area -->
  <div style="position:absolute;left:56px;right:56px;bottom:110px;z-index:20;">
    <div class="o-line" style="margin-bottom:28px;"></div>
    <h1 style="
      font-family:'Urbanist',sans-serif;
      font-size:62px;
      font-weight:900;
      color:#FFFFFF;
      line-height:1.05;
      letter-spacing:-0.5px;
      text-transform:uppercase;
      margin-bottom:22px;
    ">{headline}</h1>
    <p style="
      font-family:'Inter',sans-serif;
      font-size:21px;
      font-weight:400;
      color:#CCCCCC;
      line-height:1.45;
    ">{sub}</p>
  </div>

  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc(slide.get("headline", "Cover"), body)


# ─────────────────────────────────────────────────────────────────────────────
# DATA SLIDE
# ─────────────────────────────────────────────────────────────────────────────
_DIR_ARROW = {"UP": "↑", "DOWN": "↓", "FLAT": "→"}
_DIR_COLOR = {"UP": "#FF6700", "DOWN": "#EF4444", "FLAT": "#888888"}


def render_data_slide(slide: dict) -> str:
    """
    Key numbers — stat list with labels, values, directional cues.
    Orange accents on values. Takeaway line at the bottom.
    """
    headline = _e(slide.get("section_headline", ""))
    tag = _e(slide.get("asset_tag", ""))
    data_points: list[dict] = slide.get("data_points", [])
    takeaway = _e(slide.get("takeaway_line", ""))

    rows_html = ""
    for dp in data_points:
        label = _e(dp.get("label", ""))
        value = _e(dp.get("value", ""))
        direction = dp.get("direction", "FLAT").upper()
        arrow = _DIR_ARROW.get(direction, "→")
        arrow_color = _DIR_COLOR.get(direction, "#888888")
        rows_html += f"""\
    <div style="
      display:flex;
      align-items:center;
      justify-content:space-between;
      padding:18px 0;
      border-bottom:1px solid rgba(255,255,255,0.07);
    ">
      <span style="
        font-family:'Inter',sans-serif;
        font-size:16px;
        font-weight:400;
        color:#CCCCCC;
        flex:1;
        padding-right:16px;
      ">{label}</span>
      <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
        <span style="
          font-family:'Urbanist',sans-serif;
          font-size:26px;
          font-weight:700;
          color:#FFFFFF;
        ">{value}</span>
        <span style="
          font-size:22px;
          font-weight:700;
          color:{arrow_color};
          line-height:1;
        ">{arrow}</span>
      </div>
    </div>\n"""

    body = f"""\
<div class="slide">
  <!-- Top bar -->
  <div style="position:absolute;top:52px;left:56px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">

  <!-- Orange top accent bar -->
  <div style="position:absolute;top:0;left:0;right:0;height:5px;background:#FF6700;z-index:20;"></div>

  <!-- Main content -->
  <div style="position:absolute;top:148px;left:56px;right:56px;bottom:110px;display:flex;flex-direction:column;">
    <h2 style="
      font-family:'Urbanist',sans-serif;
      font-size:38px;
      font-weight:700;
      color:#FFFFFF;
      line-height:1.15;
      margin-bottom:36px;
    ">{headline}</h2>

    <!-- Data rows -->
    <div style="flex:1;">
{rows_html}
    </div>

    <!-- Takeaway -->
    <div style="
      margin-top:32px;
      padding:20px 24px;
      border-left:3px solid #FF6700;
      background:rgba(255,103,0,0.06);
    ">
      <p style="
        font-family:'Inter',sans-serif;
        font-size:15px;
        font-weight:500;
        color:#CCCCCC;
        line-height:1.55;
        font-style:italic;
      ">{takeaway}</p>
    </div>
  </div>

  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc(slide.get("section_headline", "Data"), body)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS SLIDE
# ─────────────────────────────────────────────────────────────────────────────
def render_analysis_slide(slide: dict, slide_num: int = 0) -> str:
    """
    2–3 analysis paragraphs on a dark background.
    Orange vertical accent bar on the left.
    """
    tag = _e(slide.get("asset_tag", ""))
    paragraphs: list[str] = slide.get("analysis_paragraphs", [])

    paras_html = ""
    for i, p in enumerate(paragraphs):
        mt = "0" if i == 0 else "32px"
        paras_html += f"""\
    <p style="
      font-family:'Inter',sans-serif;
      font-size:{'20px' if len(paragraphs) <= 2 else '18px'};
      font-weight:400;
      color:{'#FFFFFF' if i == 0 else '#CCCCCC'};
      line-height:1.7;
      margin-top:{mt};
    ">{_e(p)}</p>\n"""

    # Slide label — "Analysis 1", "Analysis 2" etc.
    label = f"0{slide_num}" if slide_num < 10 else str(slide_num)

    body = f"""\
<div class="slide">
  <!-- Top bar -->
  <div style="position:absolute;top:52px;left:56px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">

  <!-- Slide number label top-right area (below logo) -->
  <div style="position:absolute;top:100px;right:56px;z-index:20;">
    <span style="
      font-family:'Urbanist',sans-serif;
      font-size:72px;
      font-weight:900;
      color:rgba(255,103,0,0.08);
      line-height:1;
    ">{label}</span>
  </div>

  <!-- Left orange vertical accent -->
  <div style="
    position:absolute;
    top:148px;
    left:56px;
    width:4px;
    bottom:110px;
    background:linear-gradient(to bottom,#FF6700 0%,rgba(255,103,0,0) 100%);
    border-radius:4px;
    z-index:10;
  "></div>

  <!-- Content -->
  <div style="position:absolute;top:148px;left:88px;right:56px;bottom:110px;display:flex;flex-direction:column;justify-content:center;">
{paras_html}
  </div>

  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc("Analysis", body)


# ─────────────────────────────────────────────────────────────────────────────
# QUOTE SLIDE
# ─────────────────────────────────────────────────────────────────────────────
def render_quote_slide(slide: dict) -> str:
    """
    Sourced quote centered on dark bg.
    Large orange open-quote mark, attribution in orange.
    """
    tag = _e(slide.get("asset_tag", ""))
    quote = _e(slide.get("quote_text", ""))
    attribution = _e(slide.get("quote_attribution", ""))
    rhetorical = slide.get("rhetorical_question")

    rhetorical_html = ""
    if rhetorical:
        rhetorical_html = f"""\
    <p style="
      font-family:'Inter',sans-serif;
      font-size:17px;
      font-style:italic;
      color:#888888;
      line-height:1.55;
      margin-top:40px;
      max-width:760px;
    ">{_e(rhetorical)}</p>"""

    body = f"""\
<div class="slide">
  <!-- Top bar -->
  <div style="position:absolute;top:52px;left:56px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">

  <!-- Decorative large quotation mark -->
  <div style="
    position:absolute;
    top:130px;
    left:48px;
    font-family:'Urbanist',sans-serif;
    font-size:200px;
    font-weight:900;
    color:rgba(255,103,0,0.12);
    line-height:1;
    z-index:1;
    user-select:none;
  ">"</div>

  <!-- Centered content -->
  <div style="
    position:absolute;
    top:0;bottom:0;left:0;right:0;
    display:flex;
    flex-direction:column;
    align-items:flex-start;
    justify-content:center;
    padding:0 72px;
    z-index:10;
  ">
    <blockquote style="
      font-family:'Urbanist',sans-serif;
      font-size:32px;
      font-weight:700;
      color:#FFFFFF;
      line-height:1.4;
      max-width:900px;
    ">{quote}</blockquote>

    <div style="display:flex;align-items:center;gap:16px;margin-top:36px;">
      <div style="width:40px;height:2px;background:#FF6700;border-radius:1px;"></div>
      <span style="
        font-family:'Inter',sans-serif;
        font-size:14px;
        font-weight:600;
        color:#FF6700;
        letter-spacing:1px;
        text-transform:uppercase;
      ">{attribution}</span>
    </div>

    {rhetorical_html}
  </div>

  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc("Quote", body)


# ─────────────────────────────────────────────────────────────────────────────
# CHART SLIDE
# ─────────────────────────────────────────────────────────────────────────────
def render_chart_slide(slide: dict, chart_data_uri: str | None = None) -> str:
    """
    Chart image filling 60–75% of the slide.
    Caption below. Fallback to a styled placeholder if no image.
    """
    tag = _e(slide.get("asset_tag", ""))
    chart_asset = _e(slide.get("chart_asset", ""))
    caption = _e(slide.get("chart_caption", ""))

    if chart_data_uri:
        chart_content = f"""\
    <div style="width:100%;flex:1;position:relative;overflow:hidden;border-radius:4px;">
      <img src="{chart_data_uri}" style="
        width:100%;height:100%;object-fit:cover;
        filter:brightness(0.9) contrast(1.05);
      ">
      <!-- subtle orange tint overlay at bottom -->
      <div style="
        position:absolute;bottom:0;left:0;right:0;height:30%;
        background:linear-gradient(to top,rgba(10,10,10,0.6) 0%,transparent 100%);
      "></div>
    </div>"""
    else:
        # Styled SVG placeholder chart
        chart_content = f"""\
    <div style="
      width:100%;flex:1;
      border:1px solid rgba(255,103,0,0.2);
      border-radius:4px;
      background:rgba(255,103,0,0.03);
      display:flex;flex-direction:column;
      align-items:center;justify-content:center;
      position:relative;overflow:hidden;
    ">
      <!-- Decorative SVG line chart -->
      <svg viewBox="0 0 900 500" style="width:90%;height:auto;opacity:0.6;">
        <defs>
          <linearGradient id="og" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#FF6700" stop-opacity="0.3"/>
            <stop offset="100%" stop-color="#FF6700" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <!-- grid lines -->
        <line x1="0" y1="100" x2="900" y2="100" stroke="#222" stroke-width="1"/>
        <line x1="0" y1="200" x2="900" y2="200" stroke="#222" stroke-width="1"/>
        <line x1="0" y1="300" x2="900" y2="300" stroke="#222" stroke-width="1"/>
        <line x1="0" y1="400" x2="900" y2="400" stroke="#222" stroke-width="1"/>
        <!-- area fill -->
        <path d="M0,400 C100,380 150,320 220,260 S340,160 420,130 S580,90 660,110 S800,150 900,80 L900,500 L0,500 Z"
              fill="url(#og)"/>
        <!-- orange line -->
        <path d="M0,400 C100,380 150,320 220,260 S340,160 420,130 S580,90 660,110 S800,150 900,80"
              fill="none" stroke="#FF6700" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
      </svg>
      <p style="
        font-family:'Inter',sans-serif;
        font-size:13px;
        color:#555;
        margin-top:16px;
        letter-spacing:1px;
        text-transform:uppercase;
      ">{chart_asset}</p>
    </div>"""

    body = f"""\
<div class="slide">
  <!-- Top bar -->
  <div style="position:absolute;top:52px;left:56px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">

  <!-- Main layout -->
  <div style="
    position:absolute;
    top:140px;left:56px;right:56px;bottom:110px;
    display:flex;flex-direction:column;gap:24px;
  ">
{chart_content}

    <!-- Caption -->
    <div style="flex-shrink:0;padding-bottom:8px;">
      <div class="o-line" style="margin-bottom:12px;"></div>
      <p style="
        font-family:'Inter',sans-serif;
        font-size:15px;
        font-weight:400;
        color:#CCCCCC;
        line-height:1.5;
      ">{caption}</p>
    </div>
  </div>

  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc("Chart", body)


# ─────────────────────────────────────────────────────────────────────────────
# CTA SLIDE
# ─────────────────────────────────────────────────────────────────────────────
def render_cta_slide(slide: dict | None = None) -> str:
    """
    Fixed brand CTA — always the last slide.
    Logo centered, FOLLOW FOR MORE headline, sub-copy, disclaimer.
    """
    body = f"""\
<div class="slide">
  <!-- Decorative background grid -->
  <svg style="position:absolute;inset:0;width:100%;height:100%;opacity:0.04;" viewBox="0 0 1080 1350">
    <defs>
      <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
        <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#FF6700" stroke-width="0.5"/>
      </pattern>
    </defs>
    <rect width="1080" height="1350" fill="url(#grid)"/>
  </svg>

  <!-- Orange top bar -->
  <div style="position:absolute;top:0;left:0;right:0;height:5px;background:#FF6700;z-index:20;"></div>

  <!-- Centered content -->
  <div style="
    position:absolute;inset:0;
    display:flex;flex-direction:column;
    align-items:center;justify-content:center;
    padding:0 80px;
    text-align:center;
    z-index:10;
  ">
    <!-- Wisuno logo -->
    <img src="{_logo()}" alt="Wisuno" style="height:44px;width:auto;margin-bottom:64px;object-fit:contain;">

    <div class="o-line" style="margin:0 auto 40px;width:80px;"></div>

    <h2 style="
      font-family:'Urbanist',sans-serif;
      font-size:52px;
      font-weight:900;
      color:#FFFFFF;
      letter-spacing:3px;
      text-transform:uppercase;
      margin-bottom:24px;
      line-height:1.1;
    ">FOLLOW FOR MORE</h2>

    <p style="
      font-family:'Inter',sans-serif;
      font-size:20px;
      font-weight:400;
      color:#CCCCCC;
      line-height:1.5;
      max-width:680px;
      margin-bottom:56px;
    ">Daily market breakdowns so you never miss a macro move.</p>

    <!-- Platform handle -->
    <div style="
      display:flex;align-items:center;gap:12px;
      padding:14px 32px;
      border:1.5px solid rgba(255,103,0,0.5);
      border-radius:4px;
    ">
      <span style="
        font-family:'Urbanist',sans-serif;
        font-size:18px;
        font-weight:600;
        color:#FF6700;
        letter-spacing:1px;
      ">@wisuno</span>
    </div>
  </div>

  <!-- Disclaimer at bottom -->
  <div class="disclaimer" style="text-align:center;">{_e(DISCLAIMER)}</div>
</div>"""
    return _doc("Follow Wisuno", body)
