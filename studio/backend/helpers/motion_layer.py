"""
studio/backend/helpers/motion_layer.py  (v2 — "mist" scene system)
===================================================================
A library of reusable animated scene types in the style of the
29 Sep market-brief preview: drifting mist, mist-wipe transitions,
self-drawing charts, counting numbers, masked kinetic headlines.

Claude reads the final edit and returns a SCENE PLAN: which scene type fits
each beat, which word it starts/ends on, and the numbers/labels it shows.
Everything renders in ONE HyperFrames composition (transparent where the
speaker should be visible, opaque mist where graphics take over), including
the outro — so there is no separate outro render any more.

    words  = remap_words(transcript_json, cuts, fps)
    plan   = plan_motion(words, api_key, model, coverage="beats")
    overlay, total = render_motion_layer(edit_dir, words, plan, edit_duration, fps)
    compose_final(base, overlay, music, out, fps, edit_duration)

Open overlays/motion/preview.html in a browser to scrub the plan before
rendering (safe zones, caption space and figures-to-verify toggles).
"""
from __future__ import annotations

import html as _html
import json
import subprocess
from pathlib import Path

from helpers.build_karaoke_ass import (
    _load_words, _snap_dur, align_edit_to_timings, words_in_range,
)

OUTRO_DUR    = 5.0
SCENE_MIN    = 3.0    # shortest scene worth animating
BRIDGE_GAP   = 1.2    # gaps shorter than this are closed so mist doesn't flash the speaker
LOW_CONF_LP  = -0.5   # Scribe word logprob below this → number flagged "verify"

OUTRO = {
    "brand": "Wisuno",
    "line":  "Follow @wisuno for daily market briefs",
    "legal": "Trading involves risk. Not investment advice.",
}
DISCLAIMERS = [
    "CFD trading carries a high level of risk and may not be suitable for all investors.",
    "For educational purposes only. Not financial or investment advice.",
    "Regulated by CMA, CySEC, FSA &amp; FSC. Trade responsibly.",
]
MAX_WORDS, MAX_CHARS, GAP_BREAK = 4, 26, 0.8


# ══════════════════════════════════════════════════════════════════════════════
# 1. Timing: words on the output timeline + caption lines
# ══════════════════════════════════════════════════════════════════════════════

def remap_words(transcript_json: Path, ranges: list[dict], fps: float | None) -> list[dict]:
    words = _load_words(transcript_json)
    out, acc = [], 0.0
    for rng in ranges:
        r0, r1 = float(rng["start"]), float(rng["end"])
        rw = words_in_range(words, r0, r1)
        quote = (rng.get("quote") or "").strip()
        if quote and rng.get("quote_edited"):
            rw = align_edit_to_timings(rw, quote.split())
        for w in rw:
            out.append({
                "text":  w["text"].strip(),
                "start": acc + (float(w["start"]) - r0),
                "end":   acc + (min(float(w["end"]), r1) - r0),
                "lp":    w.get("logprob"),
            })
        acc += _snap_dur(r1 - r0, fps)
    return out


def caption_lines(words: list[dict]) -> list[dict]:
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur:
            gap = w["start"] - words[i - 1]["end"]
            txt = " ".join(x["text"] for x in cur)
            if len(cur) >= MAX_WORDS or len(txt) + len(w["text"]) + 1 > MAX_CHARS or gap > GAP_BREAK:
                groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    lines = []
    for i, g in enumerate(groups):
        t_in, t_out = g[0]["start"], g[-1]["end"] + 0.15
        if i + 1 < len(groups):
            t_out = min(t_out, groups[i + 1][0]["start"] - 0.04)
        lines.append({"t_in": round(t_in, 3), "t_out": round(max(t_out, t_in + 0.2), 3),
                      "words": [{"text": w["text"], "start": round(w["start"], 3),
                                 "end": round(w["end"], 3)} for w in g]})
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# 2. The scene plan (one Claude call: scenes + music + metadata)
# ══════════════════════════════════════════════════════════════════════════════

SCENE_TYPES = ["headline", "stat_line", "stairs", "gauge", "board",
               "curve_callouts", "fill", "stamp", "timeline"]

_S, _N, _I, _B = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}
_DIR = {"type": "string", "enum": ["up", "down", "flat"]}

def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}

SCENE_SCHEMA = _obj({
    "type":            {"type": "string", "enum": SCENE_TYPES},
    "start_word":      _I,
    "end_word":        _I,
    "kicker":          _S,
    "headline":        _S,
    "sub":             _S,
    "chip":            _S,
    "direction":       _DIR,
    "accent":          {"type": "string", "enum": ["ink", "harbor", "gold", "up", "down"]},
    "value_from":      _N,
    "value_to":        _N,
    "decimals":        _I,
    "prefix":          _S,
    "suffix":          _S,
    "points":          {"type": "array", "items": _N},
    "threshold":       {"type": "string", "enum": ["none", "ceiling", "band"]},
    "threshold_label": _S,
    "level":           _N,
    "stamp":           _S,
    "verify":          _B,
    "callouts":        {"type": "array", "items": _obj({"text": _S, "direction": _DIR, "at": _N})},
    "rows":            {"type": "array", "items": _obj({
                            "label": _S, "value_from": _N, "value_to": _N,
                            "decimals": _I, "direction": _DIR,
                            "points": {"type": "array", "items": _N}})},
    "events":          {"type": "array", "items": _obj({"when": _S, "label": _S, "highlight": _B})},
})

PLAN_SCHEMA = _obj({
    "scenes":   {"type": "array", "items": SCENE_SCHEMA},
    "music":    _obj({"prompt": _S, "bpm": _I}),
    "metadata": _obj({"title": _S, "caption": _S, "hashtags": {"type": "array", "items": _S}}),
})

SCENE_GUIDE = """SCENE TYPES — pick the one whose visual metaphor matches what is being said:
- headline: a big statement with no single number. kicker (optional), headline, sub, chip.
- stat_line: one key level plus its recent path (yields, an index, a price). value + line chart
  from `points`. threshold "ceiling" (dashed limit line, e.g. "Near a 19-year high") or
  "band" (shaded risk zone, e.g. "Intervention risk") with threshold_label, or "none".
- stairs: something stepping up or down over stages (rate path, rising expectations).
  3–5 `points` = bar heights. headline + chip.
- gauge: strength / pressure / sentiment of one thing (dollar strength, fear index).
  level 0–1 = needle position. value + sub + chip.
- board: 2–3 instruments moving together (FX pairs, indices). `rows` each with a short label
  ("EUR/USD"), value_from/value_to, decimals, direction and 5–7 sparkline `points`.
- curve_callouts: a story over time with 1–2 notable moments (sharp drop, then rebound).
  6–9 `points`; `callouts` with text ≤ 16 chars, direction, and `at` 0–1 along the curve.
- fill: a commodity or quantity filling up (oil, inventories, demand). level 0–1 = fill height,
  value + sub.
- stamp: a decision or event with a size (central bank hike/cut). headline ("Rates raised"),
  value (the new rate), stamp ("+25 bp"), direction.
- timeline: upcoming catalysts. 2–4 `events` (when ≤ 8 chars, label ≤ 18 chars); mark the most
  important one highlight=true.

FIELD RULES: kicker ≤ 34 chars, headline ≤ 30 chars (sentence case), sub ≤ 40 chars, chip ≤ 26.
value_to is the number the speaker says; value_from is a prior level ONLY if spoken, otherwise
equal to value_to. prefix like "$", suffix like "%" or " bp". points are 0–1 shapes that tell the
story honestly (rising, falling, drop-then-rebound) — they are illustrative, not data.
Never invent figures. Words marked with ? were transcribed with low confidence: if a scene's
number comes from one, set verify=true. Unused fields: "" / 0 / [] / "none"."""


def _indexed_transcript(words: list[dict]) -> str:
    rows, row = [], []
    for i, w in enumerate(words):
        if not row:
            row.append(f"[{w['start']:.1f}s]")
        flag = "?" if (w.get("lp") is not None and w["lp"] < LOW_CONF_LP
                       and any(c.isdigit() for c in w["text"])) else ""
        row.append(f"{i}:{w['text']}{flag}")
        if len(row) > 12:
            rows.append(" ".join(row)); row = []
    if row:
        rows.append(" ".join(row))
    return "\n".join(rows)


def plan_motion(words: list[dict], api_key: str, model: str, coverage: str = "beats") -> dict:
    """coverage="beats": graphics on the strongest beats, speaker on screen between them.
       coverage="full":  graphics run back to back for the whole video (like the 29 Sep brief)."""
    import anthropic

    duration = words[-1]["end"] if words else 0
    cover = (
        "Cover the WHOLE video with back-to-back scenes, one per beat (roughly every 5–12s). "
        "Scene N ends on the word just before scene N+1 starts."
        if coverage == "full" else
        "Pick the 3–6 strongest beats. Leave the speaker on screen for the hook, opinions and "
        "transitions. Each scene lasts 4–10s."
    )
    prompt = f"""You are the motion designer for a {duration:.0f}s vertical market-news reel.
The transcript is the FINAL edit, shown as index:word with timestamps.

{_indexed_transcript(words)}

{SCENE_GUIDE}

PLACEMENT: {cover} start_word/end_word are word indices; a scene appears as the speaker starts
that idea and holds until they finish it. Vary scene types — don't use the same type twice in a row.

Also return a music prompt for an ElevenLabs instrumental bed (genre, instruments, energy, tempo)
matching this video's mood — no vocals, no drops — and metadata (title, social caption, 5–8 hashtags)."""

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(next((b.text for b in resp.content if b.type == "text"), ""))


def place_scenes(scenes: list[dict], words: list[dict], duration: float,
                 coverage: str = "beats") -> list[dict]:
    """Word indices → seconds. Enforces min length, no overlaps, closes tiny gaps,
    and appends the outro scene after the edit."""
    out: list[dict] = []
    for s in sorted(scenes, key=lambda s: s.get("start_word", 0)):
        i, j = s.get("start_word", -1), s.get("end_word", -1)
        if not (0 <= i < len(words)):
            continue
        j = min(max(j, i), len(words) - 1)
        t0 = max(0.0, words[i]["start"] - 0.25)
        t1 = min(duration, max(words[j]["end"] + 0.35, t0 + SCENE_MIN))
        if out and t0 < out[-1]["end"]:
            if t0 < out[-1]["start"] + SCENE_MIN:
                continue
            out[-1]["end"] = t0
        if out and 0 < t0 - out[-1]["end"] < BRIDGE_GAP:
            out[-1]["end"] = t0
        if t1 - t0 < SCENE_MIN:
            continue
        out.append({**s, "start": round(t0, 3), "end": round(t1, 3)})

    if coverage == "full" and out:
        out[0]["start"] = 0.0
        for a, b in zip(out, out[1:]):
            a["end"] = b["start"]
        out[-1]["end"] = duration
    if out and duration - out[-1]["end"] < BRIDGE_GAP:
        out[-1]["end"] = duration
    out.append({"type": "outro", "start": round(duration, 3),
                "end": round(duration + OUTRO_DUR, 3), **OUTRO})
    return out


def _blocks(scenes: list[dict]) -> tuple[list[list[float]], list[float]]:
    """Contiguous scene runs (mist is opaque inside them) + interior cut points."""
    blocks, bounds = [], []
    for s in scenes:
        if blocks and abs(s["start"] - blocks[-1][1]) < 1e-3:
            bounds.append(s["start"]); blocks[-1][1] = s["end"]
        else:
            blocks.append([s["start"], s["end"]])
    return blocks, bounds


# ══════════════════════════════════════════════════════════════════════════════
# 3. The composition
# ══════════════════════════════════════════════════════════════════════════════

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Motion layer</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,300..800&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#1B2733;--ink2:#51606E;--harbor:#2E5B84;--up:#1E8558;--down:#C3453B;--gold:#A7822E;--haze:#C7D2DB}
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:transparent}
body{width:1080px;height:1920px;overflow:hidden;font-family:"IBM Plex Sans",system-ui,sans-serif;color:var(--ink)}
#stage{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden}
#mist{position:absolute;inset:0;width:100%;height:100%}
.grain{position:absolute;inset:0;opacity:0;mix-blend-mode:multiply;pointer-events:none;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}

.zone{position:absolute;left:170px;top:440px;width:740px;height:660px}
.scene{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;opacity:0;visibility:hidden}
.kicker{font-size:30px;font-weight:500;color:var(--ink2);letter-spacing:.01em}
.head{font-family:Archivo,"Arial Narrow",sans-serif;font-stretch:84%;font-weight:700;font-size:74px;line-height:1.02;letter-spacing:-.01em;margin-top:10px}
.head .w{display:inline-block;overflow:hidden;vertical-align:bottom;padding-bottom:.06em}
.head .w>span{display:inline-block}
.big{font-family:Archivo,"Arial Narrow",sans-serif;font-stretch:112%;font-weight:760;line-height:.92;letter-spacing:-.035em;font-variant-numeric:tabular-nums;margin-top:8px;white-space:nowrap}
.big small{font-size:.42em;letter-spacing:0;font-weight:600;margin-left:6px}
.big small.pre{margin:0 4px 0 0}
.sub{font-size:31px;color:var(--ink2);margin-top:18px;line-height:1.35}
.chip{display:inline-flex;align-items:center;gap:10px;padding:10px 20px;border-radius:999px;font-size:26px;font-weight:600;color:var(--harbor);background:rgba(255,255,255,.62);border:1.5px solid rgba(27,39,51,.12);margin-top:30px}
.chip.up{color:var(--up)} .chip.down{color:var(--down)}
.verify{display:inline-block;width:20px;height:20px;border-radius:50%;background:#E3A32B;vertical-align:super;margin-left:6px;opacity:0}
.show-verify .verify{opacity:1}
svg text{font-family:"IBM Plex Sans",system-ui,sans-serif}
.board{width:680px;display:flex;flex-direction:column;gap:22px;margin-top:34px}
.row{display:grid;grid-template-columns:1fr auto 150px;align-items:center;gap:22px;padding:26px 30px;border-radius:26px;background:rgba(255,255,255,.55);border:1.5px solid rgba(27,39,51,.1)}
.row .pair{font-family:Archivo,sans-serif;font-stretch:90%;font-weight:700;font-size:48px;text-align:left}
.row .px{font-family:Archivo,sans-serif;font-stretch:108%;font-weight:700;font-size:62px;font-variant-numeric:tabular-nums}
.stampwrap{position:relative;margin-top:10px}
.stamp{position:absolute;right:-70px;top:-18px;font-size:34px;padding:12px 24px;color:#fff;border:0;margin:0}

/* captions live in the reserved caption space, clear of the Reels UI */
.caps{position:absolute;left:120px;top:1170px;width:840px;height:230px}
.cap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;visibility:hidden}
.cap-box{display:inline-block;background:rgba(255,255,255,.92);border-radius:22px;padding:14px 18px;max-width:840px;text-align:center}
.cw{display:inline-block;font:600 50px/1.2 "IBM Plex Sans",system-ui,sans-serif;color:var(--ink);padding:2px 10px;border-radius:12px;background:rgba(46,91,132,0)}

.disc{position:absolute;top:268px;left:90px;right:90px;background:rgba(255,255,255,.88);border-radius:14px;padding:12px 24px;text-align:center;font-size:23px;line-height:1.4;color:var(--ink2);opacity:0}

/* preview-only chrome */
.guides{position:absolute;inset:0;pointer-events:none;display:none}
.show-guides .guides{display:block}
.g-ui{position:absolute;left:0;width:1080px;background:rgba(195,69,59,.12)}
.g-safe{position:absolute;left:60px;top:250px;width:960px;height:1220px;border:3px dashed rgba(195,69,59,.75)}
.g-zone{position:absolute;left:170px;top:440px;width:740px;height:660px;border:3px solid rgba(46,91,132,.7)}
.g-cap{position:absolute;left:120px;top:1170px;width:840px;height:230px;border:3px dashed rgba(27,39,51,.4);border-radius:20px}
body.preview{width:100vw;height:100vh;background:#DDE4EA;font-family:"IBM Plex Sans",system-ui,sans-serif}
body.preview #stage{left:50%;top:calc(50% - 34px);border-radius:18px;background:#38434E;box-shadow:0 20px 60px rgba(20,35,50,.25)}
.pv{position:fixed;left:0;right:0;bottom:0;display:flex;gap:14px;align-items:center;padding:14px 20px calc(14px + env(safe-area-inset-bottom,0px));background:#EEF2F5;border-top:1px solid #B9C5CF;font-size:14px;color:#1B2733}
.pv button{all:unset;cursor:pointer;width:40px;height:40px;border-radius:50%;background:#2E5B84;color:#fff;display:grid;place-items:center;flex:none}
.pv button:focus-visible{outline:2px solid #1B2733;outline-offset:2px}
.pv input[type=range]{flex:1;accent-color:#2E5B84;min-width:80px}
.pv .t{font-variant-numeric:tabular-nums;min-width:64px}
.pv label{display:flex;gap:6px;align-items:center;white-space:nowrap}
@media (max-width:640px){.pv label{display:none}}
</style></head>
<body>
<div id="stage" data-composition-id="motion" data-width="1080" data-height="1920"
     data-fps="__FPS__" data-start="0" data-duration="__DUR__">
  <canvas id="mist" width="360" height="640"></canvas>
  <div class="grain" id="grain"></div>
  <div class="zone" id="zone"></div>
  <div class="caps" id="caps"></div>
  <div class="guides" aria-hidden="true">
    <div class="g-ui" style="top:0;height:250px"></div><div class="g-ui" style="top:1470px;height:450px"></div>
    <div class="g-safe"></div><div class="g-zone"></div><div class="g-cap"></div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script>
(function(){
const D = __DATA__;
const stage = document.getElementById('stage'), zone = document.getElementById('zone');
const tl = gsap.timeline({paused:true});
const E = 'power3.out';
const C = {ink:'#1B2733', ink2:'#51606E', harbor:'#2E5B84', up:'#1E8558', down:'#C3453B', gold:'#A7822E'};
const STAIR = ['#C7D2DB','#9DB0C1','#6A86A2','#2E5B84','#1F4466'];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const q = (el, s) => el.querySelectorAll(s);
const dirCol = d => d === 'up' ? C.up : d === 'down' ? C.down : C.harbor;
const arrow  = d => d === 'up' ? '▲ ' : d === 'down' ? '▼ ' : '';
const acc    = a => C[a] || C.ink;
const fmtN   = (v, d) => v.toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d});
const r1     = n => Math.round(n * 10) / 10;

/* ── shared building blocks ─────────────────────────────────────────────── */
const split  = t => esc(t).split(/\s+/).filter(Boolean).map(w => '<span class="w"><span>' + w + '</span></span>').join(' ');
const kicker = s => s.kicker ? '<div class="kicker">' + esc(s.kicker) + '</div>' : '';
const head   = s => s.headline ? '<h2 class="head">' + split(s.headline) + '</h2>' : '';
const sub    = (s, st) => s.sub ? '<div class="sub"' + (st ? ' style="' + st + '"' : '') + '>' + esc(s.sub) + '</div>' : '';
const chip   = s => s.chip ? '<div class="chip ' + s.direction + '">' + arrow(s.direction) + esc(s.chip) + '</div>' : '';
const verify = s => s.verify ? '<span class="verify"></span>' : '';
function big(s, max) {
  const txt = (s.prefix || '') + fmtN(s.value_to, s.decimals) + (s.suffix || '');
  const size = Math.round(Math.min(max, 700 / Math.max(3, txt.length * 0.62)));
  return '<div class="big" style="font-size:' + size + 'px">' +
    (s.prefix ? '<small class="pre">' + esc(s.prefix) + '</small>' : '') + '<span class="cnt"></span>' +
    (s.suffix ? '<small>' + esc(s.suffix) + '</small>' : '') + verify(s) + '</div>';
}
function fromVal(from, to, dir) {
  if (from !== to && from !== 0) return from;
  return to * (1 + 0.03 * (dir === 'up' ? -1 : dir === 'down' ? 1 : 0));
}
function counter(span, from, to, dec, at, dur) {
  if (!span) return;
  const o = {v:from}; span.textContent = fmtN(from, dec);
  tl.fromTo(o, {v:from}, {v:to, duration:dur, ease:'power2.out', immediateRender:false,
    onUpdate:() => { span.textContent = fmtN(o.v, dec); }}, at);
}
function pts(p, n) {
  const v = (p && p.length >= 2 ? p : [.15,.3,.25,.45,.55,.7,.85]).map(x => Math.max(0, Math.min(1, +x || 0)));
  return n ? v.slice(0, n) : v;
}
/* Catmull-Rom → cubic bezier through 0–1 points inside a box */
function curve(p, w, h, pad) {
  const P = p.map((v, i) => [pad.l + i * (w - pad.l - pad.r) / (p.length - 1), pad.t + (1 - v) * (h - pad.t - pad.b)]);
  let d = 'M' + r1(P[0][0]) + ' ' + r1(P[0][1]);
  for (let i = 0; i < P.length - 1; i++) {
    const a = P[i - 1] || P[i], b = P[i], c = P[i + 1], e = P[i + 2] || c;
    d += ' C' + r1(b[0] + (c[0] - a[0]) / 6) + ' ' + r1(b[1] + (c[1] - a[1]) / 6) + ' ' +
         r1(c[0] - (e[0] - b[0]) / 6) + ' ' + r1(c[1] - (e[1] - b[1]) / 6) + ' ' + r1(c[0]) + ' ' + r1(c[1]);
  }
  return {d, P, last:P[P.length - 1]};
}
function prepDraw(el) {
  q(el, '.draw').forEach(p => { const L = p.getTotalLength(); p.style.strokeDasharray = L; p.style.strokeDashoffset = L; p.dataset.len = L; });
}
const words = (el, at) => { const w = q(el, '.head .w>span'); if (w.length) tl.from(w, {yPercent:110, duration:.7, stagger:.07, ease:E}, at); };
const draw  = (el, sel, at, dur, ease) => q(el, sel).forEach(p => tl.to(p, {strokeDashoffset:0, duration:dur, ease:ease || 'power2.inOut'}, at));
const pop   = (el, sel, at) => { const n = q(el, sel); if (n.length) tl.from(n, {scale:0, autoAlpha:0, transformOrigin:'50% 50%', duration:.5, ease:'back.out(2.2)'}, at); };
const rise  = (el, sel, at, y) => { const n = q(el, sel); if (n.length) tl.from(n, {y:y || 24, autoAlpha:0, duration:.55, ease:E}, at); };
function pulse(el, sel, at, until) {
  const n = Math.floor((until - at) / 1.2); if (n < 1) return;
  tl.to(q(el, sel), {scale:1.45, transformOrigin:'50% 50%', duration:.6, ease:'sine.inOut', yoyo:true, repeat:n * 2 - 1}, at);
}
function pill(x, y, text, color, maxW) {
  const w = Math.min(maxW, text.length * 15 + 48), cxp = Math.max(0, Math.min(maxW - w, x - w / 2));
  return '<g class="call"><rect x="' + r1(cxp) + '" y="' + r1(y) + '" width="' + w + '" height="56" rx="28" fill="#fff" opacity=".85"/>' +
    '<text x="' + r1(cxp + w / 2) + '" y="' + r1(y + 37) + '" text-anchor="middle" font-size="26" font-weight="600" fill="' + color + '">' + esc(text) + '</text></g>';
}

/* ── scene library ──────────────────────────────────────────────────────── */
const SCENES = {
  headline: {
    natural: 1.6,
    html: s => kicker(s) + head(s) +
      '<svg width="420" height="20" viewBox="0 0 420 20" style="margin-top:28px"><line class="draw" x1="10" y1="10" x2="410" y2="10" stroke="' + acc(s.accent === 'ink' ? 'harbor' : s.accent) + '" stroke-width="8" stroke-linecap="round"/></svg>' +
      sub(s) + chip(s),
    anim(el, at) { rise(el, '.kicker', at(0)); words(el, at(.15)); draw(el, '.draw', at(.7), .8, E); rise(el, '.sub', at(1)); pop(el, '.chip', at(1.3)); }
  },

  stat_line: {
    natural: 4.2,
    html(s) {
      const th = s.threshold, top = th === 'band' ? 76 : th === 'ceiling' ? 40 : 14;
      const c = curve(pts(s.points), 640, 190, {l:4, r:12, t:top, b:10});
      let g = '';
      if (th === 'ceiling') g = '<line class="ceil" x1="0" y1="30" x2="640" y2="30" stroke="' + C.down + '" stroke-width="3" stroke-dasharray="10 10"/>' +
        '<text class="th-lab" x="640" y="16" text-anchor="end" font-size="24" font-weight="600" fill="' + C.down + '">' + esc(s.threshold_label) + '</text>';
      if (th === 'band') g = '<rect class="band" x="0" y="0" width="640" height="68" rx="10" fill="' + C.down + '" opacity=".14"/>' +
        '<text class="th-lab" x="18" y="44" font-size="25" font-weight="600" fill="' + C.down + '">' + esc(s.threshold_label) + '</text>';
      return kicker(s) + head(s) + big(s, s.headline ? 170 : 190) + sub(s) +
        '<svg viewBox="0 0 640 190" width="640" height="190" style="margin-top:20px;overflow:visible">' + g +
        '<path class="draw" d="' + c.d + '" fill="none" stroke="' + acc(s.accent) + '" stroke-width="6" stroke-linecap="round"/>' +
        '<circle class="dot" cx="' + r1(c.last[0]) + '" cy="' + r1(c.last[1]) + '" r="11" fill="' + (th !== 'none' ? C.down : dirCol(s.direction)) + '"/></svg>';
    },
    anim(el, at, s) {
      rise(el, '.kicker', at(0)); words(el, at(.15));
      rise(el, '.big', at(.6), 60); counter(el.querySelector('.cnt'), fromVal(s.value_from, s.value_to, s.direction), s.value_to, s.decimals, at(.6), 2.2);
      rise(el, '.sub', at(1));
      if (q(el, '.ceil').length) tl.from(q(el, '.ceil'), {scaleX:0, transformOrigin:'100% 50%', duration:.8, ease:E}, at(1.2));
      if (q(el, '.band').length) tl.from(q(el, '.band'), {scaleY:0, transformOrigin:'50% 0%', duration:.6, ease:E}, at(1.2));
      if (q(el, '.th-lab').length) tl.from(q(el, '.th-lab'), {autoAlpha:0, x:30, duration:.5}, at(1.6));
      draw(el, '.draw', at(1.2), 2.4); pop(el, '.dot', at(3.5)); pulse(el, '.dot', at(4.1), s.end - .6);
    }
  },

  stairs: {
    natural: 2.2,
    html(s) {
      const v = pts(s.points).slice(0, 5), n = Math.max(3, v.length), gap = 30, bw = (520 - gap * (n - 1)) / n;
      const bars = v.map((x, i) => { const h = 50 + x * 230;
        const fill = i === v.length - 1 && s.direction !== 'flat' ? dirCol(s.direction) === C.down ? C.down : STAIR[4] : STAIR[Math.round(i / (n - 1) * 3)];
        return '<rect x="' + r1(20 + i * (bw + gap)) + '" y="' + r1(290 - h) + '" width="' + r1(bw) + '" height="' + r1(h) + '" rx="14" fill="' + fill + '"/>'; }).join('');
      return kicker(s) + head(s) + '<svg viewBox="0 0 560 300" width="560" height="300" style="margin-top:40px"><g class="stairs">' + bars + '</g></svg>' + chip(s) + sub(s);
    },
    anim(el, at) {
      rise(el, '.kicker', at(0)); words(el, at(.1));
      tl.from(q(el, '.stairs rect'), {scaleY:0, transformOrigin:'50% 100%', duration:.6, stagger:.18, ease:'back.out(1.6)'}, at(.5));
      rise(el, '.chip', at(1.5), 30); rise(el, '.sub', at(1.8));
    }
  },

  gauge: {
    natural: 2.4,
    html: s => kicker(s) + head(s) +
      '<svg viewBox="0 0 560 300" width="560" height="300" style="margin-top:22px;overflow:visible">' +
      '<path d="M60 280 A220 220 0 0 1 500 280" fill="none" stroke="#C7D2DB" stroke-width="28" stroke-linecap="round"/>' +
      '<path class="gauge" d="M60 280 A220 220 0 0 1 500 280" fill="none" stroke="' + acc(s.accent === 'ink' ? 'harbor' : s.accent) + '" stroke-width="28" stroke-linecap="round"/>' +
      '<g class="needle"><line x1="280" y1="280" x2="280" y2="120" stroke="#1B2733" stroke-width="8" stroke-linecap="round"/><circle cx="280" cy="280" r="18" fill="#1B2733"/></g></svg>' +
      big(s, 176) + sub(s) + chip(s),
    anim(el, at, s) {
      const g = el.querySelector('.gauge'), L = g.getTotalLength(), lvl = Math.max(.05, Math.min(.98, s.level || .7));
      g.style.strokeDasharray = L; g.style.strokeDashoffset = L;
      rise(el, '.kicker', at(0)); words(el, at(.1));
      tl.to(g, {strokeDashoffset:L * (1 - lvl), duration:1.6, ease:E}, at(.3));
      const deg = -88 + lvl * 176;
      tl.fromTo(q(el, '.needle'), {rotation:-88, svgOrigin:'280 280'}, {rotation:deg, svgOrigin:'280 280', duration:1.6, ease:'back.out(1.4)', immediateRender:true}, at(.3));
      const rep = Math.floor((s.end - at(1.9) - 1) / .8);
      if (rep > 0) tl.to(q(el, '.needle'), {rotation:deg - 3, svgOrigin:'280 280', duration:.8, yoyo:true, repeat:rep, ease:'sine.inOut'}, at(1.9));
      rise(el, '.big', at(.4), 40); counter(el.querySelector('.cnt'), fromVal(s.value_from, s.value_to, s.direction), s.value_to, s.decimals, at(.4), 1.8);
      rise(el, '.sub', at(.9)); pop(el, '.chip', at(1.9));
    }
  },

  board: {
    natural: 2.4,
    html: s => kicker(s) + head(s) + '<div class="board">' + (s.rows || []).slice(0, 3).map(r => {
        const c = curve(pts(r.points, 7), 150, 60, {l:4, r:4, t:8, b:8});
        return '<div class="row"><div class="pair">' + esc(r.label) + '</div><div class="px"><span class="cnt"></span>' + verify(s) + '</div>' +
          '<svg viewBox="0 0 150 60" width="150" height="60"><path class="draw" d="' + c.d + '" fill="none" stroke="' + dirCol(r.direction) + '" stroke-width="5" stroke-linecap="round"/></svg></div>';
      }).join('') + '</div>',
    anim(el, at, s) {
      rise(el, '.kicker', at(0)); words(el, at(.05));
      const rows = q(el, '.row'), rd = s.rows || [];
      rows.forEach((row, i) => {
        tl.from(row, {x:i % 2 ? 120 : -120, autoAlpha:0, duration:.7, ease:E}, at(.5 + i * .25));
        const r = rd[i]; counter(row.querySelector('.cnt'), fromVal(r.value_from, r.value_to, r.direction), r.value_to, r.decimals, at(.7 + i * .25), 1.6);
        tl.to(row.querySelector('.draw'), {strokeDashoffset:0, duration:1.2, ease:'power2.inOut'}, at(.9 + i * .25));
      });
    }
  },

  curve_callouts: {
    natural: 7.0,
    html(s) {
      const c = curve(pts(s.points), 660, 300, {l:10, r:20, t:40, b:50});
      const calls = (s.callouts || []).slice(0, 2).map(k => {
        const p = c.P[Math.round(Math.max(0, Math.min(1, k.at)) * (c.P.length - 1))];
        return pill(p[0], p[1] > 150 ? p[1] - 84 : p[1] + 24, arrow(k.direction) + k.text, dirCol(k.direction), 660);
      }).join('');
      return kicker(s) + head(s) + '<svg viewBox="0 0 660 300" width="660" height="300" style="margin-top:30px;overflow:visible">' +
        '<path class="draw" d="' + c.d + '" fill="none" stroke="' + acc(s.accent) + '" stroke-width="7" stroke-linecap="round"/>' + calls +
        '<circle class="dot" cx="' + r1(c.last[0]) + '" cy="' + r1(c.last[1]) + '" r="11" fill="' + acc(s.accent) + '"/></svg>' + sub(s) + verify(s);
    },
    anim(el, at, s, k) {
      rise(el, '.kicker', at(0)); words(el, at(.05));
      draw(el, '.draw', at(.5), 4 * k, 'power1.inOut');
      q(el, '.call').forEach((g, i) => tl.from(g, {scale:0, autoAlpha:0, transformOrigin:'50% 50%', duration:.5, ease:'back.out(2.2)'},
        at(.5 + Math.max(.15, (s.callouts[i] || {}).at || .5) * 4)));
      pop(el, '.dot', at(4.5)); pulse(el, '.dot', at(5.1), s.end - .6); rise(el, '.sub', at(4.8));
    }
  },

  fill: {
    natural: 2.6,
    html: s => kicker(s) + head(s) +
      '<svg viewBox="0 0 240 300" width="200" height="250" style="margin-top:18px;overflow:visible"><defs><clipPath id="drop' + s.idx + '">' +
      '<path d="M120 10 C120 10 30 130 30 190 A90 90 0 0 0 210 190 C210 130 120 10 120 10Z"/></clipPath></defs>' +
      '<path d="M120 10 C120 10 30 130 30 190 A90 90 0 0 0 210 190 C210 130 120 10 120 10Z" fill="rgba(255,255,255,.5)" stroke="#1B2733" stroke-width="6"/>' +
      '<g clip-path="url(#drop' + s.idx + ')"><g class="liquid"><path class="wave" d="M-240 20 Q-210 0 -180 20 T-120 20 T-60 20 T0 20 T60 20 T120 20 T180 20 T240 20 T300 20 T360 20 T420 20 T480 20 V400 H-240Z" fill="' + (s.accent === 'gold' ? C.gold : C.ink) + '"/></g></g></svg>' +
      big(s, 168) + sub(s),
    anim(el, at, s) {
      const ty = 300 - (20 + Math.max(.05, Math.min(.95, s.level || .7)) * 270);
      rise(el, '.kicker', at(0)); words(el, at(.05));
      tl.fromTo(q(el, '.liquid'), {y:300}, {y:ty, duration:2.4, ease:'power2.out', immediateRender:true}, at(.2));
      const rep = Math.floor((s.end - s.start) / 1.2);
      tl.fromTo(q(el, '.wave'), {x:0}, {x:120, duration:1.2, ease:'none', repeat:Math.max(0, rep), immediateRender:true}, s.start);
      rise(el, '.big', at(.4), 40); counter(el.querySelector('.cnt'), fromVal(s.value_from, s.value_to, s.direction), s.value_to, s.decimals, at(.4), 2.2);
      rise(el, '.sub', at(.9));
    }
  },

  stamp: {
    natural: 3.2,
    html(s) {
      const d = s.direction === 'down' ? 'M10 30 H260 V100 H550' : 'M10 100 H260 V30 H550';
      return kicker(s) + head(s) + '<div class="stampwrap">' + big(s, 190) +
        (s.stamp ? '<div class="chip stamp" style="background:' + dirCol(s.direction) + '">' + esc(s.stamp) + '</div>' : '') + '</div>' +
        '<svg viewBox="0 0 560 120" width="560" height="120" style="margin-top:22px"><path class="draw" d="' + d + '" fill="none" stroke="' + C.harbor + '" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/></svg>' + sub(s);
    },
    anim(el, at, s) {
      rise(el, '.kicker', at(0)); words(el, at(.2)); rise(el, '.big', at(.5), 40);
      draw(el, '.draw', at(.8), 1.4);
      counter(el.querySelector('.cnt'), fromVal(s.value_from, s.value_to, s.direction), s.value_to, s.decimals, at(1.2), 1.2);
      if (q(el, '.stamp').length) tl.from(q(el, '.stamp'), {scale:2.6, rotation:-18, autoAlpha:0, duration:.45, ease:'back.out(1.8)'}, at(2.3));
      rise(el, '.sub', at(3));
    }
  },

  timeline: {
    natural: 3.0,
    html(s) {
      const ev = (s.events || []).slice(0, 4), n = Math.max(2, ev.length);
      let hi = ev.findIndex(e => e.highlight); if (hi < 0) hi = ev.length - 1;
      const xs = ev.map((_, i) => 90 + i * (520 / (n - 1)));
      const wrap = t => { const w = String(t).split(/\s+/); if (w.length < 2 || t.length <= 11) return [t]; const m = Math.ceil(w.length / 2); return [w.slice(0, m).join(' '), w.slice(m).join(' ')]; };
      const g = ev.map((e, i) => { const H = i === hi, col = H ? C.down : C.ink2;
        const lab = wrap(e.label).map((l, j) => '<text x="' + r1(xs[i]) + '" y="' + (220 + j * 32) + '" text-anchor="middle" font-size="' + (H ? 27 : 25) + '" font-weight="' + (H ? 600 : 400) + '" fill="' + col + '">' + esc(l) + '</text>').join('');
        return '<g class="ev"><circle cx="' + r1(xs[i]) + '" cy="160" r="' + (H ? 24 : 16) + '" fill="' + (H ? C.down : C.harbor) + '"/>' +
          '<text x="' + r1(xs[i]) + '" y="110" text-anchor="middle" font-size="28" font-weight="600" fill="#1B2733">' + esc(e.when) + '</text>' + lab + '</g>'; }).join('');
      return kicker(s) + head(s) + '<svg viewBox="0 0 700 330" width="700" height="330" style="margin-top:34px">' +
        '<line class="draw" x1="40" y1="160" x2="660" y2="160" stroke="#1B2733" stroke-width="5" stroke-linecap="round"/>' + g +
        '<circle class="runner" cx="40" cy="160" r="9" fill="#1B2733" data-to="' + r1(xs[hi] || 590) + '"/></svg>' + sub(s, 'margin-top:0');
    },
    anim(el, at, s, k) {
      rise(el, '.kicker', at(0)); words(el, at(.05)); draw(el, '.draw', at(.4), 1.2);
      q(el, '.ev').forEach((g, i) => tl.from(g, {scale:0, autoAlpha:0, transformOrigin:'50% 50%', duration:.5, ease:'back.out(2.2)'}, at(.9 + i * .4)));
      const rn = el.querySelector('.runner');
      tl.fromTo(rn, {attr:{cx:40}}, {attr:{cx:+rn.dataset.to}, duration:Math.max(1.5, s.end - at(2.4) - .8), ease:'power1.inOut', immediateRender:true}, at(2.4));
      rise(el, '.sub', at(2.6));
    }
  },

  outro: {
    natural: 1,
    html: s => '<div class="big" style="font-size:132px;font-stretch:96%;letter-spacing:-.02em">' + esc(s.brand) + '</div>' +
      '<div class="sub" style="font-size:36px;color:#1B2733">' + esc(s.line) + '</div>' +
      '<div class="sub" style="font-size:22px;margin-top:40px">' + esc(s.legal) + '</div>',
    anim(el, at) { tl.from(q(el, '.big'), {autoAlpha:0, letterSpacing:'.2em', duration:.9, ease:E}, at(0)); tl.from(q(el, '.sub'), {autoAlpha:0, y:16, duration:.5, stagger:.2, ease:E}, at(.4)); }
  }
};

D.scenes.forEach((s, idx) => {
  const B = SCENES[s.type]; if (!B) return;
  s.idx = idx;
  const el = document.createElement('section'); el.className = 'scene';
  el.innerHTML = B.html(s); zone.appendChild(el); prepDraw(el);
  const dur = s.end - s.start, inT = s.start + (s.start < .05 ? .6 : .15);
  const k = Math.max(.35, Math.min(1, (dur - 1.4) / B.natural));
  tl.set(el, {autoAlpha:1}, inT);
  B.anim(el, x => inT + x * k, s, k);
  if (s.type !== 'outro') tl.to(el, {autoAlpha:0, filter:'blur(14px)', scale:1.04, duration:.4, ease:'power2.in'}, s.end - .45);
  tl.set(el, {filter:'none', scale:1}, s.end);
});

/* ── karaoke captions ───────────────────────────────────────────────────── */
const caps = document.getElementById('caps');
D.lines.forEach(line => {
  const cap = document.createElement('div'); cap.className = 'cap';
  const box = document.createElement('div'); box.className = 'cap-box'; cap.appendChild(box); caps.appendChild(cap);
  const sp = line.words.map(w => { const e = document.createElement('span'); e.className = 'cw'; e.textContent = w.text; box.appendChild(e); box.appendChild(document.createTextNode(' ')); return e; });
  tl.set(cap, {visibility:'visible'}, line.t_in);
  tl.fromTo(box, {y:22, opacity:0, scale:.96}, {y:0, opacity:1, scale:1, duration:.2, ease:'back.out(2)'}, line.t_in);
  line.words.forEach((w, j) => {
    tl.to(sp[j], {backgroundColor:C.harbor, color:'#fff', duration:.06}, w.start);
    tl.to(sp[j], {backgroundColor:'rgba(46,91,132,0)', color:C.ink, duration:.12}, Math.max(w.start + .06, w.end));
  });
  tl.to(box, {opacity:0, y:-6, duration:.08}, line.t_out - .08);
  tl.set(cap, {visibility:'hidden'}, line.t_out);
});

/* ── rotating disclaimer (over the edit only, not the outro) ────────────── */
const each = D.edit / D.disclaimers.length;
D.disclaimers.forEach((t, i) => {
  const d = document.createElement('div'); d.className = 'disc'; d.innerHTML = t; stage.appendChild(d);
  tl.fromTo(d, {opacity:0, y:-8}, {opacity:1, y:0, duration:.3}, Math.max(0, i * each - .1));
  tl.to(d, {opacity:0, duration:.3}, (i + 1) * each - .3);
});

/* ── mist: deterministic in t, opaque inside scene blocks, wipes at every cut ── */
const cv = document.getElementById('mist'), cx = cv.getContext('2d'), W = cv.width, H = cv.height;
const grain = document.getElementById('grain');
const rnd = s => { const x = Math.sin(s * 127.1) * 43758.5453; return x - Math.floor(x); };
const puffs = Array.from({length:22}, (_, i) => ({x:rnd(i+1)*W, y:rnd(i+11)*H, r:90+rnd(i+21)*170, sp:4+rnd(i+31)*9, ph:rnd(i+41)*6.28, a:.28+rnd(i+51)*.35, tint:rnd(i+61)}));
const wipes = Array.from({length:26}, (_, i) => ({y:rnd(i+71)*H*1.1-H*.05, r:110+rnd(i+81)*160, off:rnd(i+91)*.5-.25}));
const EDGES = D.bounds.concat(D.blocks.flat().filter(x => x > .05 && x < D.total - .05));
function puff(x, y, r, a, col) {
  const g = cx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, 'rgba(' + col + ',' + a + ')'); g.addColorStop(.55, 'rgba(' + col + ',' + a * .45 + ')'); g.addColorStop(1, 'rgba(' + col + ',0)');
  cx.fillStyle = g; cx.beginPath(); cx.arc(x, y, r, 0, 6.2832); cx.fill();
}
function envAt(t) {
  let e = 0;
  for (const [a, b] of D.blocks) {
    const i = a <= .05 ? 1 : (t - (a - .35)) / .7, o = b >= D.total - .05 ? 1 : ((b + .35) - t) / .7;
    e = Math.max(e, Math.min(1, i, o));
  }
  return Math.max(0, e);
}
function drawMist(t) {
  cx.clearRect(0, 0, W, H);
  const env = envAt(t);
  if (env > 0) {
    cx.globalAlpha = env;
    const bg = cx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#DCE5EC'); bg.addColorStop(.45, '#EEF2F5'); bg.addColorStop(1, '#D2DCE4');
    cx.fillStyle = bg; cx.fillRect(0, 0, W, H);
    for (const p of puffs) {
      const x = ((p.x + t * p.sp) % (W + 2 * p.r)) - p.r, y = p.y + Math.sin(t * .25 + p.ph) * 18;
      puff(x, y, p.r * (1 + .06 * Math.sin(t * .4 + p.ph)), p.a, p.tint > .7 ? '206,219,230' : '255,255,255');
    }
  }
  cx.globalAlpha = 1;
  let k = 0, pr = .5, dir = 1;
  EDGES.forEach((b, i) => { const p = (t - (b - .7)) / 1.4; if (p > 0 && p < 1) { const s = Math.sin(p * Math.PI); if (s > k) { k = s; pr = p; dir = i % 2 ? -1 : 1; } } });
  if (D.blocks.length && D.blocks[0][0] <= .05 && t < 1.4) { const s = 1 - t / 1.4; if (s > k) { k = s; pr = .5; dir = 0; } }
  if (k > 0) {
    for (const w of wipes) {
      const x = dir === 0 ? W * (.5 + w.off * 2) : dir > 0 ? (-.4 + (pr + w.off) * 1.8) * W : (1.4 - (pr + w.off) * 1.8) * W;
      puff(x, w.y, w.r * (1 + k * .3), .85 * k, '248,250,252');
    }
    cx.fillStyle = 'rgba(245,248,250,' + (.55 * k) + ')'; cx.fillRect(0, 0, W, H);
  }
  grain.style.opacity = (.06 * env).toFixed(3);
}
const clock = {t:0};
tl.to(clock, {t:D.total, duration:D.total, ease:'none', onUpdate:() => drawMist(clock.t)}, 0);
tl.set(stage, {opacity:1}, D.total);
drawMist(0);
window.__timelines = window.__timelines || {};
window.__timelines['motion'] = tl;

/* ── preview player (only when built with preview=True) ─────────────────── */
if (D.preview) {
  document.body.classList.add('preview'); stage.classList.add('show-verify');
  const bar = document.createElement('div'); bar.className = 'pv';
  bar.innerHTML = '<button id="pvp" aria-label="Play">▶</button><span class="t" id="pvt">0:00.0</span>' +
    '<input type="range" id="pvs" min="0" max="' + D.total + '" step="0.01" value="0" aria-label="Timeline">' +
    '<label><input type="checkbox" id="pvg"> Safe zones</label><label><input type="checkbox" id="pvv" checked> Figures to verify</label>';
  document.body.appendChild(bar);
  const fit = () => { const s = Math.min(innerWidth / 1080, (innerHeight - 90) / 1920); stage.style.transform = 'translate(-50%,-50%) scale(' + s + ')'; };
  addEventListener('resize', fit); fit();
  let t = 0, playing = false, last = 0;
  const btn = document.getElementById('pvp'), sc = document.getElementById('pvs'), tt = document.getElementById('pvt');
  const fmt = s => Math.floor(s / 60) + ':' + (s % 60).toFixed(1).padStart(4, '0');
  const show = () => { tl.seek(t, false); sc.value = t; tt.textContent = fmt(t); };
  btn.onclick = () => { playing = !playing; if (playing && t >= D.total - .01) t = 0; btn.textContent = playing ? '❚❚' : '▶'; btn.setAttribute('aria-label', playing ? 'Pause' : 'Play'); };
  sc.oninput = e => { t = +e.target.value; show(); };
  document.getElementById('pvg').onchange = e => stage.classList.toggle('show-guides', e.target.checked);
  document.getElementById('pvv').onchange = e => stage.classList.toggle('show-verify', e.target.checked);
  const loop = now => { if (playing) { t += (now - last) / 1000; if (t >= D.total) { t = D.total; btn.onclick(); } show(); } last = now; requestAnimationFrame(loop); };
  show(); requestAnimationFrame(n => { last = n; loop(n); });
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) btn.onclick();
}
})();
</script>
</body></html>"""


def build_motion_html(scenes, lines, edit_duration, fps, preview=False) -> str:
    blocks, bounds = _blocks(scenes)
    total = edit_duration + OUTRO_DUR
    data = {"scenes": scenes, "lines": lines, "blocks": blocks, "bounds": bounds,
            "edit": round(edit_duration, 3), "total": round(total, 3),
            "disclaimers": DISCLAIMERS, "preview": preview}
    out = (_TEMPLATE.replace("__FPS__", str(round(fps) if fps else 30))
                    .replace("__DUR__", f"{total:.3f}"))
    return out.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def render_motion_layer(edit_dir: Path, words: list[dict], plan: dict, edit_duration: float,
                        fps: float | None, coverage: str = "beats",
                        include_graphics: bool = True) -> tuple[Path, float]:
    from helpers.hf_render import render_hyperframes

    scenes = place_scenes(plan.get("scenes", []) if include_graphics else [], words,
                          edit_duration, coverage)
    lines = caption_lines(words)
    slot = edit_dir / "overlays" / "motion"
    slot.mkdir(parents=True, exist_ok=True)
    (slot / "index.html").write_text(build_motion_html(scenes, lines, edit_duration, fps), encoding="utf-8")
    (slot / "preview.html").write_text(build_motion_html(scenes, lines, edit_duration, fps, preview=True), encoding="utf-8")
    (slot / "plan.json").write_text(json.dumps({"scenes": scenes, "plan": plan}, indent=2), encoding="utf-8")
    out = slot / "overlay.mov"
    render_hyperframes(slot, out, fmt="mov")
    return out, edit_duration + OUTRO_DUR


# ══════════════════════════════════════════════════════════════════════════════
# 4. One ffmpeg pass. The outro is part of the overlay now: the base video is
#    held on its last frame for OUTRO_DUR and the opaque mist covers it.
# ══════════════════════════════════════════════════════════════════════════════

def compose_final(base: Path, overlay: Path, music: Path | None, out: Path,
                  fps: float, edit_duration: float, outro_dur: float = OUTRO_DUR) -> None:
    total = edit_duration + outro_dur
    rate = f"{fps:.6f}" if fps else "30"
    af = "aformat=sample_rates=48000:channel_layouts=stereo"
    fc = [
        f"[0:v]tpad=stop_mode=clone:stop_duration={outro_dur},fps={rate},setsar=1[bg]",
        "[bg][1:v]overlay=0:0:eof_action=pass,format=yuv420p[v]",
        f"[0:a]{af},apad,atrim=duration={total:.3f}[voice]",
    ]
    inputs = ["-i", str(base), "-i", str(overlay)]
    if music and music.exists():
        inputs += ["-i", str(music)]
        fc += [
            "[voice]asplit=2[vo][sc]",
            f"[2:a]{af},atrim=duration={total:.3f},volume=0.35,"
            f"afade=t=in:d=1,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[bed]",
            "[bed][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck]",
            "[vo][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        ]
    else:
        fc.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    subprocess.run([
        "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(out),
    ], check=True, capture_output=True)
