"""Unit tests for the video-studio karaoke caption builder.

Focus: the caption-edit reconciliation that regressed (edits to a cut's caption
were silently dropped from the rendered video). These tests pin the contract that
a genuine caption edit is honored while the transcript stays the source of truth
for per-word timing, and that an un-edited (prefilled) quote is ignored.
"""
from __future__ import annotations

import json
from pathlib import Path

from helpers.build_karaoke_ass import (
    build_karaoke_ass,
    transcript_text_for_ranges,
)


# ── Fixtures ────────────────────────────────────────────────────────────────────

# "the quick brown fox" — small, no >0.8s gaps so it stays one caption line
# (4-word MAX_WORDS_PER_LINE aside). fox has a small lead gap to give inserts room.
_WORDS = [
    {"type": "word", "text": "the",   "start": 0.0, "end": 0.2},
    {"type": "word", "text": "quick", "start": 0.2, "end": 0.5},
    {"type": "word", "text": "brown", "start": 0.5, "end": 0.8},
    {"type": "word", "text": "fox",   "start": 1.0, "end": 1.3},
]
_RANGE = {"source": "clip", "start": 0.0, "end": 1.5}


def _transcript(tmp_path: Path) -> Path:
    p = tmp_path / "clip.json"
    p.write_text(json.dumps({"words": _WORDS}), encoding="utf-8")
    return p


def _flatten(lines):
    """Flatten the returned list-of-caption-lines into one word list."""
    out = []
    for line in (lines or []):
        out.extend(line)
    return out


def _run(tmp_path, rng):
    ass = tmp_path / "master.ass"
    lines = build_karaoke_ass(
        transcript_json=_transcript(tmp_path),
        ranges=[rng],
        slide_windows=[],
        output_path=ass,
        edit_duration_s=1.5,
        fps=None,
    )
    return _flatten(lines)


# ── transcript_text_for_ranges ──────────────────────────────────────────────────

def test_transcript_text_matches_words_used(tmp_path):
    texts = transcript_text_for_ranges(_transcript(tmp_path), [_RANGE])
    assert texts == ["the quick brown fox"]


# ── No edit: transcript is used verbatim, timings intact ─────────────────────────

def test_no_quote_uses_transcript(tmp_path):
    words = _run(tmp_path, dict(_RANGE))
    assert [w["text"] for w in words] == ["the", "quick", "brown", "fox"]
    assert words[0]["start"] == 0.0
    assert words[3]["start"] == 1.0  # fox keeps its real onset


def test_prefilled_quote_without_flag_is_ignored(tmp_path):
    # The review UI seeds `quote` with the transcript text but does NOT set
    # quote_edited unless the user types. An un-flagged quote (even a divergent
    # one, e.g. after a pure time trim) must fall back to the transcript words.
    rng = {**_RANGE, "quote": "totally different caption words here"}
    words = _run(tmp_path, rng)
    assert [w["text"] for w in words] == ["the", "quick", "brown", "fox"]


# ── Typo fix (same word count): text swapped, timings unchanged ──────────────────

def test_typo_fix_swaps_text_keeps_timing(tmp_path):
    rng = {**_RANGE, "quote": "the quick browne fox", "quote_edited": True}
    words = _run(tmp_path, rng)
    assert [w["text"] for w in words] == ["the", "quick", "browne", "fox"]
    # The edited word keeps the exact transcript timing of the word it replaced.
    assert words[2]["start"] == 0.5
    assert words[3]["start"] == 1.0


# ── Word removed: dropped, neighbours keep exact timing ──────────────────────────

def test_removed_word_is_dropped(tmp_path):
    rng = {**_RANGE, "quote": "the brown fox", "quote_edited": True}
    words = _run(tmp_path, rng)
    assert [w["text"] for w in words] == ["the", "brown", "fox"]
    assert words[1]["start"] == 0.5   # brown keeps its onset
    assert words[2]["start"] == 1.0   # fox keeps its onset


# ── Word added: inserted in the right place, still renders ───────────────────────

def test_added_word_is_inserted(tmp_path):
    rng = {**_RANGE, "quote": "the quick brown red fox", "quote_edited": True}
    words = _run(tmp_path, rng)
    texts = [w["text"] for w in words]
    assert texts == ["the", "quick", "brown", "red", "fox"]
    # The inserted word lands between brown and fox on the output timeline.
    red = words[3]
    assert words[2]["start"] <= red["start"] <= words[4]["start"] + 1e-9
