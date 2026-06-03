"""
studio/backend/helpers/build_overlays.py
==========================================
Generates all HyperFrames HTML overlay compositions and renders them.

Functions:
    build_caption_overlay(master_ass, edit_dir, edit_duration_s) -> Path
    build_graphic_slides(packed_md, transcript_json, ranges, edit_dir) -> list[dict]
    build_disclaimer_overlay(edit_dir, edit_duration_s) -> Path
    build_outro(edit_dir) -> Path

All renders use hf_render.render_hyperframes() which shells through cmd.exe.
"""
from __future__ import annotations
import json
import re
import os
from pathlib import Path


# ── Brand constants ────────────────────────────────────────────────────────────
ORANGE = "#F56A21"
BG     = "#F5F5F5"
CARD   = "#FFFFFF"
TEXT   = "#1A1A1A"
BODY   = "#333333"
BORDER = "#E0E0E0"


# ── Logo ───────────────────────────────────────────────────────────────────────
def _logo_dataurl() -> str:
    """Read the pre-encoded base64 logo from helpers/logo_b64.txt."""
    b64_path = Path(__file__).parent / "logo_b64.txt"
    if b64_path.exists():
        return "data:image/png;base64," + b64_path.read_text(encoding="utf-8").strip()
    return ""  # fallback: empty src


# ── CAPTION OVERLAY (transparent MOV) ─────────────────────────────────────────

def build_caption_overlay(
    master_ass: Path,
    edit_dir: Path,
    edit_duration_s: float,
) -> Path:
    """
    Parse master.ass → build HyperFrames HTML caption overlay → render overlay.mov
    Returns path to the rendered overlay.mov
    """
    from helpers.hf_render import render_hyperframes

    slot_dir = edit_dir / "overlays" / "captions"
    slot_dir.mkdir(parents=True, exist_ok=True)
    out_path = slot_dir / "overlay.mov"

    # Parse ASS Dialogue lines
    captions = _parse_ass_captions(master_ass)

    # Generate the HTML
    html = _build_caption_html(captions, edit_duration_s)
    (slot_dir / "index.html").write_text(html, encoding="utf-8")

    render_hyperframes(slot_dir, out_path, fmt="mov")
    return out_path


def _parse_ass_captions(ass_path: Path) -> list[dict]:
    """Parse ASS Dialogue lines → list of {start, end, words:[{text,dur_cs}]}"""
    captions = []
    for line in ass_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        # Dialogue: 0,H:MM:SS.cc,H:MM:SS.cc,Default,,0,0,0,,{text}
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start = _parse_ts(parts[1])
        end   = _parse_ts(parts[2])
        raw   = parts[9]

        # Extract {\\kN} / {\\kfN}word tokens
        tokens = re.findall(r"\{\\k[f]?(\d+)\}([^{]*)", raw)
        words = [{"text": t.strip(), "dur_cs": int(d)} for d, t in tokens if t.strip()]
        if words:
            captions.append({"start": start, "end": end, "words": words})
    return captions


def _parse_ts(ts: str) -> float:
    """H:MM:SS.cc → seconds"""
    ts = ts.strip()
    h, m, rest = ts.split(":")
    s, cs = rest.split(".")
    return int(h)*3600 + int(m)*60 + int(s) + int(cs)/100


def _build_caption_html(captions: list[dict], duration: float) -> str:
    # Build div elements
    cap_divs = []
    for i, cap in enumerate(captions):
        word_spans = "".join(
            f'<span class="w" id="c{i}w{j}">{w["text"]}</span>'
            for j, w in enumerate(cap["words"])
        )
        cap_divs.append(
            f'<div class="cap" id="cap{i}"><div class="cap-box">{word_spans}</div></div>'
        )

    # Build GSAP timeline JS
    tl_lines = []
    for i, cap in enumerate(captions):
        t0 = cap["start"]
        t1 = cap["end"]
        tl_lines.append(f'  tl.set("#cap{i}", {{opacity:1}}, {t0:.3f});')
        # Word highlights
        cursor = t0
        for j, w in enumerate(cap["words"]):
            word_t = cursor
            tl_lines.append(f'  tl.set("#c{i}w{j}", {{color:"{ORANGE}"}}, {word_t:.3f});')
            if j > 0:
                tl_lines.append(f'  tl.set("#c{i}w{j-1}", {{color:"{TEXT}"}}, {word_t:.3f});')
            cursor += w["dur_cs"] / 100
        tl_lines.append(f'  tl.set("#cap{i}", {{opacity:0}}, {t1:.3f});')

    caps_html = "\n".join(cap_divs)
    tl_js = "\n".join(tl_lines)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:transparent; width:1080px; height:1920px; overflow:hidden;
       font-family:'Inter','Arial',sans-serif; }}
.cap {{ position:absolute; bottom:390px; left:50px; right:50px;
        text-align:center; opacity:0; }}
.cap-box {{ display:inline-block; background:{CARD}; border-radius:10px;
            padding:14px 28px; max-width:100%; word-break:break-word; }}
.w {{ font-size:52px; font-weight:900; text-transform:uppercase;
      letter-spacing:1px; color:{TEXT}; display:inline; }}
.w + .w::before {{ content:' '; }}
</style>
</head>
<body>
<div id="stage"
     data-composition-id="captions"
     data-width="1080" data-height="1920" data-fps="30"
     data-start="0" data-duration="{duration:.2f}">
{caps_html}
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{tl_js}
window.__timelines["captions"] = tl;
</script>
</body>
</html>"""


# ── GRAPHIC SLIDES (3 × opaque MP4) ───────────────────────────────────────────

def build_graphic_slides(
    packed_md: str,
    transcript_json: Path,
    ranges: list[dict],
    edit_dir: Path,
    anthropic_api_key: str,
    anthropic_model: str,
) -> list[dict]:
    """
    Ask Claude to extract 3 topic slides from the transcript,
    then generate + render each as a 4-second HyperFrames MP4.
    Returns list of overlay dicts: [{file, start_in_output, duration}]
    """
    import anthropic
    from helpers.hf_render import render_hyperframes

    # Calculate output timestamps for words in transcript
    word_output_times = _build_word_output_times(transcript_json, ranges)

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    resp = client.messages.create(
        model=anthropic_model,
        max_tokens=1024,
        system="You are a JSON API. Return only a JSON array, no prose.",
        messages=[{"role": "user", "content": f"""Analyze this market video transcript.
Extract exactly 3 key data points suitable for graphic slides.
Each slide should highlight a specific financial stat or market move.

TRANSCRIPT:
{packed_md}

For each slide, choose which design variant fits best:
- Variant A (big_stat): one large number/percentage (e.g. "$110", "+3.2%")
- Variant B (bullets): 3 short bullet points (e.g. "Up 2.1%", "Near ATH", "Watch earnings")

Identify the EXACT PHRASE the speaker says that introduces this topic,
so we can find the output timestamp.

Return JSON array:
[{{
  "topic_keyword": "AI Stocks",
  "trigger_phrase": "AI stocks are surging",
  "headline_line1": "AI STOCKS",
  "headline_line2": "SURGING",
  "headline_highlight": "SURGING",
  "subtitle": "Tech sector leads gains with <span class=\\"hl\\">+3.2%</span> rally",
  "variant": "big_stat",
  "stat_num": "+3.2%",
  "stat_unit": "DAILY GAIN",
  "stat_note": "Nasdaq extends winning streak to 5 sessions",
  "caption_main": "AI STOCKS",
  "caption_hl": "RALLY",
  "bullets": null
}}]

For Variant B use:
  "variant": "bullets",
  "bullets": ["UP 2.1%", "NEAR ATH", "WATCH EARNINGS"],
  "stat_num": null, "stat_unit": null, "stat_note": null
"""}],
    )

    raw = resp.content[0].text.strip()
    # Extract JSON array
    m = re.search(r"\[\s*\{", raw)
    slides_data = []
    if m:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(raw[m.start():], m.start()):
            if esc:    esc = False; continue
            if ch == "\\" and in_str: esc = True; continue
            if ch == '"': in_str = not in_str; continue
            if in_str: continue
            if ch == "[": depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    slides_data = json.loads(raw[m.start():i+1])
                    break

    overlays = []
    for idx, sd in enumerate(slides_data[:3]):
        # Find output timestamp for this slide's trigger phrase
        trigger = (sd.get("trigger_phrase") or sd.get("topic_keyword", "")).lower()
        start_in_output = _find_trigger_time(trigger, word_output_times)

        slot_name = re.sub(r"[^a-z0-9]+", "_", sd.get("topic_keyword", f"slide_{idx}").lower())
        slot_dir  = edit_dir / "overlays" / slot_name
        slot_dir.mkdir(parents=True, exist_ok=True)
        out_path  = slot_dir / "slide.mp4"

        html = _build_slide_html(sd, slot_name)
        (slot_dir / "index.html").write_text(html, encoding="utf-8")

        # Render sequentially (HyperFrames requirement)
        render_hyperframes(slot_dir, out_path, fmt="mp4")

        overlays.append({
            "file":            str(out_path.relative_to(edit_dir)),
            "start_in_output": round(start_in_output, 3),
            "duration":        4.0,
            "abs_path":        str(out_path),
        })

    return overlays


def _build_word_output_times(transcript_json: Path, ranges: list[dict]) -> list[dict]:
    """Return list of {text, output_time} for every word in the EDL ranges."""
    data  = json.loads(transcript_json.read_text(encoding="utf-8"))
    words = [w for w in data.get("words", []) if w.get("type") == "word"]
    result = []
    accumulated = 0.0
    for rng in ranges:
        r_start, r_end = float(rng["start"]), float(rng["end"])
        for w in words:
            ws = float(w["start"])
            if r_start <= ws < r_end:
                result.append({
                    "text":        w["text"].lower().strip(".,!?;:\"'"),
                    "output_time": accumulated + (ws - r_start),
                })
        accumulated += r_end - r_start
    return result


def _find_trigger_time(trigger_phrase: str, word_times: list[dict]) -> float:
    """Find the output timestamp when the trigger phrase first appears."""
    trigger_words = [w.lower().strip(".,!?;:\"'") for w in trigger_phrase.split()]
    if not trigger_words or not word_times:
        return 5.0  # fallback
    texts = [w["text"] for w in word_times]
    for i in range(len(texts) - len(trigger_words) + 1):
        if texts[i:i+len(trigger_words)] == trigger_words:
            return word_times[i]["output_time"]
    # Fallback: find first matching word
    for w in word_times:
        if trigger_words[0] in w["text"]:
            return w["output_time"]
    return 5.0


def _build_slide_html(sd: dict, slide_id: str) -> str:
    hl1  = sd.get("headline_line1", "")
    hl2  = sd.get("headline_line2", "")
    hlw  = sd.get("headline_highlight", hl2)
    sub  = sd.get("subtitle", "")
    var  = sd.get("variant", "big_stat")
    cap_main = sd.get("caption_main", "")
    cap_hl   = sd.get("caption_hl", "")

    # Highlight keyword in headline
    hl2_html = hl2.replace(hlw, f'<span class="hl">{hlw}</span>') if hlw in hl2 else hl2

    if var == "big_stat":
        num  = sd.get("stat_num", "")
        unit = sd.get("stat_unit", "")
        note = sd.get("stat_note", "")
        card_html = f"""<div id="card">
      <div class="big-stat">
        <div class="num">{num}</div>
        <div class="unit">{unit}</div>
      </div>
      <div class="stat-note">{note}</div>
    </div>"""
        extra_anim = """
  tl.from(".big-stat .num", { opacity:0, scale:0.7, duration:0.5, ease:"back.out(1.5)" }, 0.55);
  tl.from(".stat-note",     { opacity:0, y:20, duration:0.35 }, 0.75);"""
    else:
        bullets = sd.get("bullets") or ["", "", ""]
        rows = []
        for j, b in enumerate(bullets[:3]):
            rows.append(f'<div class="row"><div class="dot"></div><div class="label">{b}</div></div>')
            if j < 2:
                rows.append('<div class="divider"></div>')
        card_html = f'<div id="card">\n      {"".join(rows)}\n    </div>'
        extra_anim = """
  tl.from(".row:nth-child(1)", { opacity:0, x:-20, duration:0.3 }, 0.55);
  tl.from(".divider:nth-child(2)", { opacity:0, duration:0.2 }, 0.65);
  tl.from(".row:nth-child(3)", { opacity:0, x:-20, duration:0.3 }, 0.7);
  tl.from(".divider:nth-child(4)", { opacity:0, duration:0.2 }, 0.8);
  tl.from(".row:nth-child(5)", { opacity:0, x:-20, duration:0.3 }, 0.85);"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:{BG}; width:1080px; height:1920px; overflow:hidden;
       font-family:'Inter','Helvetica Neue',Arial,sans-serif; color:{TEXT}; }}
#content {{ position:absolute; top:500px; left:50px; right:50px; bottom:360px;
  display:flex; flex-direction:column; justify-content:center; gap:36px; }}
#headline {{ font-size:92px; font-weight:900; text-transform:uppercase;
  letter-spacing:-1px; line-height:1.0; text-align:center; }}
#headline .hl {{ color:{ORANGE}; }}
#subtitle {{ font-size:34px; font-weight:400; line-height:1.55; color:{BODY}; text-align:center; }}
#subtitle .hl {{ color:{ORANGE}; font-weight:700; }}
#card {{ background:{CARD}; border-radius:16px; padding:52px 44px;
  display:flex; flex-direction:column; align-items:center; gap:28px;
  box-shadow:0 2px 20px rgba(0,0,0,0.06); }}
.big-stat {{ text-align:center; }}
.big-stat .num {{ font-size:110px; font-weight:900; color:{ORANGE}; line-height:1.0; }}
.big-stat .unit {{ font-size:36px; font-weight:700; color:{TEXT}; text-transform:uppercase;
  letter-spacing:1px; margin-top:8px; }}
.stat-note {{ font-size:30px; color:#555; text-align:center; line-height:1.5; }}
.row {{ display:flex; align-items:center; gap:20px; width:100%; }}
.dot {{ width:18px; height:18px; border-radius:50%; background:{ORANGE}; flex-shrink:0; }}
.label {{ font-size:32px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; }}
.divider {{ height:1px; background:{BORDER}; width:100%; }}
#caption {{ position:absolute; bottom:270px; left:50px; right:50px;
  text-align:center; font-size:62px; font-weight:900;
  text-transform:uppercase; letter-spacing:1.5px; color:{TEXT}; }}
#caption .hl {{ color:{ORANGE}; }}
</style>
</head>
<body>
<div id="stage"
     data-composition-id="{slide_id}"
     data-width="1080" data-height="1920" data-fps="30"
     data-start="0" data-duration="4">
  <div id="content" class="clip" style="opacity:0">
    <div id="headline">{hl1}<br>{hl2_html}</div>
    <div id="subtitle">{sub}</div>
    {card_html}
  </div>
  <div id="caption" class="clip" style="opacity:0">
    {cap_main} <span class="hl">{cap_hl}</span>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
gsap.set(["#content","#caption"], {{ opacity:0 }});
tl.to("#content",    {{ opacity:1, duration:0.25 }}, 0.1);
tl.from("#headline", {{ opacity:0, y:30, scale:0.95, duration:0.4, ease:"power3.out" }}, 0.15);
tl.from("#subtitle", {{ opacity:0, y:16, duration:0.35 }}, 0.35);
tl.from("#card",     {{ opacity:0, y:40, duration:0.45, ease:"power2.out" }}, 0.4);{extra_anim}
tl.to("#caption",    {{ opacity:1, duration:0.2 }}, 0.6);
window.__timelines["{slide_id}"] = tl;
</script>
</body>
</html>"""


# ── DISCLAIMER OVERLAY (transparent MOV) ──────────────────────────────────────

def build_disclaimer_overlay(edit_dir: Path, edit_duration_s: float) -> Path:
    """Generate + render rotating 3-sentence disclaimer as transparent MOV."""
    from helpers.hf_render import render_hyperframes

    slot_dir = edit_dir / "overlays" / "disclaimer"
    slot_dir.mkdir(parents=True, exist_ok=True)
    out_path = slot_dir / "overlay.mov"

    dur = edit_duration_s

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:transparent; width:1080px; height:1920px; overflow:hidden;
       font-family:'Inter','Arial',sans-serif; }}
.disc {{ position:absolute; top:260px; left:50px; right:50px;
  background:{CARD}; border-radius:10px; padding:16px 28px;
  text-align:center; font-size:26px; line-height:1.45; color:{TEXT}; opacity:0; }}
</style>
</head>
<body>
<div id="stage"
     data-composition-id="disclaimer"
     data-width="1080" data-height="1920" data-fps="30"
     data-start="0" data-duration="{dur:.2f}">
  <div class="disc" id="d1">CFD trading carries a high level of risk and may not be suitable for all investors.</div>
  <div class="disc" id="d2">This content is for educational purposes only and does not constitute financial or investment advice.</div>
  <div class="disc" id="d3">Regulated by CMA, CySEC, FSA &amp; FSC. Trade responsibly.</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
const dur  = parseFloat(document.getElementById("stage").dataset.duration);
const each = dur / 3;
const fade = 0.3;
tl.to("#d1", {{ opacity:1, duration:fade }}, 0);
tl.to("#d1", {{ opacity:0, duration:fade }}, each - fade);
tl.to("#d2", {{ opacity:1, duration:fade }}, each - fade);
tl.to("#d2", {{ opacity:0, duration:fade }}, each * 2 - fade);
tl.to("#d3", {{ opacity:1, duration:fade }}, each * 2 - fade);
tl.to("#d3", {{ opacity:0, duration:fade }}, dur - fade);
window.__timelines["disclaimer"] = tl;
</script>
</body>
</html>"""

    (slot_dir / "index.html").write_text(html, encoding="utf-8")
    render_hyperframes(slot_dir, out_path, fmt="mov")
    return out_path


# ── BRANDED OUTRO (5-second opaque MP4) ───────────────────────────────────────

def build_outro(edit_dir: Path) -> Path:
    """Generate + render the branded 5-second outro as opaque MP4."""
    from helpers.hf_render import render_hyperframes

    slot_dir = edit_dir / "overlays" / "outro"
    slot_dir.mkdir(parents=True, exist_ok=True)
    out_path = slot_dir / "slide.mp4"

    logo_dataurl = _logo_dataurl()
    logo_html = (
        f'<img src="{logo_dataurl}" style="width:420px;height:auto;" alt="Wisuno">'
        if logo_dataurl else
        '<div style="font-size:72px;font-weight:900;color:#1A1A1A;">WISUNO</div>'
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ margin:0; padding:0; width:1080px; height:1920px; overflow:hidden; background:{CARD}; }}
#stage {{
  position:absolute; top:0; left:0;
  width:1080px; height:1920px;
  background:{CARD};
  font-family:'Inter','Helvetica Neue',Arial,sans-serif;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
}}
#logo-row   {{ display:flex; justify-content:center; margin-bottom:40px; }}
#divider    {{ width:360px; height:3px; background:{ORANGE}; margin-bottom:48px; flex-shrink:0; }}
#headline   {{ font-size:96px; font-weight:900; text-transform:uppercase; color:{TEXT};
               letter-spacing:-1px; text-align:center; margin-bottom:24px; line-height:1.05; }}
#subtitle   {{ font-size:32px; font-weight:400; color:#555; text-align:center;
               max-width:860px; line-height:1.6; margin-bottom:48px; padding:0 40px; }}
#handle-btn {{ border:3px solid {ORANGE}; border-radius:100px; padding:18px 56px;
               font-size:36px; font-weight:700; color:{ORANGE}; }}
#disclaimer {{ position:absolute; bottom:80px; left:60px; right:60px;
               font-size:24px; color:#999; text-align:center; line-height:1.5; }}
</style>
</head>
<body>
<div id="stage"
     data-composition-id="outro"
     data-width="1080" data-height="1920" data-fps="30"
     data-start="0" data-duration="5">
  <div id="logo-row">{logo_html}</div>
  <div id="divider"></div>
  <div id="headline">FOLLOW FOR MORE</div>
  <div id="subtitle">Daily market breakdowns so you never miss a macro move.</div>
  <div id="handle-btn">@wisuno</div>
  <div id="disclaimer">Past performance is not indicative of future results. Trading involves risk.</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
gsap.set(["#logo-row","#divider","#headline","#subtitle","#handle-btn","#disclaimer"], {{ opacity:0 }});
tl.to("#logo-row",    {{ opacity:1, duration:0.35, ease:"power2.out" }},            0.1);
tl.to("#divider",     {{ opacity:1, duration:0.35, ease:"power2.inOut" }},          0.35);
tl.fromTo("#headline",   {{ opacity:0, y:24 }}, {{ opacity:1, y:0, duration:0.45, ease:"power3.out" }}, 0.55);
tl.fromTo("#subtitle",   {{ opacity:0, y:16 }}, {{ opacity:1, y:0, duration:0.4 }},                    0.78);
tl.fromTo("#handle-btn", {{ opacity:0, scale:0.9 }}, {{ opacity:1, scale:1, duration:0.4, ease:"back.out(1.5)" }}, 1.0);
tl.to("#disclaimer",  {{ opacity:1, duration:0.4 }},                                1.2);
window.__timelines["outro"] = tl;
</script>
</body>
</html>"""

    (slot_dir / "index.html").write_text(html, encoding="utf-8")
    render_hyperframes(slot_dir, out_path, fmt="mp4")
    return out_path
