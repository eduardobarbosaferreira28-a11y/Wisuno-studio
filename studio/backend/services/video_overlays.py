"""
studio/backend/services/video_overlays.py
==========================================
Subtitle burn-in and branded slide generation.
Uses FFmpeg only — no Pillow/PIL required.

  burn_subtitles()     — drawtext from SRT (no libass required)
  make_lower_third()   — speaker name card (drawtext overlay, first N seconds)
  make_text_slide()    — branded disclaimer / outro card
  concat_with_slides() — join disclaimer + main + outro
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# ── Brand colours ─────────────────────────────────────────────────────────────

_BG      = "0x0D0D0D"   # near-black background
_FG      = "0xFFFFFF"   # white text
_ACCENT  = "0xFF5A00"   # Wisuno orange
_MUTED   = "0x888888"   # secondary text


# ── Font discovery ─────────────────────────────────────────────────────────────

def _font() -> str:
    """Return a fontfile= value escaped for FFmpeg filter syntax, or '' if not found."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            # Escape the colon in drive letter (C:) for FFmpeg filter syntax
            return c.replace(":", "\\:")
    return ""


def _font_opt() -> str:
    f = _font()
    return f"fontfile='{f}':" if f else ""


# ── SRT parser ─────────────────────────────────────────────────────────────────

def _parse_srt(srt_path: Path) -> list[tuple[float, float, str]]:
    """Parse SRT → list of (start_s, end_s, text)."""
    raw = srt_path.read_text(encoding="utf-8", errors="replace")
    cues: list[tuple[float, float, str]] = []

    def _ts(ts: str) -> float:
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s

    for block in re.split(r"\n{2,}", raw.strip()):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if len(lines) < 2:
            continue
        for i, line in enumerate(lines):
            m = re.match(r"([\d:,]+)\s+-->\s+([\d:,]+)", line)
            if m:
                try:
                    start, end = _ts(m.group(1)), _ts(m.group(2))
                except Exception:
                    break
                txt = " ".join(lines[i + 1:]).strip()
                txt = _esc(txt)
                if txt:
                    cues.append((start, end, txt))
                break
    return cues


def _esc(text: str) -> str:
    """Escape a string for FFmpeg drawtext text= value."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'",  "")        # drop single quotes (safest)
        .replace(":",  "\\:")
        .replace("%",  "\\%")
        .replace("\n", " ")
    )


# ── Subtitle burn-in (drawtext, no libass) ─────────────────────────────────────

def burn_subtitles(
    input_path:  Path,
    output_path: Path,
    srt_path:    Path | None,
    width:  int = 1920,
    height: int = 1080,
) -> None:
    """
    Burn-in subtitles using FFmpeg drawtext (no libass needed).
    Falls back to a copy if no SRT is provided or SRT is empty.
    """
    cues = _parse_srt(srt_path) if (srt_path and srt_path.exists()) else []

    if not cues:
        _copy(input_path, output_path)
        return

    fo         = _font_opt()
    font_size  = max(28, int(height * 0.032))   # ~3% of height
    margin_v   = max(60, int(height * 0.075))   # ~7.5% from bottom
    border_w   = max(2,  int(height * 0.003))

    parts = [
        (
            f"drawtext={fo}"
            f"text='{txt}':"
            f"fontsize={font_size}:fontcolor={_FG}:"
            f"borderw={border_w}:bordercolor=black:"
            f"x=(w-text_w)/2:y=h-text_h-{margin_v}:"
            f"enable='between(t,{s:.3f},{e:.3f})'"
        )
        for s, e, txt in cues
    ]

    _encode_with_vf(input_path, output_path, ",".join(parts), copy_audio=True)


# ── Lower-third speaker name ───────────────────────────────────────────────────

def apply_lower_third(
    input_path:   Path,
    output_path:  Path,
    speaker_name: str,
    speaker_title: str = "",
    hold_secs:    float = 5.0,
    width:  int = 1920,
    height: int = 1080,
) -> None:
    """
    Overlay a lower-third name card during the first `hold_secs` seconds.
    Layout: orange bar + name (large) + title (small) at bottom-left.
    """
    if not speaker_name.strip():
        _copy(input_path, output_path)
        return

    fo        = _font_opt()
    name_size = max(32, int(height * 0.038))
    sub_size  = max(22, int(height * 0.026))
    margin_x  = max(60, int(width  * 0.04))
    bar_y     = height - max(130, int(height * 0.14))
    name_y    = bar_y + max(10, int(height * 0.01))
    sub_y     = name_y + name_size + max(6, int(height * 0.006))
    bar_h     = max(4,  int(height * 0.004))
    bar_w     = max(200, int(width * 0.25))

    hold = f"between(t,0,{hold_secs:.1f})"
    name_esc  = _esc(speaker_name)
    title_esc = _esc(speaker_title)

    vf_parts = [
        # Orange accent bar
        f"drawbox=x={margin_x}:y={bar_y}:w={bar_w}:h={bar_h}:color={_ACCENT}:t=fill:enable='{hold}'",
        # Speaker name
        f"drawtext={fo}text='{name_esc}':fontsize={name_size}:fontcolor={_FG}:"
        f"x={margin_x}:y={name_y}:enable='{hold}'",
    ]
    if title_esc:
        vf_parts.append(
            f"drawtext={fo}text='{title_esc}':fontsize={sub_size}:fontcolor={_MUTED}:"
            f"x={margin_x}:y={sub_y}:enable='{hold}'"
        )

    _encode_with_vf(input_path, output_path, ",".join(vf_parts), copy_audio=True)


# ── Branded slide generation (disclaimer / outro) ─────────────────────────────

def make_text_slide(
    output_path: Path,
    heading:     str,
    body:        str = "",
    duration:    float = 4.0,
    width:  int  = 1920,
    height: int  = 1080,
    fps:    int  = 24,
) -> None:
    """
    Generate a branded card as MP4 with silent audio.
    Uses FFmpeg color source + drawtext — no PIL/Pillow required.
    Includes silent 48kHz stereo so it can be concat'd with the main video.
    """
    fo          = _font_opt()
    head_size   = max(38, int(height * 0.044))
    body_size   = max(24, int(height * 0.027))
    accent_h    = max(4,  int(height * 0.004))
    accent_w    = min(width, max(300, int(width * 0.55)))
    center_y    = height // 2
    accent_y    = center_y - head_size - accent_h - 24
    head_y      = center_y - head_size // 2
    body_y      = center_y + head_size // 2 + 24

    head_esc = _esc(heading)
    body_esc = _esc(body)

    vf_parts = [
        f"drawbox=x=(w-{accent_w})/2:y={accent_y}:w={accent_w}:h={accent_h}:color={_ACCENT}:t=fill",
        f"drawtext={fo}text='{head_esc}':fontsize={head_size}:fontcolor={_FG}:x=(w-text_w)/2:y={head_y}",
    ]
    if body_esc:
        # Body text — wrap long lines by splitting on word boundaries
        wrapped = _wrap(body, max_chars=80)
        line_h  = body_size + 8
        for li, line in enumerate(wrapped[:4]):   # max 4 lines
            y = body_y + li * line_h
            vf_parts.append(
                f"drawtext={fo}text='{_esc(line)}':fontsize={body_size}:"
                f"fontcolor={_MUTED}:x=(w-text_w)/2:y={y}"
            )

    vf = ",".join(vf_parts)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={_BG}:s={width}x{height}:r={fps}",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-t", str(duration),
            "-movflags", "+faststart",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


# ── Final concat: slides around main ──────────────────────────────────────────

def concat_with_slides(
    main_path:       Path,
    output_path:     Path,
    disclaimer_path: Path | None,
    outro_path:      Path | None,
    edit_dir:        Path,
) -> None:
    """Concatenate [disclaimer] + main + [outro] into output_path."""
    parts: list[Path] = []
    if disclaimer_path and disclaimer_path.exists():
        parts.append(disclaimer_path)
    parts.append(main_path)
    if outro_path and outro_path.exists():
        parts.append(outro_path)

    if len(parts) == 1:
        _copy(main_path, output_path)
        return

    concat_list = edit_dir / "_slides_concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    concat_list.unlink(missing_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _copy(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(dst)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def _encode_with_vf(src: Path, dst: Path, vf: str, copy_audio: bool = True) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
    ]
    if copy_audio:
        cmd += ["-c:a", "copy"]
    cmd += ["-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _wrap(text: str, max_chars: int = 80) -> list[str]:
    """Simple word-wrap for body text."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 > max_chars:
            if current:
                lines.append(current)
            current = w
        else:
            current = (current + " " + w).strip()
    if current:
        lines.append(current)
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — Graphic slides, background music, audio mix
# ══════════════════════════════════════════════════════════════════════════════

# ── Graphic data slide generation ─────────────────────────────────────────────

_MUSIC_PROMPTS: dict[str, str] = {
    "corporate": (
        "subtle corporate background music, financial news broadcast, "
        "ambient piano, soft pads, very low energy, non-intrusive, instrumental only"
    ),
    "energetic": (
        "upbeat energetic background music, fast-paced financial news reel, "
        "light electronic beats, positive momentum, instrumental"
    ),
    "calm": (
        "calm minimal background music, soft ambient soundscape, peaceful, "
        "corporate wellness, slow tempo, instrumental"
    ),
    "dramatic": (
        "dramatic cinematic underscore, financial news tension, "
        "building orchestral strings, serious mood, instrumental"
    ),
}


def generate_graphic_slides(
    packed_md:  str,
    edit_dir:   Path,
    probe:      dict,
    num_slides: int = 3,
) -> list[dict]:
    """
    Ask Claude to extract N key data points from the transcript, then render
    each as a branded PIL card → 5-second MP4.  Returns a list of dicts:
        [{"path": Path, "label": str, "value": str, "duration": 5.0}, …]
    Falls back to an empty list on any error (non-fatal).
    """
    import json
    import re

    # ── Step 1: Claude extracts data points ───────────────────────────────────
    try:
        import anthropic
        import os
        api_key = os.getenv("ANTHROPIC_API_KEY") or _read_env_key("ANTHROPIC_API_KEY")
        model   = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system="You are a JSON API. Return only a JSON array, no prose.",
            messages=[{
                "role": "user",
                "content": (
                    f"Extract exactly {num_slides} key data points from this market video transcript.\n"
                    "Each should be a short, punchy financial stat.\n\n"
                    f"TRANSCRIPT:\n{packed_md}\n\n"
                    'Return JSON array:\n'
                    '[{"label": "AI Stocks", "value": "+3.2%", "context": "tech rally continues"}]'
                ),
            }],
        )
        raw = resp.content[0].text.strip()
        # Extract first JSON array
        m = re.search(r"\[\s*\{", raw)
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
                        data_points = json.loads(raw[m.start():i + 1])
                        break
            else:
                data_points = []
        else:
            data_points = []
    except Exception as e:
        print(f"[video_overlays] Graphic slide Claude call failed (non-fatal): {e}")
        return []

    if not data_points:
        return []

    # ── Step 2: PIL card rendering ────────────────────────────────────────────
    try:
        from PIL import Image, ImageDraw, ImageFont
        _pil_ok = True
    except ImportError:
        _pil_ok = False

    slides_dir = edit_dir / "slides"
    slides_dir.mkdir(exist_ok=True)

    vid_w = probe.get("width")  or 1920
    vid_h = probe.get("height") or 1080
    vid_fps = int(probe.get("fps") or 24)

    results = []
    for idx, dp in enumerate(data_points[:num_slides]):
        label   = str(dp.get("label",   ""))
        value   = str(dp.get("value",   ""))
        context = str(dp.get("context", ""))

        png_path = slides_dir / f"slide_{idx:02d}.png"
        mp4_path = slides_dir / f"slide_{idx:02d}.mp4"

        if _pil_ok:
            _render_pil_card(png_path, label, value, context, vid_w, vid_h)
        else:
            _render_ffmpeg_card(png_path, label, value, context, vid_w, vid_h)

        # PNG → 5-second MP4 with silent audio
        _png_to_mp4(png_path, mp4_path, duration=5.0, fps=vid_fps, width=vid_w, height=vid_h)
        results.append({
            "path":     mp4_path,
            "label":    label,
            "value":    value,
            "duration": 5.0,
        })

    return results


def _read_env_key(key: str) -> str:
    """Read a key from .env file in the project root."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _render_pil_card(
    out_path: Path,
    label: str, value: str, context: str,
    width: int, height: int,
) -> None:
    """Render a branded data card PNG using PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img  = Image.new("RGB", (width, height), (13, 13, 13))
    draw = ImageDraw.Draw(img)

    # Orange accent bar at top
    draw.rectangle([0, 0, width, 6], fill=(255, 90, 0))

    # Try to get a decent font
    def _load_font(size: int):
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                try:
                    return ImageFont.truetype(c, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    value_font   = _load_font(max(72, int(height * 0.085)))
    label_font   = _load_font(max(28, int(height * 0.034)))
    context_font = _load_font(max(20, int(height * 0.024)))

    cy = height // 2

    # Value (big white number)
    v_bbox = draw.textbbox((0, 0), value, font=value_font)
    v_w, v_h = v_bbox[2] - v_bbox[0], v_bbox[3] - v_bbox[1]
    draw.text(((width - v_w) // 2, cy - v_h - 10), value, font=value_font, fill=(255, 255, 255))

    # Label (gray)
    l_bbox = draw.textbbox((0, 0), label.upper(), font=label_font)
    l_w = l_bbox[2] - l_bbox[0]
    draw.text(((width - l_w) // 2, cy + 16), label.upper(), font=label_font, fill=(136, 136, 136))

    # Context (dim gray)
    if context:
        c_bbox = draw.textbbox((0, 0), context, font=context_font)
        c_w = c_bbox[2] - c_bbox[0]
        draw.text(((width - c_w) // 2, cy + 16 + 44), context, font=context_font, fill=(80, 80, 80))

    # Wisuno branding bottom-right
    brand_font = _load_font(max(18, int(height * 0.022)))
    draw.text((width - 120, height - 40), "wisuno", font=brand_font, fill=(255, 90, 0))

    img.save(str(out_path), "PNG")


def _render_ffmpeg_card(
    out_path: Path,
    label: str, value: str, context: str,
    width: int, height: int,
) -> None:
    """Fallback: render card via FFmpeg drawtext (when PIL is not available)."""
    fo   = _font_opt()
    cy   = height // 2
    vs   = max(72, int(height * 0.085))
    ls   = max(28, int(height * 0.034))
    cs   = max(20, int(height * 0.024))
    val_esc = _esc(value)
    lbl_esc = _esc(label.upper())
    ctx_esc = _esc(context)

    vf_parts = [
        f"drawbox=x=0:y=0:w={width}:h=6:color=0xFF5A00:t=fill",
        f"drawtext={fo}text='{val_esc}':fontsize={vs}:fontcolor=white:x=(w-text_w)/2:y={cy - vs - 10}",
        f"drawtext={fo}text='{lbl_esc}':fontsize={ls}:fontcolor=0x888888:x=(w-text_w)/2:y={cy + 16}",
    ]
    if ctx_esc:
        vf_parts.append(
            f"drawtext={fo}text='{ctx_esc}':fontsize={cs}:fontcolor=0x505050:x=(w-text_w)/2:y={cy + 60}"
        )
    vf_parts.append(
        f"drawtext={fo}text='wisuno':fontsize={max(18,int(height*0.022))}:fontcolor=0xFF5A00:x=w-120:y=h-40"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x0D0D0D:s={width}x{height}:r=1",
            "-vf", ",".join(vf_parts),
            "-frames:v", "1",
            str(out_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def _png_to_mp4(
    png_path: Path, mp4_path: Path,
    duration: float = 5.0, fps: int = 24,
    width: int = 1920, height: int = 1080,
) -> None:
    """Convert a still PNG to a duration-second MP4 with silent audio."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(png_path),
            "-f",    "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:v",  "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-vf",   f"scale={width}:{height}",
            "-c:a",  "aac", "-b:a", "128k", "-ar", "48000",
            "-t",    str(duration),
            "-movflags", "+faststart",
            str(mp4_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


# ── Composite slides into video (concat-insert approach) ──────────────────────

def composite_graphic_slides(
    main_path:   Path,
    slides:      list[dict],
    output_path: Path,
    edit_dir:    Path,
) -> None:
    """
    Insert graphic slides evenly spaced through the video using FFmpeg concat.
    Distributes slides across the middle 80% of the video (avoiding the first
    and last 20% to prevent clashes with lower-third and outro).

    Falls back to a copy if slides is empty or on any error.
    """
    if not slides:
        _copy(main_path, output_path)
        return

    try:
        # Get main video duration
        import json as _json
        probe_out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", str(main_path),
            ],
            stderr=subprocess.DEVNULL,
        )
        main_dur = float(_json.loads(probe_out)["format"]["duration"])

        n = len(slides)
        # Distribute insert points evenly across 20%–80% of video timeline
        spread = main_dur * 0.60
        start_offset = main_dur * 0.20
        insert_points = [
            start_offset + spread * (i / (n + 1))
            for i in range(1, n + 1)
        ]

        # Build segmented concat list
        # Cut the main video at each insert point and interleave slides
        segments_dir = edit_dir / "slides_segments"
        segments_dir.mkdir(exist_ok=True)

        parts: list[Path] = []
        prev = 0.0

        for i, (slide, cut_t) in enumerate(zip(slides, insert_points)):
            # Segment of main video: prev → cut_t
            seg_path = segments_dir / f"seg_{i:02d}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(prev), "-to", str(cut_t),
                    "-i", str(main_path),
                    "-c", "copy",
                    str(seg_path),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            parts.append(seg_path)
            parts.append(slide["path"])
            prev = cut_t

        # Final tail segment: last cut_t → end
        tail_path = segments_dir / "seg_tail.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(prev),
                "-i", str(main_path),
                "-c", "copy",
                str(tail_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        parts.append(tail_path)

        # Concat all parts
        concat_txt = edit_dir / "_graphics_concat.txt"
        concat_txt.write_text(
            "".join(f"file '{p.resolve()}'\n" for p in parts),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_txt),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        concat_txt.unlink(missing_ok=True)

    except Exception as e:
        print(f"[video_overlays] Slide composite failed, falling back to copy: {e}")
        _copy(main_path, output_path)


# ── Background music generation ───────────────────────────────────────────────

def generate_background_music(
    video_duration_s: float,
    style:            str,
    output_path:      Path,
) -> None:
    """
    Generate background music via ElevenLabs Music API and save to output_path (MP3).
    If video is longer than 30s, loops the track to match duration.
    Raises on failure — caller should catch and skip music if desired.
    """
    import os

    api_key = os.getenv("ELEVENLABS_API_KEY") or _read_env_key("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not found in environment or .env")

    prompt       = _MUSIC_PROMPTS.get(style, _MUSIC_PROMPTS["corporate"])
    gen_duration = min(video_duration_s, 30.0)   # ElevenLabs max = 30s

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=api_key)

    # Try Music API first; fall back to SFX API if music endpoint not available
    raw_mp3 = output_path.parent / "_music_raw.mp3"
    try:
        audio_iter = client.music.compose(
            prompt=prompt,
            music_length_ms=int(gen_duration * 1000),
            force_instrumental=True,
            output_format="mp3_44100_128",
        )
        raw_mp3.write_bytes(b"".join(audio_iter))
    except AttributeError:
        # SDK version doesn't have .music — fall back to text_to_sound_effects
        print("[video_overlays] Music API not available in this SDK version, using SFX fallback")
        audio_iter = client.text_to_sound_effects.convert(
            text=prompt,
            duration_seconds=gen_duration,
            prompt_influence=0.5,
        )
        raw_mp3.write_bytes(b"".join(audio_iter))

    # If video is longer than the generated track, loop it
    if video_duration_s > gen_duration + 1.0:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-i", str(raw_mp3),
                "-t", str(video_duration_s),
                "-c", "copy",
                str(output_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        raw_mp3.unlink(missing_ok=True)
    else:
        raw_mp3.rename(output_path)


# ── Audio duck + mix ──────────────────────────────────────────────────────────

def mix_audio_with_music(
    video_path:  Path,
    music_path:  Path,
    output_path: Path,
    music_db:    float = -18.0,
) -> None:
    """
    Mix background music under the voice track:
      - Music ducked to music_db dB
      - Music fades out over the last 3 seconds
      - Voice unchanged at 0 dB
      - Output: AAC 192k
    """
    # Get video duration to calculate fade start
    import json as _json
    probe_out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(video_path),
        ],
        stderr=subprocess.DEVNULL,
    )
    dur = float(_json.loads(probe_out)["format"]["duration"])
    fade_start = max(0.0, dur - 3.0)

    filter_complex = (
        f"[1:a]volume={music_db}dB,"
        f"afade=t=out:st={fade_start:.3f}:d=3[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
