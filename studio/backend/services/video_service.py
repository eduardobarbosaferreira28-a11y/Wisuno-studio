"""
studio/backend/services/video_service.py
=========================================
Video pipeline service — 14-step spec per ANTIGRAVITY_REBUILD.md

  STEP 0 — Probe + portrait crop (4K landscape → 1080×1920)
  STEP 1 — Transcribe with ElevenLabs Scribe (cached)
  STEP 2 — Pack transcript to phrase-level markdown
  STEP 3 — AI cut analysis via Claude (returns proposed EDL ranges)
  STEP 4 — [Waiting for human approval]
  STEP 5 — Render:
      A  Build EDL + karaoke ASS subtitles
      B  Extract graded segments
      C  Concat → base.mp4
      D  Render HyperFrames overlays (captions, 3 slides, disclaimer, outro)
      E  Build final edl.json with all overlays
      F  Composite via render.py (graded + overlays + 2-pass loudnorm)
      G  Generate background music (ElevenLabs /v1/music)
      H  Mix audio (amix normalize=0) → final_music.mp4

All output goes to:  wisuno-carousel/output/video/<slug>/edit/
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR   = Path(__file__).parent.parent
STUDIO_DIR    = BACKEND_DIR.parent
PROJECT_ROOT  = STUDIO_DIR.parent
VIDEO_USE_DIR = STUDIO_DIR / "repos" / "video-use"
HELPERS_DIR   = VIDEO_USE_DIR / "helpers"
MY_HELPERS    = BACKEND_DIR / "helpers"

for _p in (str(BACKEND_DIR), str(PROJECT_ROOT), str(HELPERS_DIR), str(MY_HELPERS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.history_service import log_job

VIDEO_OUTPUT_ROOT = PROJECT_ROOT / "output" / "video"

# Portrait crop constants (calibrated for the Wisuno camera setup)
PORTRAIT_CROP_W  = 1215
PORTRAIT_CROP_H  = 2160
PORTRAIT_CROP_X  = 1312   # x offset – centres the speaker
PORTRAIT_CROP_Y  = 0
PORTRAIT_OUT_W   = 1080
PORTRAIT_OUT_H   = 1920

STEP_LABELS = [
    "Probe + portrait crop",
    "Transcribe audio (ElevenLabs Scribe)",
    "Pack transcript",
    "AI cut analysis (Claude)",
    "Waiting for your approval",
    "Render final video",
]

# ── Job store ─────────────────────────────────────────────────────────────────
_jobs: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)


def _make_job(video_path: str) -> dict:
    return {
        "status":        "pending",
        "steps":         [{"label": lbl, "status": "pending"} for lbl in STEP_LABELS],
        "current_step":  -1,
        "video_path":    video_path,
        "portrait_path": None,   # path after portrait crop
        "edit_dir":      None,
        "probe":         None,
        "transcript":    None,
        "packed_md":     None,
        "proposed_cuts": [],
        "approved_cuts": None,
        "edl_path":      None,
        "render_path":   None,
        "error":         None,
    }


def _step_start(job: dict, idx: int):
    job["current_step"] = idx
    job["steps"][idx]["status"] = "running"


def _step_done(job: dict, idx: int, note: str = ""):
    job["steps"][idx]["status"] = "done"
    if note:
        job["steps"][idx]["note"] = note


def _step_error(job: dict, idx: int, msg: str):
    job["steps"][idx]["status"] = "error"
    job["steps"][idx]["error"]  = msg


# ── Public API ─────────────────────────────────────────────────────────────────

def start_analysis(video_path: str) -> str:
    job_id = str(uuid.uuid4())[:10]
    job = _make_job(video_path)
    _jobs[job_id] = job
    _executor.submit(_run_analysis, job_id, video_path)
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def approve_cuts(job_id: str, cuts: list[dict]) -> bool:
    job = _jobs.get(job_id)
    if not job:
        return False
    job["approved_cuts"] = cuts
    job["steps"][4]["status"] = "done"
    job["steps"][4]["note"]   = f"{len(cuts)} cut(s) approved"
    return True


def start_render(
    job_id:           str,
    grade:            str   = "neutral_punch",
    include_music:    bool  = True,
    include_graphics: bool  = True,
    retry_step:       int   | None = None,
) -> bool:
    job = _jobs.get(job_id)
    if not job or job.get("approved_cuts") is None:
        return False
    # If retrying, reset the current step status
    if retry_step is not None and 0 <= retry_step < len(job["steps"]):
        job["steps"][retry_step]["status"] = "pending"
        job["steps"][retry_step].pop("error", None)
        job["error"] = None
        job["status"] = "rendering" if retry_step == 5 else "analysing"

    _executor.submit(_run_render, job_id, grade, include_music, include_graphics)
    return True


# ── Analysis pipeline (steps 0–4) ─────────────────────────────────────────────

def _run_analysis(job_id: str, video_path: str):
    job   = _jobs[job_id]
    vpath = Path(video_path)
    job["status"] = "analysing"

    try:
        slug     = re.sub(r"[^a-z0-9]+", "-", vpath.stem.lower()).strip("-") or "video"
        edit_dir = VIDEO_OUTPUT_ROOT / slug / "edit"
        edit_dir.mkdir(parents=True, exist_ok=True)
        job["edit_dir"] = str(edit_dir)

        # STEP 0 — Probe + portrait crop
        _step_start(job, 0)
        probe = _probe_video(vpath)
        job["probe"] = probe
        w, h = probe.get("width", 0), probe.get("height", 0)

        # If already portrait (1080×1920), skip crop
        if w == PORTRAIT_OUT_W and h == PORTRAIT_OUT_H:
            portrait_path = vpath
            crop_note = "already portrait — skipping crop"
        else:
            portrait_path = edit_dir / f"{vpath.stem}_portrait.mp4"
            if not portrait_path.exists():
                _crop_portrait(vpath, portrait_path)
            crop_note = f"cropped {w}×{h} → {PORTRAIT_OUT_W}×{PORTRAIT_OUT_H}"

        job["portrait_path"] = str(portrait_path)
        # Re-probe portrait to get accurate duration/fps
        probe = _probe_video(portrait_path)
        job["probe"] = probe
        dur_s = probe.get("duration", 0)
        _step_done(job, 0, f"{crop_note} · {dur_s:.1f}s · {probe.get('fps','?')} fps")

        # STEP 1 — Transcribe (uses original vpath for audio, portrait for video)
        _step_start(job, 1)
        transcript_path = _transcribe(vpath, edit_dir)
        job["transcript"] = str(transcript_path)
        kb = transcript_path.stat().st_size / 1024
        _step_done(job, 1, f"Saved {transcript_path.name} ({kb:.0f} KB)")

        # STEP 2 — Pack
        _step_start(job, 2)
        packed_path = _pack_transcripts(edit_dir)
        job["packed_md"] = str(packed_path)
        _step_done(job, 2, f"Packed → {packed_path.name}")

        # STEP 3 — AI Cut Analysis (operates on portrait source)
        _step_start(job, 3)
        cuts = _ai_cut_analysis(portrait_path, edit_dir, probe)
        job["proposed_cuts"] = cuts
        _step_done(job, 3, f"{len(cuts)} proposed cut(s) — {sum(c['end']-c['start'] for c in cuts):.1f}s total")

        # STEP 4 — Await approval
        _step_start(job, 4)
        job["status"] = "awaiting_approval"

    except Exception as exc:
        tb = traceback.format_exc()
        job["status"] = "error"
        job["error"]  = str(exc)
        for step in job["steps"]:
            if step["status"] == "running":
                step["status"] = "error"
        print(f"[video_service] Analysis {job_id} failed:\n{tb}")
        
        try:
            log_job(job_id, "video", "error", {"error": str(exc), "step": "analysis"})
        except Exception:
            pass


def _crop_portrait(src: Path, dst: Path) -> None:
    """FFmpeg portrait crop: 4K landscape → 1080×1920"""
    vf = (
        f"crop={PORTRAIT_CROP_W}:{PORTRAIT_CROP_H}:{PORTRAIT_CROP_X}:{PORTRAIT_CROP_Y},"
        f"scale={PORTRAIT_OUT_W}:{PORTRAIT_OUT_H},setsar=1:1"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dst),
    ], check=True, capture_output=True)


# ── Render pipeline (step 5) ─────────────────────────────────────────────────

def _run_render(
    job_id:           str,
    grade:            str  = "neutral_punch",
    include_music:    bool = True,
    include_graphics: bool = True,
):
    job = _jobs[job_id]
    try:
        portrait_path = Path(job.get("portrait_path") or job["video_path"])
        edit_dir      = Path(job["edit_dir"])
        cuts          = job["approved_cuts"]
        probe         = job.get("probe") or {}
        vid_fps       = int(probe.get("fps") or 30)
        job["status"] = "rendering"

        _step_start(job, 5)

        # Verify HyperFrames is available (hard fail per spec)
        from helpers.hf_render import check_hyperframes
        check_hyperframes()

        # Import render helpers from video-use
        sys.path.insert(0, str(HELPERS_DIR))
        from render import (
            extract_all_segments,
            concat_segments,
            apply_loudnorm_two_pass,
            build_final_composite,
        )
        from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

        # ── A: Build initial EDL (no overlays yet) ─────────────────────────────
        job["steps"][5]["note"] = "[1/8] Building EDL…"
        edl = {
            "version":  1,
            "sources":  {portrait_path.stem: str(portrait_path)},
            "ranges":   cuts,
            "grade":    grade,
            "overlays": [],
        }
        edl_path = edit_dir / "edl.json"
        edl_path.write_text(json.dumps(edl, indent=2))
        job["edl_path"] = str(edl_path)

        # Calculate edit duration (sum of approved cut durations)
        edit_duration = sum(float(c["end"]) - float(c["start"]) for c in cuts)

        # ── B: Build karaoke ASS subtitles ─────────────────────────────────────
        job["steps"][5]["note"] = "[2/8] Building karaoke subtitles…"
        transcript_json = edit_dir / "transcripts" / f"{portrait_path.stem}.json"
        # Also check original stem if portrait stem doesn't match
        if not transcript_json.exists():
            jsons = list((edit_dir / "transcripts").glob("*.json"))
            transcript_json = jsons[0] if jsons else transcript_json

        ass_path = edit_dir / "master.ass"
        # We don't know slide positions yet — build ASS without skipping (we'll refine if needed)
        from helpers.build_karaoke_ass import build_karaoke_ass
        build_karaoke_ass(
            transcript_json=transcript_json,
            ranges=cuts,
            slide_windows=[],   # filled in after graphic slides are placed
            output_path=ass_path,
            edit_duration_s=edit_duration,
        )

        # ── C: Extract graded segments + concat → base.mp4 ────────────────────
        job["steps"][5]["note"] = "[3/8] Extracting & concatenating segments…"
        segment_paths = extract_all_segments(edl, edit_dir, preview=False)
        base_path = edit_dir / "base.mp4"
        concat_segments(segment_paths, base_path, edit_dir)

        # ── D: Render HyperFrames overlays (sequentially) ─────────────────────
        from helpers.build_overlays import (
            build_caption_overlay,
            build_graphic_slides,
            build_disclaimer_overlay,
            build_outro,
        )

        overlays = []  # list of overlay dicts for final EDL

        # D1 — Caption overlay (karaoke captions, transparent MOV)
        job["steps"][5]["note"] = "[4/8] Rendering karaoke captions (HyperFrames)…"
        cap_overlay = build_caption_overlay(ass_path, edit_dir, edit_duration)
        overlays.append({
            "file":            str(cap_overlay.relative_to(edit_dir)),
            "start_in_output": 0.0,
            "duration":        edit_duration,
        })

        # D2 — Graphic slides (3 × 4s opaque MP4)
        slide_overlays = []
        if include_graphics and transcript_json.exists():
            job["steps"][5]["note"] = "[5/8] Rendering AI graphic slides (HyperFrames)…"
            packed_md_text = (edit_dir / "takes_packed.md").read_text(encoding="utf-8") \
                if (edit_dir / "takes_packed.md").exists() else ""
            try:
                slide_overlays = build_graphic_slides(
                    packed_md=packed_md_text,
                    transcript_json=transcript_json,
                    ranges=cuts,
                    edit_dir=edit_dir,
                    anthropic_api_key=ANTHROPIC_API_KEY,
                    anthropic_model=ANTHROPIC_MODEL,
                )
                for so in slide_overlays:
                    overlays.append({
                        "file":            so["file"],
                        "start_in_output": so["start_in_output"],
                        "duration":        4.0,
                    })

                # Rebuild ASS skipping words that fall inside slide windows
                slide_windows = [
                    (so["start_in_output"], so["start_in_output"] + 4.0)
                    for so in slide_overlays
                ]
                build_karaoke_ass(
                    transcript_json=transcript_json,
                    ranges=cuts,
                    slide_windows=slide_windows,
                    output_path=ass_path,
                    edit_duration_s=edit_duration,
                )
                # Re-render captions with updated windows
                build_caption_overlay(ass_path, edit_dir, edit_duration)
            except Exception as gfx_err:
                print(f"[video_service] Graphic slides failed: {gfx_err}")
                raise  # hard fail per spec

        # D3 — Disclaimer overlay (transparent MOV)
        job["steps"][5]["note"] = "[5/8] Rendering disclaimer overlay (HyperFrames)…"
        disc_overlay = build_disclaimer_overlay(edit_dir, edit_duration)
        overlays.append({
            "file":            str(disc_overlay.relative_to(edit_dir)),
            "start_in_output": 0.0,
            "duration":        edit_duration,
        })

        # D4 — Branded outro (5s opaque MP4)
        job["steps"][5]["note"] = "[5/8] Rendering branded outro (HyperFrames)…"
        outro_path = build_outro(edit_dir)
        overlays.append({
            "file":            str(outro_path.relative_to(edit_dir)),
            "start_in_output": edit_duration,
            "duration":        5.0,
        })

        # ── E: Update EDL with all overlays ────────────────────────────────────
        job["steps"][5]["note"] = "[6/8] Writing final EDL with overlays…"
        edl["overlays"] = overlays
        edl_path.write_text(json.dumps(edl, indent=2))

        # ── F: Render composite + 2-pass loudnorm ─────────────────────────────
        job["steps"][5]["note"] = "[6/8] Compositing overlays + loudnorm (render.py)…"
        final_path = edit_dir / "final.mp4"
        build_final_composite(
            base_path,
            [{"file": str((edit_dir / o["file"]).resolve()),
              "start_in_output": o["start_in_output"],
              "duration": o["duration"]}
             for o in overlays],
            None,
            final_path,
            edit_dir,
        )
        normalised = edit_dir / "normalised.mp4"
        apply_loudnorm_two_pass(final_path, normalised, preview=False)
        final_path.unlink(missing_ok=True)
        normalised.rename(final_path)

        # ── G: Generate background music ───────────────────────────────────────
        music_final_path = None
        if include_music:
            job["steps"][5]["note"] = "[7/8] Generating background music (ElevenLabs)…"
            try:
                music_raw  = edit_dir / "music_news_raw.mp3"
                music_proc = edit_dir / "music_news.mp3"
                _generate_music(edit_duration, music_raw)
                _process_music(music_raw, music_proc, edit_duration)
                music_final_path = music_proc
            except Exception as mus_err:
                print(f"[video_service] Music generation failed: {mus_err}")
                raise  # hard fail

        # ── H: Mix audio → final_music.mp4 ────────────────────────────────────
        output_path = edit_dir / "final_music.mp4"
        if music_final_path and music_final_path.exists():
            job["steps"][5]["note"] = "[8/8] Mixing audio…"
            _mix_audio(final_path, music_final_path, output_path)
        else:
            # No music — just copy final.mp4 as the deliverable
            import shutil
            shutil.copy2(str(final_path), str(output_path))

        job["render_path"] = str(output_path)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        _step_done(job, 5, f"final_music.mp4 · {size_mb:.1f} MB · 1080×1920 portrait")
        job["status"] = "done"

        # Log history
        try:
            log_job(
                job_id, "video", "done",
                {"file": f"/api/video/download/{job_id}", "size_mb": size_mb}
            )
        except Exception as e:
            print(f"[video_service] History log failed: {e}")

    except Exception as exc:
        tb = traceback.format_exc()
        job["status"] = "error"
        job["error"]  = str(exc)
        _step_error(job, 5, str(exc))
        print(f"[video_service] Render {job_id} failed:\n{tb}")
        
        # Log error history
        try:
            log_job(job_id, "video", "error", {"error": str(exc)})
        except Exception:
            pass


# ── Music helpers ─────────────────────────────────────────────────────────────

def _generate_music(edit_duration: float, out_path: Path) -> None:
    """Call ElevenLabs /v1/music with exact duration."""
    import os
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set in .env")

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=api_key)

    dur_secs = int(edit_duration)
    prompt = (
        f"news broadcast background music for a {dur_secs} second video, "
        "professional corporate news intro, dramatic orchestral strings with brass, "
        "urgent and dynamic, breaking news style, cinematic instrumental"
    )
    audio = client.music.compose(
        prompt=prompt,
        model_id="music_v1",
        music_length_ms=int(edit_duration * 1000),
        force_instrumental=True,
    )
    # audio is a generator of bytes
    raw = b""
    for chunk in audio:
        if isinstance(chunk, bytes):
            raw += chunk
    out_path.write_bytes(raw)


def _process_music(raw_mp3: Path, out_mp3: Path, edit_duration: float) -> None:
    """
    Apply volume (-18 dB = 0.126), 1s fade-in, 0.5s fade-out at edit_duration.
    Spec: volume=0.126, afade=t=in:st=0:d=1, afade=t=out:st=<edit_dur-0.5>:d=0.5
    """
    fade_out_start = max(0.0, edit_duration - 0.5)
    af = (
        f"volume=0.126,"
        f"afade=t=in:st=0:d=1,"
        f"afade=t=out:st={fade_out_start:.3f}:d=0.5"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_mp3),
        "-af", af,
        str(out_mp3),
    ], check=True, capture_output=True)


def _mix_audio(video_path: Path, music_path: Path, out_path: Path) -> None:
    """
    Mix voice + music using amix normalize=0 (CRITICAL — preserves voice level).
    Spec formula:
      [1:a]volume=0.25[music];[0:a][music]amix=inputs=2:duration=first:normalize=0[aout]
    """
    filter_complex = (
        "[1:a]volume=0.25[music];"
        "[0:a][music]amix=inputs=2:duration=first:normalize=0[aout]"
    )
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ], check=True, capture_output=True)


# ── Helper functions ───────────────────────────────────────────────────────────

def _probe_video(vpath: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(vpath),
    ]
    out    = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    data   = json.loads(out)
    stream = data.get("streams", [{}])[0]
    fmt    = data.get("format", {})

    fps_raw = stream.get("r_frame_rate", "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = round(int(num) / int(den), 2)
    except Exception:
        fps = 0

    return {
        "width":    stream.get("width"),
        "height":   stream.get("height"),
        "fps":      fps,
        "codec":    stream.get("codec_name"),
        "duration": float(fmt.get("duration", 0)),
        "size_mb":  round(int(fmt.get("size", 0)) / (1024 * 1024), 1),
    }


def _transcribe(vpath: Path, edit_dir: Path) -> Path:
    """Call ElevenLabs Scribe via transcribe.py helper. Cached."""
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{vpath.stem}.json"

    if out_path.exists():
        return out_path  # cached

    sys.path.insert(0, str(HELPERS_DIR))
    from transcribe import transcribe_one, load_api_key
    api_key = load_api_key()
    transcribe_one(video=vpath, edit_dir=edit_dir, api_key=api_key, verbose=True)
    return out_path


def _pack_transcripts(edit_dir: Path) -> Path:
    """Run pack_transcripts.py to generate takes_packed.md."""
    sys.path.insert(0, str(HELPERS_DIR))
    from pack_transcripts import pack_one_file, render_markdown

    transcripts_dir = edit_dir / "transcripts"
    json_files      = sorted(transcripts_dir.glob("*.json"))
    entries         = [pack_one_file(p, silence_threshold=0.5) for p in json_files]
    markdown        = render_markdown(entries, silence_threshold=0.5)

    out_path = edit_dir / "takes_packed.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path


def _ai_cut_analysis(vpath: Path, edit_dir: Path, probe: dict) -> list[dict]:
    """Call Claude to propose EDL cuts from the packed transcript."""
    import anthropic
    from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

    packed_md = (edit_dir / "takes_packed.md").read_text(encoding="utf-8")
    duration  = probe.get("duration", 0)

    target_s   = round(duration * 0.50)
    target_min = round(duration * 0.35)
    target_max = round(duration * 0.65)

    prompt = f"""You are a professional social-media video editor. Cut this talking-head video to a tight reel.

VIDEO: {vpath.name}
ORIGINAL DURATION: {duration:.1f}s
SOURCE NAME (use exactly in output): {vpath.stem}

TARGET OUTPUT: {target_s}s  (range: {target_min}–{target_max}s)
Remove roughly half the video. Be aggressive.

TRANSCRIPT (phrase-level with word-boundary timestamps):
{packed_md}

EDITING RULES:
1. CUT: filler words, false starts, repeated phrases, long pauses, tangents
2. KEEP: hooks, key insights, punchy statements, punchlines
3. Every start/end MUST land on a word boundary from the transcript
4. Add 50ms padding before each kept word, 80ms after
5. Prefer silences 400ms+ as cut points — never cut mid-word
6. Segments should be 2–15s each. Avoid one giant uncut block
7. Self-check: your cuts must total {target_min}–{target_max}s before responding

IMPORTANT: Respond with ONLY the JSON array below — no prose, no markdown, no analysis before or after:
[
  {{
    "source": "{vpath.stem}",
    "start": 0.04,
    "end": 4.72,
    "beat": "HOOK",
    "quote": "exact words kept from transcript",
    "reason": "why kept"
  }}
]

Beat labels: HOOK, POINT, EXAMPLE, INSIGHT, TRANSITION, CTA, CLOSING"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=(
            "You are a JSON API for a video editing pipeline. "
            "You MUST respond with ONLY a raw JSON array — no prose, no markdown, "
            "no analysis, no explanations before or after. "
            "Your entire response must be parseable by json.loads()."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.content[0].text.strip()

    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$",        "", raw, flags=re.MULTILINE)
    raw = raw.strip()
    if raw.startswith(("b'", 'b"')):
        raw = raw[1:]
    if raw.startswith("'") and raw.endswith("'"):
        raw = raw[1:-1]

    # Extract JSON array via bracket-depth tracking
    def _find_json_array(text: str) -> str:
        m = re.search(r"\[\s*\{", text)
        if not m:
            preview = text[:400].replace("\n", "\\n")
            raise ValueError(f"No JSON array found. Claude replied: {preview!r}")
        start_idx = m.start()
        depth, in_str, escaped = 0, False, False
        for i, ch in enumerate(text[start_idx:], start_idx):
            if escaped:     escaped = False; continue
            if ch == "\\" and in_str: escaped = True; continue
            if ch == '"':   in_str = not in_str; continue
            if in_str:      continue
            if ch == "[":   depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start_idx:i + 1]
        raise ValueError("Claude returned an incomplete JSON array")

    try:
        json_str = _find_json_array(raw)
        cuts = json.loads(json_str)
    except Exception as parse_err:
        preview = raw[:600].replace("\n", "\\n")
        raise ValueError(
            f"Claude JSON parse failed ({parse_err}). "
            f"Raw response (first 600 chars): {preview}"
        ) from parse_err

    valid = []
    for c in cuts:
        if all(k in c for k in ("source", "start", "end")):
            valid.append({
                "source": str(c["source"]),
                "start":  float(c["start"]),
                "end":    float(c["end"]),
                "beat":   c.get("beat", ""),
                "quote":  c.get("quote", ""),
                "reason": c.get("reason", ""),
            })

    (edit_dir / "proposed_cuts.json").write_text(
        json.dumps(valid, indent=2), encoding="utf-8"
    )
    return valid
