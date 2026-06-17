"""
Wisuno Swipeable HTML Carousel Generator.

Produces a single self-contained HTML file with all slides embedded inline.
Supports: touch swipe, mouse drag, keyboard arrows, dot navigation.

Each slide is rendered at the canonical 1080×1350 px canvas and scaled
responsively to fit the browser window — no upscaling beyond native resolution.

Usage (standalone):
    python swipeable_carousel.py --script output/some-folder/script.json
    python swipeable_carousel.py --script output/some-folder/script.json --no-images

The output HTML is written to output/<folder>/carousel.html.
"""
import base64
import html as _esc
import json
import re
import sys
from pathlib import Path

# ── Brand tokens ────────────────────────────────────────────────────────────
_BG       = "#0A0A0A"
_ORANGE   = "#FF6700"
_WHITE    = "#FFFFFF"
_GRAY     = "#CCCCCC"
_DIM      = "#888888"

# Light theme — English non-cover slides only
_CLOUD_MIST      = "#FAFAFA"
_LIGHT_PRIMARY   = "#0A0A0A"
_LIGHT_SECONDARY = "#444444"
_LIGHT_DIM       = "#666666"
_LIGHT_BORDER    = "rgba(0,0,0,0.10)"

_BASE_DIR = Path(__file__).parent
_LOGO_PATH = _BASE_DIR / "Wisuno Logo" / "White-Colored.png"
_DARK_LOGO_PATH = _BASE_DIR / "Wisuno Logo" / "Black-Colored.png"

# ── Language / font configuration ───────────────────────────────────────────
_FONT_CONFIGS: dict[str, dict] = {
    "en": {
        "google_fonts": (
            "https://fonts.googleapis.com/css2?family=Urbanist:wght@400;600;700;900"
            "&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap"
        ),
        "heading": "'Urbanist'",
        "body":    "'Inter'",
    },
    "zh-TW": {
        "google_fonts": (
            "https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;700;900"
            "&family=Noto+Sans+TC:wght@300;400;500;600&display=swap"
        ),
        "heading": "'Noto Serif TC'",
        "body":    "'Noto Sans TC'",
    },
    "zh-CN": {
        "google_fonts": (
            "https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900"
            "&family=Noto+Sans+SC:wght@300;400;500;600&display=swap"
        ),
        "heading": "'Noto Serif SC'",
        "body":    "'Noto Sans SC'",
    },
    "th": {
        "google_fonts": (
            "https://fonts.googleapis.com/css2?family=Sarabun:ital,wght@"
            "0,300;0,400;0,500;0,600;0,700;1,400&display=swap"
        ),
        "heading": "'Sarabun'",
        "body":    "'Sarabun'",
    },
    # Brazilian Portuguese is Latin-script — reuse the brand fonts (Urbanist + Inter).
    "pt-BR": {
        "google_fonts": (
            "https://fonts.googleapis.com/css2?family=Urbanist:wght@400;600;700;900"
            "&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap"
        ),
        "heading": "'Urbanist'",
        "body":    "'Inter'",
    },
}

# ── CTA slide copy per language ──────────────────────────────────────────────
_CTA_CONTENT: dict[str, tuple[str, str]] = {
    "en":    ("FOLLOW FOR MORE",  "Daily market breakdowns so you never miss a macro move."),
    "zh-TW": ("追蹤更多內容",      "每日市場解析，讓您掌握每一個宏觀動態。"),
    "zh-CN": ("关注获取更多",      "每日市场解析，让您掌握每一个宏观动态。"),
    "th":    ("ติดตามเพิ่มเติม",  "วิเคราะห์ตลาดรายวัน ไม่พลาดทุกความเคลื่อนไหวเศรษฐกิจมหภาค"),
    "pt-BR": ("SIGA PARA MAIS",  "Análises de mercado diárias para você nunca perder um movimento macro."),
}

_CTA_CONTENT_EDUCATIONAL: dict[str, tuple[str, str]] = {
    "en":    ("FOLLOW FOR MORE",  "New financial concepts every week — so you never stop learning."),
    "zh-TW": ("追蹤更多內容",      "每週全新金融概念，讓您持續學習、不斷進步。"),
    "zh-CN": ("关注获取更多",      "每周全新金融概念，让您持续学习、不断进步。"),
    "th":    ("ติดตามเพิ่มเติม",  "แนวคิดการเงินใหม่ทุกสัปดาห์ เพื่อให้คุณไม่หยุดเรียนรู้"),
    "pt-BR": ("SIGA PARA MAIS",  "Novos conceitos financeiros toda semana — para você nunca parar de aprender."),
}

_CTA_CONTENT_PROMOTIONAL: dict[str, tuple[str, str]] = {
    "en":    ("FOLLOW FOR MORE",  "Join a community trading smarter with Wisuno — clear markets, every day."),
    "zh-TW": ("追蹤更多內容",      "加入 Wisuno 社群，與更聰明的交易者同行——每日看懂市場。"),
    "zh-CN": ("关注获取更多",      "加入 Wisuno 社群，与更聪明的交易者同行——每日看懂市场。"),
    "th":    ("ติดตามเพิ่มเติม",  "ร่วมเป็นส่วนหนึ่งของชุมชน Wisuno เทรดอย่างชาญฉลาด เข้าใจตลาดทุกวัน"),
    "pt-BR": ("SIGA PARA MAIS",  "Junte-se a uma comunidade que opera de forma mais inteligente com a Wisuno — mercados claros, todos os dias."),
}

# ── UI chrome strings per language ───────────────────────────────────────────
_UI_STRINGS: dict[str, dict] = {
    "en": {
        "html_lang":    "en",
        "slide_label":  "Slide",
        "prev_slide":   "Previous slide",
        "next_slide":   "Next slide",
        "download_btn": "Download All Slides (JPG)",
        "loading":      "Loading libraries...",
        "rendering":    "Rendering {i} / {n}...",
        "packaging":    "Packaging ZIP...",
        "done":         "Download All Slides (JPG)",
        "error":        "Export failed \u2014 try again",
    },
    "zh-TW": {
        "html_lang":    "zh-TW",
        "slide_label":  "幻燈片",
        "prev_slide":   "上一張",
        "next_slide":   "下一張",
        "download_btn": "下載全部幻燈片 (JPG)",
        "loading":      "載入中...",
        "rendering":    "渲染 {i} / {n}...",
        "packaging":    "打包 ZIP...",
        "done":         "下載全部幻燈片 (JPG)",
        "error":        "匯出失敗，請重試",
    },
    "zh-CN": {
        "html_lang":    "zh-CN",
        "slide_label":  "幻灯片",
        "prev_slide":   "上一张",
        "next_slide":   "下一张",
        "download_btn": "下载全部幻灯片 (JPG)",
        "loading":      "加载中...",
        "rendering":    "渲染 {i} / {n}...",
        "packaging":    "打包 ZIP...",
        "done":         "下载全部幻灯片 (JPG)",
        "error":        "导出失败，请重试",
    },
    "pt-BR": {
        "html_lang":    "pt-BR",
        "slide_label":  "Slide",
        "prev_slide":   "Slide anterior",
        "next_slide":   "Próximo slide",
        "download_btn": "Baixar todos os slides (JPG)",
        "loading":      "Carregando...",
        "rendering":    "Renderizando {i} / {n}...",
        "packaging":    "Compactando ZIP...",
        "done":         "Baixar todos os slides (JPG)",
        "error":        "Falha na exportação — tente novamente",
    },
    "th": {
        "html_lang":    "th",
        "slide_label":  "สไลด์",
        "prev_slide":   "สไลด์ก่อนหน้า",
        "next_slide":   "สไลด์ถัดไป",
        "download_btn": "ดาวน์โหลดทุกสไลด์ (JPG)",
        "loading":      "กำลังโหลด...",
        "rendering":    "กำลังแสดงผล {i} / {n}...",
        "packaging":    "กำลังบีบอัด ZIP...",
        "done":         "ดาวน์โหลดทุกสไลด์ (JPG)",
        "error":        "ส่งออกล้มเหลว \u2014 ลองอีกครั้ง",
    },
}

# ── Fixed on-slide labels per language (not part of the script JSON) ──────────
_SLIDE_LABELS: dict[str, dict[str, str]] = {
    "en":    {"why_it_matters": "WHY IT MATTERS"},
    "zh-TW": {"why_it_matters": "為什麼重要"},
    "zh-CN": {"why_it_matters": "为什么重要"},
    "th":    {"why_it_matters": "ทำไมจึงสำคัญ"},
    "pt-BR": {"why_it_matters": "POR QUE IMPORTA"},
}


# ── Disclaimer per language ───────────────────────────────────────────────────
_DISCLAIMER_TEXT: dict[str, str] = {
    "en": (
        "CFD trading carries a high level of risk and may not be suitable for all investors. "
        "This content is for educational purposes only and does not constitute financial or investment advice. "
        "Wisuno Capital is regulated by CMA, CySEC, FSA & FSC. Trade responsibly."
    ),
    "zh-TW": (
        "差價合約交易風險極高，可能並不適合所有投資者。"
        "本內容僅供教育參考，不構成財務或投資建議。"
        "Wisuno Capital 受 CMA、CySEC、FSA 及 FSC 監管。請謹慎交易。"
    ),
    "zh-CN": (
        "差价合约交易风险极高，可能并不适合所有投资者。"
        "本内容仅供教育参考，不构成财务或投资建议。"
        "Wisuno Capital 受 CMA、CySEC、FSA 及 FSC 监管。请谨慎交易。"
    ),
    "th": (
        "การซื้อขาย CFD มีความเสี่ยงสูงและอาจไม่เหมาะสำหรับนักลงทุนทุกราย "
        "เนื้อหานี้มีวัตถุประสงค์เพื่อการศึกษาเท่านั้น ไม่ถือเป็นคำแนะนำทางการเงินหรือการลงทุน "
        "Wisuno Capital ได้รับการกำกับดูแลโดย CMA, CySEC, FSA และ FSC โปรดซื้อขายด้วยความรับผิดชอบ"
    ),
    "pt-BR": (
        "O trading de CFDs envolve um alto nível de risco e pode não ser adequado para todos os investidores. "
        "Este conteúdo tem caráter exclusivamente educacional e não constitui aconselhamento financeiro ou de investimento. "
        "A Wisuno Capital é regulamentada pela CMA, CySEC, FSA e FSC. Negocie com responsabilidade."
    ),
}

_LOGO_URI: str | None = None
_DARK_LOGO_URI: str | None = None


def _logo() -> str:
    global _LOGO_URI
    if _LOGO_URI is None:
        data = _LOGO_PATH.read_bytes()
        b64 = base64.b64encode(data).decode()
        _LOGO_URI = f"data:image/png;base64,{b64}"
    return _LOGO_URI


def _dark_logo() -> str:
    global _DARK_LOGO_URI
    if _DARK_LOGO_URI is None:
        data = _DARK_LOGO_PATH.read_bytes()
        b64 = base64.b64encode(data).decode()
        _DARK_LOGO_URI = f"data:image/png;base64,{b64}"
    return _DARK_LOGO_URI


def _e(v: object) -> str:
    return _esc.escape(str(v))


# ── Shared slide CSS (injected once into the document head) ──────────────────
_SLIDE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Urbanist:wght@400;600;700;900&family=Inter:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

.slide-inner *, .slide-inner *::before, .slide-inner *::after {
  margin: 0; padding: 0; box-sizing: border-box;
}

.slide-inner {
  width: 1080px;
  height: 1350px;
  position: relative;
  overflow: hidden;
  background: #0A0A0A;
  font-family: 'Inter', sans-serif;
  color: #FFFFFF;
  transform-origin: top left;
  flex-shrink: 0;
}

.slide-inner .logo {
  position: absolute;
  top: 180px; right: 180px;
  height: 30px; width: auto;
  object-fit: contain;
  z-index: 20;
}

.slide-inner .asset-tag {
  display: inline-block;
  font-family: 'Urbanist', sans-serif;
  font-size: 13px; font-weight: 700;
  color: #FF6700;
  letter-spacing: 3px;
  text-transform: uppercase;
  padding: 7px 16px;
  border: 1.5px solid #FF6700;
  border-radius: 3px;
}

.slide-inner .disclaimer {
  position: absolute;
  bottom: 180px; left: 180px; right: 180px;
  font-family: 'Inter', sans-serif;
  font-size: 15px; font-weight: 400;
  color: #888888;
  line-height: 1.55;
}

.slide-inner .o-line {
  width: 56px; height: 3px;
  background: #FF6700;
  border-radius: 2px;
}

/* ── Educational slide elements ─────────────────────────────── */
.slide-inner .edu-step-row {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  padding: 16px 0;
}
.slide-inner .edu-step-num {
  font-family: 'Urbanist', sans-serif;
  font-size: 28px;
  font-weight: 900;
  color: #FF6700;
  line-height: 1;
  flex-shrink: 0;
  width: 40px;
  text-align: right;
}
.slide-inner .edu-cmp-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 14px 0;
}
"""


# ── Slide body renderers (return inner HTML only, no wrapping doc) ────────────

def _render_cover(slide: dict, bg_data_uri: str | None = None, disclaimer: str = "") -> str:
    headline = _e(slide.get("headline", ""))
    sub      = _e(slide.get("subheadline", ""))
    tag      = _e(slide.get("asset_tag", ""))

    bg_css  = ""
    overlay = ""
    if bg_data_uri:
        bg_css = (
            f"background-image:url('{bg_data_uri}');"
            "background-size:cover;background-position:center;"
        )
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

    return f"""
<div class="slide-inner" style="{bg_css}">
  {overlay}
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">
  <div style="position:absolute;left:180px;right:180px;bottom:340px;z-index:20;">
    <div class="o-line" style="margin-bottom:28px;"></div>
    <h1 style="
      font-family:'Urbanist',sans-serif;
      font-size:62px; font-weight:900;
      color:#FFFFFF; line-height:1.05;
      letter-spacing:-0.5px;
      text-transform:uppercase;
      margin-bottom:22px;
    ">{headline}</h1>
    <p style="
      font-family:'Inter',sans-serif;
      font-size:21px; font-weight:400;
      color:#CCCCCC; line-height:1.45;
    ">{sub}</p>
  </div>
  <div class="disclaimer">{_e(disclaimer)}</div>
</div>"""


_DIR_ARROW = {"UP": "↑", "DOWN": "↓", "FLAT": "→"}
_DIR_COLOR = {"UP": "#FF6700", "DOWN": "#EF4444", "FLAT": "#888888"}


def _render_data_slide(slide: dict, disclaimer: str = "", light: bool = False) -> str:
    headline    = _e(slide.get("section_headline", ""))
    tag         = _e(slide.get("asset_tag", ""))
    data_points = slide.get("data_points", [])
    takeaway    = _e(slide.get("takeaway_line", ""))

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM
    row_border = _LIGHT_BORDER   if light else "rgba(255,255,255,0.07)"

    rows = ""
    for dp in data_points:
        label     = _e(dp.get("label", ""))
        value     = _e(dp.get("value", ""))
        direction = dp.get("direction", "FLAT").upper()
        arrow     = _DIR_ARROW.get(direction, "→")
        color     = _DIR_COLOR.get(direction, "#888888")
        rows += f"""
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:18px 0;border-bottom:1px solid {row_border};">
      <span style="font-family:'Inter',sans-serif;font-size:16px;font-weight:400;
                   color:{secondary};flex:1;padding-right:16px;">{label}</span>
      <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
        <span style="font-family:'Urbanist',sans-serif;font-size:26px;font-weight:700;
                     color:{primary};">{value}</span>
        <span style="font-size:22px;font-weight:700;color:{color};line-height:1;">{arrow}</span>
      </div>
    </div>"""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;">
    <h2 style="font-family:'Urbanist',sans-serif;font-size:38px;font-weight:700;
               color:{primary};line-height:1.15;margin-bottom:36px;">{headline}</h2>
    <div style="flex:1;">{rows}</div>
    <div style="margin-top:32px;padding:20px 24px;
                border-left:3px solid #FF6700;background:rgba(255,103,0,0.06);">
      <p style="font-family:'Inter',sans-serif;font-size:15px;font-weight:500;
                color:{secondary};line-height:1.55;font-style:italic;">{takeaway}</p>
    </div>
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_analysis_slide(slide: dict, slide_num: int = 0, disclaimer: str = "", light: bool = False) -> str:
    tag        = _e(slide.get("asset_tag", ""))
    paragraphs = slide.get("analysis_paragraphs", [])
    label      = f"0{slide_num}" if slide_num < 10 else str(slide_num)
    fs         = "20px" if len(paragraphs) <= 2 else "18px"

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM
    watermark = "rgba(255,103,0,0.22)" if light else "rgba(255,103,0,0.08)"

    paras = ""
    for i, p in enumerate(paragraphs):
        mt    = "0" if i == 0 else "32px"
        color = primary if i == 0 else secondary
        paras += f"""<p style="font-family:'Inter',sans-serif;font-size:{fs};font-weight:400;
                        color:{color};line-height:1.7;margin-top:{mt};">{_e(p)}</p>\n"""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:180px;right:180px;z-index:20;">
    <span style="font-family:'Urbanist',sans-serif;font-size:72px;font-weight:900;
                 color:{watermark};line-height:1;">{label}</span>
  </div>
  <div style="position:absolute;top:260px;left:180px;width:4px;bottom:340px;
              background:linear-gradient(to bottom,#FF6700 0%,rgba(255,103,0,0) 100%);
              border-radius:4px;z-index:10;"></div>
  <div style="position:absolute;top:260px;left:212px;right:180px;bottom:340px;
              display:flex;flex-direction:column;justify-content:center;">
    {paras}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_quote_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "", light: bool = False) -> str:
    tag         = _e(slide.get("asset_tag", ""))
    quote       = _e(slide.get("quote_text", ""))
    attribution = _e(slide.get("quote_attribution", ""))
    rhetorical  = slide.get("rhetorical_question")

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    dim       = _LIGHT_DIM       if light else _DIM
    watermark = "rgba(255,103,0,0.28)" if light else "rgba(255,103,0,0.12)"
    rhet_color = "#555555" if light else "#888888"

    rhetorical_html = ""
    if rhetorical:
        rhetorical_html = f"""<p style="font-family:'Inter',sans-serif;font-size:17px;
            font-style:italic;color:{rhet_color};line-height:1.55;margin-top:40px;
            max-width:760px;">{_e(rhetorical)}</p>"""

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:28px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.85;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""

    justify = "flex-start" if img_uri else "center"
    pt      = "padding-top:60px;" if img_uri else ""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:200px;left:180px;font-family:'Urbanist',sans-serif;
              font-size:200px;font-weight:900;color:{watermark};line-height:1;
              z-index:1;user-select:none;">"</div>
  <div style="position:absolute;top:180px;bottom:340px;left:0;right:0;display:flex;
              flex-direction:column;align-items:flex-start;justify-content:{justify};
              padding:0 180px;{pt}z-index:10;">
    <blockquote style="font-family:'Urbanist',sans-serif;font-size:32px;font-weight:700;
                       color:{primary};line-height:1.4;max-width:900px;flex-shrink:0;">{quote}</blockquote>
    <div style="display:flex;align-items:center;gap:16px;margin-top:36px;flex-shrink:0;">
      <div style="width:40px;height:2px;background:#FF6700;border-radius:1px;"></div>
      <span style="font-family:'Inter',sans-serif;font-size:14px;font-weight:600;
                   color:#FF6700;letter-spacing:1px;text-transform:uppercase;">{attribution}</span>
    </div>
    {rhetorical_html}
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_chart_slide(slide: dict, chart_data_uri: str | None = None, disclaimer: str = "", light: bool = False) -> str:
    tag         = _e(slide.get("asset_tag", ""))
    chart_asset = _e(slide.get("chart_asset", ""))
    caption     = _e(slide.get("chart_caption", ""))

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM
    grid_stroke = "#BBBBBB" if light else "#222"

    if chart_data_uri:
        chart_content = f"""
    <div style="width:100%;flex:1;position:relative;overflow:hidden;border-radius:4px;">
      <img src="{chart_data_uri}" style="width:100%;height:100%;object-fit:cover;
           filter:brightness(0.9) contrast(1.05);">
      <div style="position:absolute;bottom:0;left:0;right:0;height:30%;
                  background:linear-gradient(to top,rgba(10,10,10,0.6) 0%,transparent 100%);"></div>
    </div>"""
    else:
        chart_content = f"""
    <div style="width:100%;flex:1;border:1px solid rgba(255,103,0,0.2);border-radius:4px;
                background:rgba(255,103,0,0.03);display:flex;flex-direction:column;
                align-items:center;justify-content:center;position:relative;overflow:hidden;">
      <svg viewBox="0 0 900 500" style="width:90%;height:auto;opacity:0.6;">
        <defs>
          <linearGradient id="og2" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#FF6700" stop-opacity="0.3"/>
            <stop offset="100%" stop-color="#FF6700" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <line x1="0" y1="100" x2="900" y2="100" stroke="{grid_stroke}" stroke-width="1"/>
        <line x1="0" y1="200" x2="900" y2="200" stroke="{grid_stroke}" stroke-width="1"/>
        <line x1="0" y1="300" x2="900" y2="300" stroke="{grid_stroke}" stroke-width="1"/>
        <line x1="0" y1="400" x2="900" y2="400" stroke="{grid_stroke}" stroke-width="1"/>
        <path d="M0,400 C100,380 150,320 220,260 S340,160 420,130 S580,90 660,110 S800,150 900,80 L900,500 L0,500 Z"
              fill="url(#og2)"/>
        <path d="M0,400 C100,380 150,320 220,260 S340,160 420,130 S580,90 660,110 S800,150 900,80"
              fill="none" stroke="#FF6700" stroke-width="3"
              stroke-linejoin="round" stroke-linecap="round"/>
      </svg>
      <p style="font-family:'Inter',sans-serif;font-size:13px;color:#555;
                margin-top:16px;letter-spacing:1px;text-transform:uppercase;">{chart_asset}</p>
    </div>"""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;gap:24px;">
    {chart_content}
    <div style="flex-shrink:0;padding-bottom:8px;">
      <div class="o-line" style="margin-bottom:12px;"></div>
      <p style="font-family:'Inter',sans-serif;font-size:15px;font-weight:400;
                color:{secondary};line-height:1.5;">{caption}</p>
    </div>
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_cta_slide(slide: dict | None = None, language: str = "en",
                      content_type: str = "market_insight", light: bool = False) -> str:
    if content_type == "educational":
        cta_map = _CTA_CONTENT_EDUCATIONAL
    elif content_type == "promotional":
        cta_map = _CTA_CONTENT_PROMOTIONAL
    else:
        cta_map = _CTA_CONTENT
    headline, body = cta_map.get(language, cta_map["en"])
    disclaimer     = _DISCLAIMER_TEXT.get(language, _DISCLAIMER_TEXT["en"])

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM
    grid_opacity = "0.07" if light else "0.04"

    return f"""
<div class="slide-inner" style="background:{bg};">
  <svg style="position:absolute;inset:0;width:100%;height:100%;opacity:{grid_opacity};"
       viewBox="0 0 1080 1350">
    <defs>
      <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
        <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#FF6700" stroke-width="0.5"/>
      </pattern>
    </defs>
    <rect width="1080" height="1350" fill="url(#grid)"/>
  </svg>
  <div style="position:absolute;top:0;left:0;right:0;height:5px;background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;bottom:340px;left:0;right:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;padding:0 180px;
              text-align:center;z-index:10;">
    <img src="{logo_uri}" alt="Wisuno"
         style="height:44px;width:auto;margin-bottom:64px;object-fit:contain;">
    <div class="o-line" style="margin:0 auto 40px;width:80px;"></div>
    <h2 style="font-family:'Urbanist',sans-serif;font-size:52px;font-weight:900;
               color:{primary};letter-spacing:3px;text-transform:uppercase;
               margin-bottom:24px;line-height:1.1;">{_e(headline)}</h2>
    <p style="font-family:'Inter',sans-serif;font-size:20px;font-weight:400;
              color:{secondary};line-height:1.5;max-width:680px;margin-bottom:56px;">
      {_e(body)}
    </p>
    <div style="display:flex;align-items:center;gap:12px;padding:14px 32px;
                border:1.5px solid rgba(255,103,0,0.5);border-radius:4px;">
      <span style="font-family:'Urbanist',sans-serif;font-size:18px;font-weight:600;
                   color:#FF6700;letter-spacing:1px;">@wisuno</span>
    </div>
  </div>
  <div class="disclaimer" style="text-align:center;color:{dim};">{_e(disclaimer)}</div>
</div>"""


# ── Educational slide renderers ───────────────────────────────────────────────

def _render_concept_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "",
                          light: bool = False, language: str = "en") -> str:
    tag          = _e(slide.get("asset_tag", ""))
    term         = _e(slide.get("term", ""))
    definition   = _e(slide.get("definition", ""))
    why_matters  = _e(slide.get("why_it_matters", ""))
    why_label    = _SLIDE_LABELS.get(language, _SLIDE_LABELS["en"])["why_it_matters"]

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:28px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.85;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""

    justify = "" if img_uri else "justify-content:center;"

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:290px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;{justify}gap:0;">
    <div class="o-line" style="margin-bottom:20px;flex-shrink:0;"></div>
    <h2 style="font-family:'Urbanist',sans-serif;font-size:44px;font-weight:900;
               color:#FF6700;line-height:1.05;text-transform:uppercase;
               letter-spacing:1px;margin-bottom:20px;flex-shrink:0;">{term}</h2>
    <div style="width:100%;height:1px;background:rgba(255,103,0,0.25);
                margin-bottom:28px;flex-shrink:0;"></div>
    <p style="font-family:'Inter',sans-serif;font-size:18px;font-weight:400;
              color:{primary};line-height:1.65;margin-bottom:36px;flex-shrink:0;">{definition}</p>
    <div style="flex-shrink:0;">
      <span style="font-family:'Inter',sans-serif;font-size:10px;font-weight:600;
                   color:#FF6700;letter-spacing:3px;text-transform:uppercase;
                   display:block;margin-bottom:10px;">{why_label}</span>
      <p style="font-family:'Inter',sans-serif;font-size:16px;font-weight:400;
                color:{secondary};line-height:1.6;">{why_matters}</p>
    </div>
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_steps_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "", light: bool = False) -> str:
    tag      = _e(slide.get("asset_tag", ""))
    headline = _e(slide.get("headline", ""))
    steps    = slide.get("steps", [])
    fs       = "14px" if len(steps) >= 5 else "16px"

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    dim       = _LIGHT_DIM       if light else _DIM
    step_border_color = "rgba(0,0,0,0.08)" if light else "rgba(255,255,255,0.06)"

    rows = ""
    for i, step in enumerate(steps):
        text   = _e(step.get("text", step) if isinstance(step, dict) else step)
        num    = str(i + 1).zfill(2)
        border = f"border-bottom:1px solid {step_border_color};" if i < len(steps) - 1 else ""
        rows += f"""
    <div class="edu-step-row" style="{border}">
      <span class="edu-step-num">{num}</span>
      <p style="font-family:'Inter',sans-serif;font-size:{fs};font-weight:400;
                color:{primary};line-height:1.55;flex:1;padding-top:4px;">{text}</p>
    </div>"""

    rows_style = "flex-shrink:0;" if img_uri else "flex:1;overflow:hidden;"

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:24px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.85;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;">
    <h2 style="font-family:'Urbanist',sans-serif;font-size:36px;font-weight:700;
               color:{primary};line-height:1.15;margin-bottom:28px;flex-shrink:0;">{headline}</h2>
    <div class="o-line" style="margin-bottom:24px;flex-shrink:0;"></div>
    <div style="{rows_style}">{rows}</div>
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_comparison_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "", light: bool = False) -> str:
    tag       = _e(slide.get("asset_tag", ""))
    headline  = _e(slide.get("headline", ""))
    col_a     = _e(slide.get("col_a_label", "A"))
    col_b     = _e(slide.get("col_b_label", "B"))
    rows_data = slide.get("rows", [])

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM
    row_border_color = "rgba(0,0,0,0.08)" if light else "rgba(255,255,255,0.06)"
    col_divider = "rgba(0,0,0,0.12)" if light else "rgba(255,255,255,0.08)"

    rows_html = ""
    for i, row in enumerate(rows_data):
        cell_a = _e(row.get("col_a", ""))
        cell_b = _e(row.get("col_b", ""))
        border = f"border-bottom:1px solid {row_border_color};" if i < len(rows_data) - 1 else ""
        rows_html += f"""
    <div class="edu-cmp-row" style="{border}">
      <span style="font-family:'Inter',sans-serif;font-size:16px;
                   color:{primary};line-height:1.5;padding-right:12px;">{cell_a}</span>
      <span style="font-family:'Inter',sans-serif;font-size:16px;
                   color:{secondary};line-height:1.5;padding-left:12px;
                   border-left:1px solid {col_divider};">{cell_b}</span>
    </div>"""

    rows_style = "flex-shrink:0;" if img_uri else "flex:1;overflow:hidden;"

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:24px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.85;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;">
    <h2 style="font-family:'Urbanist',sans-serif;font-size:36px;font-weight:700;
               color:{primary};line-height:1.15;margin-bottom:24px;flex-shrink:0;">{headline}</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;margin-bottom:12px;flex-shrink:0;">
      <span style="font-family:'Urbanist',sans-serif;font-size:13px;font-weight:700;
                   color:#FF6700;letter-spacing:2px;text-transform:uppercase;">{col_a}</span>
      <span style="font-family:'Urbanist',sans-serif;font-size:13px;font-weight:700;
                   color:{secondary};letter-spacing:2px;text-transform:uppercase;
                   padding-left:12px;border-left:1px solid {col_divider};">{col_b}</span>
    </div>
    <div style="width:100%;height:1px;background:rgba(255,103,0,0.3);margin-bottom:4px;flex-shrink:0;"></div>
    <div style="{rows_style}">{rows_html}</div>
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


def _render_example_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "", light: bool = False) -> str:
    tag             = _e(slide.get("asset_tag", ""))
    headline        = _e(slide.get("headline", ""))
    scenario        = _e(slide.get("scenario", ""))
    featured_number = _e(slide.get("featured_number", ""))
    number_label    = _e(slide.get("number_label", ""))
    narrative       = _e(slide.get("narrative", ""))
    outcome         = slide.get("outcome")

    bg        = _CLOUD_MIST if light else _BG
    logo_uri  = _dark_logo() if light else _logo()
    primary   = _LIGHT_PRIMARY   if light else _WHITE
    secondary = _LIGHT_SECONDARY if light else _GRAY
    dim       = _LIGHT_DIM       if light else _DIM

    outcome_html = ""
    if outcome:
        outcome_html = f"""
    <p style="font-family:'Inter',sans-serif;font-size:15px;font-weight:400;
              color:{secondary};font-style:italic;line-height:1.5;margin-top:20px;flex-shrink:0;">{_e(outcome)}</p>"""

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:28px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.85;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""

    justify = "" if img_uri else "justify-content:center;"

    return f"""
<div class="slide-inner" style="background:{bg};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{logo_uri}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;{justify}">
    <h2 style="font-family:'Urbanist',sans-serif;font-size:36px;font-weight:700;
               color:{primary};line-height:1.15;margin-bottom:12px;flex-shrink:0;">{headline}</h2>
    <p style="font-family:'Inter',sans-serif;font-size:17px;font-style:italic;
              color:{secondary};line-height:1.5;margin-bottom:36px;flex-shrink:0;">{scenario}</p>
    <span style="font-family:'Urbanist',sans-serif;font-size:52px;font-weight:900;
                 color:#FF6700;line-height:1;display:block;margin-bottom:8px;flex-shrink:0;">{featured_number}</span>
    <span style="font-family:'Inter',sans-serif;font-size:12px;font-weight:500;
                 color:{dim};letter-spacing:2px;text-transform:uppercase;
                 display:block;margin-bottom:24px;flex-shrink:0;">{number_label}</span>
    <div style="width:100%;height:1px;background:rgba(255,103,0,0.25);margin-bottom:24px;flex-shrink:0;"></div>
    <p style="font-family:'Inter',sans-serif;font-size:16px;font-weight:400;
              color:{primary};line-height:1.65;flex-shrink:0;">{narrative}</p>
    {outcome_html}
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{dim};">{_e(disclaimer)}</div>
</div>"""


# ── Promotional slide renderers (always dark brand theme) ─────────────────────

def _render_value_prop_slide(slide: dict, disclaimer: str = "") -> str:
    """Promo: eyebrow + headline + three value pillars (title / detail)."""
    tag      = _e(slide.get("asset_tag", ""))
    eyebrow  = _e(slide.get("section_headline", ""))
    headline = _e(slide.get("headline", ""))
    pillars  = slide.get("pillars", []) or []

    rows = ""
    for i, p in enumerate(pillars[:3]):
        title  = _e(p.get("title", "") if isinstance(p, dict) else str(p))
        detail = _e(p.get("detail", "") if isinstance(p, dict) else "")
        border = "border-top:1px solid rgba(255,255,255,0.08);" if i > 0 else ""
        rows += f"""
    <div style="display:flex;gap:24px;align-items:flex-start;padding:22px 0;{border}flex-shrink:0;">
      <span style="font-family:'Urbanist',sans-serif;font-size:22px;font-weight:900;
                   color:#FF6700;line-height:1;min-width:36px;">{str(i + 1).zfill(2)}</span>
      <div>
        <h3 style="font-family:'Urbanist',sans-serif;font-size:22px;font-weight:700;
                   color:{_WHITE};line-height:1.15;margin-bottom:6px;">{title}</h3>
        <p style="font-family:'Inter',sans-serif;font-size:15px;font-weight:400;
                  color:{_GRAY};line-height:1.55;">{detail}</p>
      </div>
    </div>"""

    eyebrow_html = ""
    if eyebrow:
        eyebrow_html = f"""<span style="font-family:'Inter',sans-serif;font-size:11px;font-weight:600;
                 color:#FF6700;letter-spacing:3px;text-transform:uppercase;
                 display:block;margin-bottom:14px;flex-shrink:0;">{eyebrow}</span>"""

    return f"""
<div class="slide-inner" style="background:{_BG};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;justify-content:center;">
    {eyebrow_html}
    <h2 style="font-family:'Urbanist',sans-serif;font-size:42px;font-weight:900;
               color:{_WHITE};line-height:1.08;text-transform:uppercase;letter-spacing:1px;
               margin-bottom:18px;flex-shrink:0;">{headline}</h2>
    <div class="o-line" style="margin-bottom:8px;flex-shrink:0;"></div>
    <div style="flex-shrink:0;">{rows}</div>
  </div>
  <div class="disclaimer" style="color:{_DIM};">{_e(disclaimer)}</div>
</div>"""


def _render_benefits_slide(slide: dict, disclaimer: str = "") -> str:
    """Promo: headline + a list of benefits with orange check markers."""
    tag      = _e(slide.get("asset_tag", ""))
    headline = _e(slide.get("headline", ""))
    benefits = slide.get("benefits", []) or []
    fs       = "18px" if len(benefits) <= 3 else "16px"

    rows = ""
    for b in benefits[:5]:
        text = _e(b.get("text", b) if isinstance(b, dict) else b)
        rows += f"""
    <div style="display:flex;gap:18px;align-items:flex-start;padding:18px 0;
                border-bottom:1px solid rgba(255,255,255,0.06);flex-shrink:0;">
      <span style="color:#FF6700;font-size:20px;font-weight:900;line-height:1.4;flex-shrink:0;">&#10003;</span>
      <p style="font-family:'Inter',sans-serif;font-size:{fs};font-weight:400;
                color:{_WHITE};line-height:1.5;flex:1;">{text}</p>
    </div>"""

    return f"""
<div class="slide-inner" style="background:{_BG};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">
  <div style="position:absolute;top:260px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;justify-content:center;">
    <h2 style="font-family:'Urbanist',sans-serif;font-size:38px;font-weight:900;
               color:{_WHITE};line-height:1.1;text-transform:uppercase;letter-spacing:1px;
               margin-bottom:24px;flex-shrink:0;">{headline}</h2>
    <div class="o-line" style="margin-bottom:8px;flex-shrink:0;"></div>
    <div style="flex-shrink:0;">{rows}</div>
  </div>
  <div class="disclaimer" style="color:{_DIM};">{_e(disclaimer)}</div>
</div>"""


def _render_feature_slide(slide: dict, img_uri: str | None = None, disclaimer: str = "") -> str:
    """Promo: single feature spotlight (name + detail) with optional hero image."""
    tag      = _e(slide.get("asset_tag", ""))
    name     = _e(slide.get("feature_name", slide.get("headline", "")))
    detail   = _e(slide.get("feature_detail", ""))

    img_panel = ""
    if img_uri:
        img_panel = f"""
    <div style="width:100%;flex:1;min-height:0;border-radius:6px;overflow:hidden;
                margin-top:32px;position:relative;">
      <img src="{img_uri}" style="width:100%;height:100%;object-fit:cover;
           opacity:0.9;display:block;">
      <div style="position:absolute;bottom:0;left:0;right:0;height:35%;
                  background:linear-gradient(to top,rgba(10,10,10,0.55) 0%,transparent 100%);"></div>
    </div>"""
    justify = "" if img_uri else "justify-content:center;"

    return f"""
<div class="slide-inner" style="background:{_BG};">
  <div style="position:absolute;top:0;left:0;right:0;height:5px;
              background:#FF6700;z-index:20;"></div>
  <div style="position:absolute;top:180px;left:180px;z-index:20;">
    <span class="asset-tag">{tag}</span>
  </div>
  <img class="logo" src="{_logo()}" alt="Wisuno">
  <div style="position:absolute;top:290px;left:180px;right:180px;bottom:340px;
              display:flex;flex-direction:column;{justify}gap:0;">
    <div class="o-line" style="margin-bottom:20px;flex-shrink:0;"></div>
    <h2 style="font-family:'Urbanist',sans-serif;font-size:46px;font-weight:900;
               color:#FF6700;line-height:1.05;text-transform:uppercase;letter-spacing:1px;
               margin-bottom:20px;flex-shrink:0;">{name}</h2>
    <p style="font-family:'Inter',sans-serif;font-size:19px;font-weight:400;
              color:{_GRAY};line-height:1.6;flex-shrink:0;">{detail}</p>
    {img_panel}
  </div>
  <div class="disclaimer" style="color:{_DIM};">{_e(disclaimer)}</div>
</div>"""


# ── Dispatch ─────────────────────────────────────────────────────────────────

def _render_slide(
    slide: dict,
    slide_images: dict,
    analysis_counter: list,
    language: str = "en",
    content_type: str = "market_insight",
) -> str | None:
    stype = slide.get("type", "")
    snum  = slide.get("slide_number", 0)
    disc  = _DISCLAIMER_TEXT.get(language, _DISCLAIMER_TEXT["en"])

    # Cloud Mist light theme applies only to English non-cover slides
    light = (language == "en" and stype != "cover")

    if stype == "cover":
        return _render_cover(slide, bg_data_uri=slide_images.get(snum), disclaimer=disc)
    elif stype == "data_slide":
        return _render_data_slide(slide, disclaimer=disc, light=light)
    elif stype == "analysis_slide":
        analysis_counter[0] += 1
        return _render_analysis_slide(slide, slide_num=analysis_counter[0], disclaimer=disc, light=light)
    elif stype == "quote_slide":
        return _render_quote_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc, light=light)
    elif stype == "chart_slide":
        return _render_chart_slide(slide, chart_data_uri=slide_images.get(snum), disclaimer=disc, light=light)
    elif stype == "cta_slide":
        return _render_cta_slide(slide, language=language, content_type=content_type, light=light)
    elif stype == "concept_slide":
        return _render_concept_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc, light=light, language=language)
    elif stype == "steps_slide":
        return _render_steps_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc, light=light)
    elif stype == "comparison_slide":
        return _render_comparison_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc, light=light)
    elif stype == "example_slide":
        return _render_example_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc, light=light)
    # Promotional slide types — always rendered on the dark brand theme (no light variant).
    elif stype == "value_prop_slide":
        return _render_value_prop_slide(slide, disclaimer=disc)
    elif stype == "benefits_slide":
        return _render_benefits_slide(slide, disclaimer=disc)
    elif stype == "feature_slide":
        return _render_feature_slide(slide, img_uri=slide_images.get(snum), disclaimer=disc)
    return None


# ── Main assembler ────────────────────────────────────────────────────────────

def build_swipeable_html(
    script: dict,
    slide_images: dict | None = None,
    language: str = "en",
) -> str:
    """
    Build a single swipeable HTML file from a script dict.

    Args:
        script:        The carousel script dict (same schema as script.json).
        slide_images:  Optional mapping of slide_number → data URI for bg images.
        language:      One of 'en', 'zh-TW', 'zh-CN', 'th'. Controls fonts,
                       disclaimer text, and CTA copy.

    Returns:
        Complete HTML string.
    """
    if slide_images is None:
        slide_images = {}

    slides_data  = script.get("slides", [])
    total        = len(slides_data)
    title        = _e(script.get("title", "Wisuno Carousel"))
    analysis_ctr = [0]
    ui           = _UI_STRINGS.get(language, _UI_STRINGS["en"])
    content_type = script.get("content_type", "market_insight")

    # Build slide divs
    slide_divs = ""
    for slide in slides_data:
        inner = _render_slide(slide, slide_images, analysis_ctr, language=language,
                              content_type=content_type)
        if inner is None:
            continue
        slide_divs += f'<div class="slide-frame">{inner}</div>\n'

    # Dot buttons
    dots_html = ""
    for i in range(total):
        dots_html += (
            f'<button class="dot{" active" if i == 0 else ""}" '
            f'onclick="goTo({i})" aria-label="{ui["slide_label"]} {i+1}"></button>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="{ui['html_lang']}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
{_SLIDE_CSS}

    /* ── Layout chrome ───────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; }}

    html, body {{
      margin: 0; padding: 0;
      width: 100%; height: 100%;
      background: #111111;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      touch-action: none;
    }}

    .carousel-shell {{
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}

    /* The visible window */
    #viewport {{
      position: relative;
      overflow: hidden;
      cursor: grab;
    }}
    #viewport:active {{ cursor: grabbing; }}

    /* Sliding track */
    #track {{
      display: flex;
      height: 100%;
      transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
      will-change: transform;
    }}

    /* Each frame matches the viewport size */
    .slide-frame {{
      flex-shrink: 0;
      overflow: hidden;
      display: flex;
      align-items: flex-start;
      justify-content: flex-start;
    }}

    /* ── Navigation arrows ───────────────────────────────── */
    .nav-arrow {{
      position: absolute;
      top: 50%; transform: translateY(-50%);
      background: rgba(255,103,0,0.12);
      border: 1px solid rgba(255,103,0,0.35);
      color: #FF6700;
      width: 40px; height: 40px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer; z-index: 200;
      font-size: 17px; line-height: 1;
      transition: background 0.2s;
      outline: none;
      padding: 0;
    }}
    .nav-arrow:hover {{ background: rgba(255,103,0,0.28); }}
    #btn-prev {{ right: calc(100% + 14px); }}
    #btn-next {{ left:  calc(100% + 14px); }}

    /* ── Dots ────────────────────────────────────────────── */
    .dots-row {{
      display: flex;
      gap: 8px;
      margin-top: 14px;
    }}

    .dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #333;
      border: none;
      cursor: pointer;
      padding: 0;
      transition: background 0.2s, transform 0.2s;
    }}
    .dot.active {{
      background: #FF6700;
      transform: scale(1.4);
    }}

    /* ── Slide counter ───────────────────────────────────── */
    #counter {{
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      color: #555;
      margin-top: 8px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}

    /* ── Download button ─────────────────────────────────── */
    #btn-download {{
      margin-top: 16px;
      padding: 10px 28px;
      background: transparent;
      border: 1.5px solid rgba(255,103,0,0.45);
      border-radius: 4px;
      color: #FF6700;
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s;
      outline: none;
    }}
    #btn-download:hover:not(:disabled) {{
      background: rgba(255,103,0,0.1);
      border-color: rgba(255,103,0,0.8);
    }}
    #btn-download:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
  </style>
</head>
<body>
  <div class="carousel-shell">
    <!-- Arrows sit outside the viewport -->
    <button class="nav-arrow" id="btn-prev" aria-label="{ui['prev_slide']}">&#8592;</button>
    <button class="nav-arrow" id="btn-next" aria-label="{ui['next_slide']}">&#8594;</button>

    <!-- Viewport -->
    <div id="viewport">
      <div id="track">
        {slide_divs}
      </div>
    </div>

    <!-- Dots -->
    <div class="dots-row" id="dots-row">
      {dots_html}
    </div>

    <!-- Counter -->
    <div id="counter">1 / {total}</div>

    <!-- Download -->
    <button id="btn-download" onclick="downloadAllSlides()">
      <span id="download-label">{ui['download_btn']}</span>
    </button>
  </div>

  <script>
    const TOTAL   = {total};
    let current   = 0;
    let scale     = 1;

    const viewport = document.getElementById('viewport');
    const track    = document.getElementById('track');
    const counter  = document.getElementById('counter');
    const dotsRow  = document.getElementById('dots-row');
    const dots     = Array.from(dotsRow.querySelectorAll('.dot'));
    const frames   = Array.from(track.querySelectorAll('.slide-frame'));
    const inners   = Array.from(track.querySelectorAll('.slide-inner'));

    // ── Responsive sizing ─────────────────────────────────────────────────
    function resize() {{
      // Available area: full screen minus bottom chrome (dots + counter + button ~120px)
      const vw    = window.innerWidth;
      const vh    = window.innerHeight - 120;
      const sxFit = vw  / 1080;
      const syFit = vh  / 1350;
      scale = Math.min(sxFit, syFit, 1);   // never upscale

      const vpW = Math.round(1080 * scale);
      const vpH = Math.round(1350 * scale);

      viewport.style.width  = vpW + 'px';
      viewport.style.height = vpH + 'px';

      frames.forEach(f => {{
        f.style.width  = vpW + 'px';
        f.style.height = vpH + 'px';
      }});

      inners.forEach(s => {{
        s.style.transform = `scale(${{scale}})`;
      }});

      // Re-position track without animation
      track.style.transition = 'none';
      track.style.transform  = `translateX(${{-current * vpW}}px)`;
      requestAnimationFrame(() => {{
        track.style.transition = 'transform 0.35s cubic-bezier(0.4,0,0.2,1)';
      }});
    }}

    // ── Navigation ────────────────────────────────────────────────────────
    function goTo(index) {{
      current = Math.max(0, Math.min(TOTAL - 1, index));
      const vpW = viewport.offsetWidth;
      track.style.transform = `translateX(${{-current * vpW}}px)`;
      dots.forEach((d, i) => d.classList.toggle('active', i === current));
      counter.textContent = `${{current + 1}} / ${{TOTAL}}`;
    }}

    document.getElementById('btn-prev').addEventListener('click', () => goTo(current - 1));
    document.getElementById('btn-next').addEventListener('click', () => goTo(current + 1));

    // Keyboard
    document.addEventListener('keydown', e => {{
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {{ e.preventDefault(); goTo(current + 1); }}
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   {{ e.preventDefault(); goTo(current - 1); }}
    }});

    // ── Pointer/touch swipe ───────────────────────────────────────────────
    let startX = 0;
    let startY = 0;
    let swiping = false;
    const SWIPE_THRESHOLD = 40;

    viewport.addEventListener('pointerdown', e => {{
      startX  = e.clientX;
      startY  = e.clientY;
      swiping = true;
      viewport.setPointerCapture(e.pointerId);
    }});

    viewport.addEventListener('pointermove', e => {{
      if (!swiping) return;
      // If vertical scroll is dominant, cancel
      const dx = Math.abs(e.clientX - startX);
      const dy = Math.abs(e.clientY - startY);
      if (dy > dx && dy > 10) {{ swiping = false; }}
    }});

    viewport.addEventListener('pointerup', e => {{
      if (!swiping) return;
      swiping = false;
      const diff = e.clientX - startX;
      if (Math.abs(diff) >= SWIPE_THRESHOLD) {{
        goTo(diff < 0 ? current + 1 : current - 1);
      }}
    }});

    viewport.addEventListener('pointercancel', () => {{ swiping = false; }});

    // Prevent context menu on long press (mobile)
    viewport.addEventListener('contextmenu', e => e.preventDefault());

    // ── JPG export ───────────────────────────────────────────────────────
    function loadScript(src) {{
      return new Promise((res, rej) => {{
        const s = document.createElement('script');
        s.src = src; s.onload = res;
        s.onerror = () => rej(new Error('Failed to load: ' + src));
        document.head.appendChild(s);
      }});
    }}

    async function downloadAllSlides() {{
      const btn   = document.getElementById('btn-download');
      const label = document.getElementById('download-label');
      btn.disabled = true;

      try {{
        label.textContent = '{_e(ui["loading"])}';
        if (!window.html2canvas) {{
          await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
        }}
        if (!window.JSZip) {{
          await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js');
        }}

        // Ensure fonts are fully rendered
        await document.fonts.ready;

        // Off-screen container at native canvas size
        const captureEl = document.createElement('div');
        Object.assign(captureEl.style, {{
          position: 'fixed', top: '-99999px', left: '0',
          width: '1080px', height: '1350px', overflow: 'hidden',
          background: '#0A0A0A',
        }});
        document.body.appendChild(captureEl);

        const zip       = new JSZip();
        const allInners = Array.from(document.querySelectorAll('.slide-inner'));

        for (let i = 0; i < allInners.length; i++) {{
          label.textContent = `{_e(ui["rendering"].split("{i}")[0])}${{i + 1}} / ${{allInners.length}}{_e(ui["rendering"].split("{n}")[-1])}`;

          // Clone at native size — no scale transform
          const clone = allInners[i].cloneNode(true);
          clone.style.transform = 'none';
          clone.style.position  = 'absolute';
          clone.style.top  = '0';
          clone.style.left = '0';
          captureEl.innerHTML = '';
          captureEl.appendChild(clone);

          // Brief settle so images/fonts paint inside the clone
          await new Promise(r => setTimeout(r, 120));

          const canvas = await html2canvas(captureEl, {{
            width:           1080,
            height:          1350,
            scale:           2,          // 2160×2700 output → crisp JPG
            useCORS:         true,
            allowTaint:      true,
            logging:         false,
            backgroundColor: '#0A0A0A',
          }});

          const b64 = canvas.toDataURL('image/jpeg', 0.93).split(',')[1];
          zip.file(`wisuno_slide_${{String(i + 1).padStart(2, '0')}}.jpg`, b64, {{ base64: true }});
        }}

        document.body.removeChild(captureEl);

        label.textContent = '{_e(ui["packaging"])}';
        const blob = await zip.generateAsync({{ type: 'blob', compression: 'STORE' }});

        const a = document.createElement('a');
        a.href     = URL.createObjectURL(blob);
        a.download = 'wisuno_carousel.zip';
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 10000);

        label.textContent = '{_e(ui["done"])}';
      }} catch (err) {{
        console.error('Export error:', err);
        label.textContent = '{_e(ui["error"])}';
      }} finally {{
        btn.disabled = false;
      }}
    }}

    // ── Init ─────────────────────────────────────────────────────────────
    window.addEventListener('resize', resize);
    resize();
  </script>
</body>
</html>"""

    # ── Language font substitution ────────────────────────────────────────────
    if language != "en":
        eng      = _FONT_CONFIGS["en"]
        lang_cfg = _FONT_CONFIGS.get(language, eng)
        html = html.replace(eng["google_fonts"], lang_cfg["google_fonts"])
        html = html.replace("'Urbanist'",        lang_cfg["heading"])
        html = html.replace("'Inter'",           lang_cfg["body"])

    return html


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import time
    from image_generator import bytes_to_data_uri, generate_background_image, generate_chart_image

    parser = argparse.ArgumentParser(description="Build a swipeable carousel HTML from script.json")
    parser.add_argument("--script", type=Path, required=True, help="Path to script.json")
    parser.add_argument("--no-images", action="store_true", help="Skip Gemini image generation")
    args = parser.parse_args()

    script_path: Path = args.script
    if not script_path.exists():
        print(f"Error: {script_path} not found.", file=sys.stderr)
        sys.exit(1)

    script = json.loads(script_path.read_text(encoding="utf-8"))
    output_dir  = script_path.parent
    images_dir  = output_dir / "images"
    carousel_out = output_dir / "carousel.html"

    slide_images: dict[int, str] = {}

    if not args.no_images:
        print("Generating Gemini images…")
        for slide in script.get("slides", []):
            stype = slide.get("type", "")
            snum  = slide.get("slide_number", 0)

            if slide.get("background_image_description"):
                desc     = slide["background_image_description"]
                img_name = "cover_bg.jpg" if stype == "cover" else f"slide_{snum}_bg.jpg"
                img_path = images_dir / img_name
                label    = "Cover bg" if stype == "cover" else f"Slide {snum} bg"
                print(f"  → {label}: {desc[:60]}…")
                try:
                    img_bytes = generate_background_image(desc, img_path)
                    slide_images[snum] = bytes_to_data_uri(img_bytes)
                except Exception as exc:
                    print(f"  ⚠ {label} image failed: {exc}")
                time.sleep(1)

            elif stype == "chart_slide":
                chart_asset = slide.get("chart_asset", "price action")
                chart_type  = slide.get("chart_type", "line_chart")
                print(f"  → Chart: {chart_asset}")
                img_path = images_dir / f"chart_{snum}.jpg"
                try:
                    img_bytes = generate_chart_image(chart_asset, chart_type, img_path)
                    slide_images[snum] = bytes_to_data_uri(img_bytes)
                except Exception as exc:
                    print(f"  ⚠ Chart image failed: {exc}")
                time.sleep(1)

    print("Rendering swipeable HTML…")
    html = build_swipeable_html(script, slide_images)
    carousel_out.write_text(html, encoding="utf-8")
    print(f"\nDone → {carousel_out}")


if __name__ == "__main__":
    main()
