"""
Brand disclaimer overlay for Gen Studio assets.

Burns the regulatory disclaimer onto every generated image (Pillow) and video
(a Pillow-rendered band composited via FFmpeg). Placement mirrors the Carousel
Studio template — a small, subtle line near the bottom within side margins,
coloured #888888, scaled proportionally to the asset size (carousel reference:
15px / #888888 / line-height 1.55 on a 1080-wide canvas).

A faint dark scrim sits behind the text so the (legally required) disclaimer
stays legible over arbitrary generated imagery — the carousel doesn't need this
because its background is always near-black, but Gen Studio output can be any
colour.
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = (
    "CFD trading carries a high level of risk and may not be suitable for all "
    "investors. This content is for educational purposes only and does not "
    "constitute financial or investment advice. Regulated by CMA, CySEC, FSA & FSC. "
    "Trade responsibly."
)

_TEXT_COLOR  = (136, 136, 136, 255)   # #888888 — matches the carousel disclaimer
_SCRIM_COLOR = (10, 10, 10)           # near-black scrim base (#0A0A0A)

# Font discovery order: Windows (local dev) → Linux (Railway) → macOS.
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int):
    from PIL import ImageFont
    for c in _FONT_CANDIDATES:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Word-wrap `text` so each line fits within `max_w` pixels."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if not current or draw.textlength(trial, font=font) <= max_w:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_band(width: int, height: int):
    """Return an RGBA band (width×height) — transparent except a bottom scrim + disclaimer."""
    from PIL import Image, ImageDraw

    band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(band)

    side_margin   = int(width * 0.08)
    bottom_margin = int(height * 0.045)
    font_size     = max(12, round(width * 0.0139))   # carousel: 15px on 1080w
    line_gap      = round(font_size * 1.55)           # carousel line-height: 1.55
    font          = _load_font(font_size)

    lines   = _wrap(draw, DISCLAIMER_TEXT, font, width - 2 * side_margin)
    block_h = line_gap * len(lines)

    # Gradient scrim (transparent at top → ~65% black at the very bottom).
    scrim_top = max(0, height - bottom_margin - block_h - font_size)
    for y in range(scrim_top, height):
        t = (y - scrim_top) / max(1, height - scrim_top)
        draw.line([(0, y), (width, y)], fill=(*_SCRIM_COLOR, int(165 * t)))

    # Disclaimer text, centred horizontally.
    y = height - bottom_margin - block_h
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((width - w) / 2, y), line, font=font, fill=_TEXT_COLOR)
        y += line_gap

    return band


def overlay_disclaimer_on_image(image_bytes: bytes) -> bytes:
    """Composite the disclaimer band onto an image. Returns PNG bytes."""
    from PIL import Image

    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = base.size
    composed = Image.alpha_composite(base, _render_band(width, height)).convert("RGB")
    buf = io.BytesIO()
    composed.save(buf, format="PNG")
    return buf.getvalue()


def _probe_dims(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        stderr=subprocess.DEVNULL,
    )
    stream = json.loads(out)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def overlay_disclaimer_on_video(input_path: Path, output_path: Path) -> None:
    """Burn the disclaimer band into a video, preserving its audio."""
    width, height = _probe_dims(input_path)
    band = _render_band(width, height)
    band_png = Path(tempfile.gettempdir()) / f"_disc_band_{input_path.stem}.png"
    band.save(str(band_png), "PNG")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-i", str(band_png),
                "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]",
                "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    finally:
        band_png.unlink(missing_ok=True)
