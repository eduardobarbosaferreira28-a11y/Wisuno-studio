"""
Gemini image wrapper for generating carousel slide images.
Used for cover background images, quote slide backgrounds, and chart visualizations.
"""
import base64
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_BG_IMAGE_MODEL, GEMINI_IMAGE_MODEL
from retry_utils import retry

# All image generation goes through generateContent. The Imagen `predict`
# models (imagen-4.0-generate-001 et al.) are no longer served on the Gemini
# API key, so calling them 404s.
_BG_IMAGE_MODEL = GEMINI_BG_IMAGE_MODEL
# Same family, used for chart stylization.
_FLASH_IMAGE_MODEL = GEMINI_IMAGE_MODEL

# Slide canvas (px) — images never need to be larger than what they render into.
SLIDE_CANVAS = (1080, 1350)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _first_inline_image(response) -> bytes:
    """Pull the first inline image payload out of a generateContent response."""
    candidates = response.candidates or []
    for candidate in candidates:
        content = candidate.content
        for part in (content.parts or []) if content else []:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
    raise RuntimeError("Gemini returned no image data.")


def sniff_image_mime(image_bytes: bytes, default: str = "image/jpeg") -> str:
    """Detect the image type from its magic bytes."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return default


def _to_jpeg(image_bytes: bytes, quality: int = 88) -> bytes:
    """Downscale to the slide canvas and re-encode to JPEG.

    Slide images are inlined into carousel.html as base64 data URIs, so raw
    model output (~1.5 MB PNGs from 2.5-flash-image, ~850 KB JPEGs from
    3.1-flash-image) would bloat the file by a third again per slide. Nothing is
    lost by fitting them to the 1080x1350 canvas they render into. Pillow is
    optional outside the studio, so fall back to the original bytes when it (or
    the decode) is unavailable.
    """
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail(SLIDE_CANVAS, Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes
    try:
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.open(io.BytesIO(image_bytes)).convert("RGB").save(
            buf, format="JPEG", quality=quality, optimize=True
        )
        return buf.getvalue()
    except Exception:
        return image_bytes


_BG_STYLE = (
    " Dark moody financial photography. Deep blacks, dramatic cinematic lighting, "
    "long shadows. No text, no watermarks, no logos. High contrast, editorial quality, "
    "photorealistic. Aspect ratio 3:4 portrait."
)

_CHART_STYLE = (
    " Abstract financial data chart. Pure black background. "
    "Single bright orange line showing price movement with subtle glow. "
    "Very faint dark-grey grid lines. No axis labels, no titles, no watermarks. "
    "Clean, minimal, cinematic. Portrait orientation."
)


def generate_background_image(
    description: str,
    output_path: Path | None = None,
    retries: int = 2,
) -> bytes:
    """Generate a dark background image from a text description."""
    client = _get_client()
    prompt = description.strip().rstrip(".") + "." + _BG_STYLE

    def _call() -> bytes:
        response = client.models.generate_content(
            model=_BG_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="3:4"),
            ),
        )
        image_bytes = _to_jpeg(_first_inline_image(response))
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
        return image_bytes

    try:
        return retry(_call, attempts=retries + 1, base_delay=3.0)
    except Exception as exc:
        raise RuntimeError(
            f"Gemini background image generation failed: {exc}"
        ) from exc


def generate_chart_image(
    chart_asset: str,
    chart_type: str = "line_chart",
    output_path: Path | None = None,
    retries: int = 2,
) -> bytes:
    """Generate a stylized chart image using Gemini 2.5 Flash Image."""
    client = _get_client()
    kind = chart_type.replace("_", " ")
    prompt = (
        f"Create a minimalist abstract {kind} visualization showing {chart_asset} "
        f"price action on a pure black background. Use a single bright orange line "
        f"for the data. No text, no labels, no watermarks. Cinematic and clean."
    )

    def _call() -> bytes:
        response = client.models.generate_content(
            model=_FLASH_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        image_bytes = _first_inline_image(response)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
        return image_bytes

    try:
        return retry(_call, attempts=retries + 1, base_delay=3.0)
    except Exception as exc:
        raise RuntimeError(
            f"Gemini chart image generation failed: {exc}"
        ) from exc


def bytes_to_data_uri(image_bytes: bytes, mime: str | None = None) -> str:
    """Encode raw image bytes as an inline data URI."""
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime or sniff_image_mime(image_bytes)};base64,{b64}"
