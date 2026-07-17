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
import difflib
import json
import string
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


def _clean(s: str) -> str:
    """Normalise a caption word for comparison: strip punctuation + lowercase."""
    return s.translate(str.maketrans("", "", string.punctuation)).lower()


def words_in_range(words: list[dict], r_start: float, r_end: float) -> list[dict]:
    """Transcript words whose start falls inside [r_start, r_end).

    Single source of truth for range→words selection so the review-step caption
    prefill (transcript_text_for_ranges) and the render (build_karaoke_ass) can
    never diverge on which words belong to a cut.
    """
    return [w for w in words if r_start <= float(w["start"]) < r_end]


def _load_words(transcript_json: Path) -> list[dict]:
    data = json.loads(transcript_json.read_text(encoding="utf-8"))
    return [w for w in data.get("words", []) if w.get("type") == "word"]


def transcript_text_for_ranges(transcript_json: Path, ranges: list[dict]) -> list[str]:
    """Exact transcript caption text per range — the words that will be burned in.

    Used to prefill the review UI's per-cut caption box so what the user sees and
    edits is precisely what the karaoke renderer would otherwise emit verbatim.
    """
    words = _load_words(transcript_json)
    out: list[str] = []
    for rng in ranges:
        rw = words_in_range(words, float(rng["start"]), float(rng["end"]))
        out.append(" ".join(w["text"].strip() for w in rw))
    return out


def align_edit_to_timings(range_words: list[dict], user_words: list[str]) -> list[dict]:
    """Map the user's edited caption words onto the transcript's per-word timings.

    The transcript is the source of truth for timing (this is what keeps the
    karaoke locked to the speaker). We diff the edited text against the transcript
    words and:
      • equal   → keep the transcript timing, show the user's spelling;
      • replace → distribute the edited words evenly across the span of the
                  transcript words they replaced (only that changed span is
                  redistributed — never the whole cut, which was the old drift bug);
      • delete  → drop the words the user removed;
      • insert  → place the added words in the gap between the neighbouring
                  transcript words (borrowing a small slice from an adjacent word
                  when there is no real gap), split evenly.
    """
    orig_clean = [_clean(w["text"]) for w in range_words]
    user_clean = [_clean(u) for u in user_words]
    if orig_clean == user_clean:
        return range_words  # no textual change — keep exact transcript timings

    out: list[dict] = []
    sm = difflib.SequenceMatcher(None, orig_clean, user_clean, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out.append({**range_words[i1 + k], "text": user_words[j1 + k]})
        elif tag == "replace":
            span0 = float(range_words[i1]["start"])
            span1 = float(range_words[i2 - 1]["end"])
            n = j2 - j1
            for k in range(n):
                out.append({
                    "text":  user_words[j1 + k],
                    "start": span0 + (span1 - span0) * k / n,
                    "end":   span0 + (span1 - span0) * (k + 1) / n,
                })
        elif tag == "delete":
            continue  # user removed these words; timing absorbed by neighbours
        elif tag == "insert":
            # Added words with no transcript counterpart. Fill the gap between the
            # previous word's end and the next word's start; if there is no gap,
            # borrow a short slice from the adjacent word so they still show.
            prev_end = float(range_words[i1 - 1]["end"]) if i1 > 0 else None
            next_start = float(range_words[i1]["start"]) if i1 < len(range_words) else None
            if prev_end is not None and next_start is not None:
                g0, g1 = prev_end, next_start
            elif prev_end is not None:
                g0, g1 = prev_end, prev_end + 0.4
            elif next_start is not None:
                g0, g1 = max(0.0, next_start - 0.4), next_start
            else:
                g0, g1 = 0.0, 0.4
            if g1 <= g0:
                g1 = g0 + 0.4  # no real gap — carve a small window
            n = j2 - j1
            for k in range(n):
                out.append({
                    "text":  user_words[j1 + k],
                    "start": g0 + (g1 - g0) * k / n,
                    "end":   g0 + (g1 - g0) * (k + 1) / n,
                })
    return out


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
    words = _load_words(transcript_json)

    # Remap each word to output timeline
    output_words: list[dict] = []
    accumulated = 0.0

    for rng in ranges:
        r_start = float(rng["start"])
        r_end   = float(rng["end"])
        dur     = r_end - r_start

        range_words = words_in_range(words, r_start, r_end)

        # Honor the user's edited caption text from the cut's `quote` field while
        # ALWAYS keeping the transcript's real per-word timings as the skeleton.
        # align_edit_to_timings() diffs the edit against the transcript words:
        # unchanged words keep their exact timing, and only the edited span is
        # redistributed. This is what lets typo fixes AND add/remove/split/merge
        # edits reach the render, without the old even-distribution that made the
        # karaoke drift behind the speaker (see git history / PROJECT_MEMORY.md).
        #
        # Gate on `quote_edited`: the review UI seeds every `quote` with the exact
        # transcript text of its range, so an un-edited quote must be ignored (use
        # the transcript verbatim). Only align when the user actually typed into the
        # caption box — otherwise a pure start/end trim would diff a now-stale quote
        # against the re-scoped range and wrongly add back / drop words.
        user_quote = rng.get("quote", "").strip()
        if user_quote and rng.get("quote_edited"):
            range_words = align_edit_to_timings(range_words, user_quote.split())

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
