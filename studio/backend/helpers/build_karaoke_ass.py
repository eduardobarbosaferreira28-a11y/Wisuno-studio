"""
studio/backend/helpers/build_karaoke_ass.py
============================================
Builds an ASS subtitle file with word-level karaoke highlight tags.

Each word in the EDL ranges is remapped to output timeline coordinates,
grouped into 4-word caption lines, and written with {\\k<cs>} tags so
that one word turns orange at a time.

Usage (called internally by video_service):
    from helpers.build_karaoke_ass import build_karaoke_ass
    build_karaoke_ass(
        transcript_json_path,  # Path to ElevenLabs Scribe JSON
        ranges,                # list of {"source":…,"start":…,"end":…}
        slide_windows,         # list of (start_s, end_s) to skip
        output_ass_path,       # where to write master.ass
        edit_duration_s,       # total edit duration (for ASS header)
    )
"""
from __future__ import annotations
import json
from pathlib import Path


# ── ASS constants ──────────────────────────────────────────────────────────────
# Orange (active) = #F56A21 in BGR ASS = &H00216AF5
# White box uses BorderStyle=3 (opaque background box)
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H001A1A1A,&H00216AF5,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,12,0,2,50,50,290,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

MAX_WORDS_PER_LINE = 4
MAX_CHARS_PER_LINE = 24
WORD_GAP_BREAK = 0.8   # force new line if gap between words > this


def _ts(secs: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc"""
    cs = int(round(secs * 100))
    h  = cs // 360000;   cs %= 360000
    m  = cs // 6000;     cs %= 6000
    s  = cs // 100;      cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _snap_dur(duration: float, fps: float | None) -> float:
    """Round a cut duration to the nearest whole frame at `fps`.

    Must match render.snap_duration_to_frame so the caption output-timeline
    lines up exactly with the frame-locked base video the captions are drawn on.
    Pass fps=None to disable (legacy callers/tests) — leaves timings unchanged.
    """
    if not fps or fps <= 0:
        return duration
    return round(duration * fps) / fps


def build_karaoke_ass(
    transcript_json: Path,
    ranges: list[dict],
    slide_windows: list[tuple[float, float]],
    output_path: Path,
    edit_duration_s: float,
    fps: float | None = None,
) -> list[list[dict]]:
    """Generate master.ass from Scribe transcript + EDL ranges, and return structured lines."""
    # Load word-level transcript
    data  = json.loads(transcript_json.read_text(encoding="utf-8"))
    words = [w for w in data.get("words", []) if w.get("type") == "word"]

    # Remap each word to output timeline
    output_words: list[dict] = []
    accumulated = 0.0

    for rng in ranges:
        r_start = float(rng["start"])
        r_end   = float(rng["end"])
        dur     = r_end - r_start

        range_words = []
        for w in words:
            ws = float(w["start"])
            we = float(w["end"])
            if ws >= r_start and ws < r_end:
                range_words.append(w)
                
        # Check if user manually modified the caption quote
        user_quote = rng.get("quote", "").strip()
        orig_text = " ".join(w["text"] for w in range_words)
        
        if user_quote:
            import string
            def clean(s): return s.translate(str.maketrans('', '', string.punctuation)).lower().split()
            
            user_words = user_quote.split()
            user_clean = clean(user_quote)
            orig_clean = clean(orig_text)
            
            if user_clean != orig_clean and len(user_words) > 0:
                # User edited the caption!
                if len(user_words) == len(range_words):
                    # Same word count: preserve original ElevenLabs timings exactly
                    for i in range(len(range_words)):
                        range_words[i] = {**range_words[i], "text": user_words[i]}
                else:
                    # Different word count: distribute evenly across the cut duration
                    step = dur / len(user_words)
                    range_words = []
                    for i, text in enumerate(user_words):
                        range_words.append({
                            "text": text,
                            "start": r_start + (i * step),
                            "end": r_start + ((i + 1) * step)
                        })
        
        # Remap to output timeline
        for w in range_words:
            ws = float(w["start"])
            we = float(w["end"])
            out_start = accumulated + (ws - r_start)
            out_end   = accumulated + (min(we, r_end) - r_start)
            output_words.append({
                "text":  w["text"].strip(),
                "start": out_start,
                "end":   out_end,
            })

        accumulated += _snap_dur(dur, fps)

    # Filter out words that fall inside a graphic slide window
    def _in_slide(t: float) -> bool:
        return any(t0 <= t < t1 for t0, t1 in slide_windows)

    output_words = [w for w in output_words if not _in_slide(w["start"])]

    if not output_words:
        output_path.write_text(_ASS_HEADER, encoding="utf-8")
        return

    # Group into caption lines
    lines: list[list[dict]] = []
    current: list[dict] = []

    for i, w in enumerate(output_words):
        if current:
            gap = w["start"] - output_words[i - 1]["end"]
            current_text = " ".join(x["text"] for x in current)
            if (
                len(current) >= MAX_WORDS_PER_LINE
                or len(current_text) + len(w["text"]) + 1 > MAX_CHARS_PER_LINE
                or gap > WORD_GAP_BREAK
            ):
                lines.append(current)
                current = []
        current.append(w)
    if current:
        lines.append(current)

    # Write ASS
    events = []
    for line in lines:
        line_start = line[0]["start"]
        line_end   = line[-1]["end"] + 0.15   # small tail padding

        # Build karaoke text: {\\k<cs>}WORD for each word
        karaoke_parts = []
        cursor = line_start
        for w in line:
            # Gap before this word
            gap_cs = int(round((w["start"] - cursor) * 100))
            if gap_cs > 0:
                karaoke_parts.append(f"{{\\k{gap_cs}}}")
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            karaoke_parts.append(f"{{\\kf{dur_cs}}}{w['text'].upper()}")
            cursor = w["end"]

        text = " ".join(karaoke_parts)
        events.append(
            f"Dialogue: 0,{_ts(line_start)},{_ts(line_end)},Default,,0,0,0,,{text}"
        )

    output_path.write_text(_ASS_HEADER + "\n" + "\n".join(events), encoding="utf-8")
    return lines
