"""
Gemini Imagen wrapper for generating carousel slide images.
Used for cover background images, quote slide backgrounds, and chart visualizations.
"""
import base64
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY
from retry_utils import retry

# imagen-4.0 via generate_images API (fast, photorealistic)
_IMAGEN_MODEL = "imagen-4.0-generate-001"
# gemini-2.5-flash-image via generateContent (fallback / chart stylization)
_FLASH_IMAGE_MODEL = "gemini-2.5-flash-image"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


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
    """Generate a dark background image from a text description (Imagen 4)."""
    client = _get_client()
    prompt = description.strip().rstrip(".") + "." + _BG_STYLE

    def _call() -> bytes:
        response = client.models.generate_images(
            model=_IMAGEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4",
                output_mime_type="image/jpeg",
            ),
        )
        image_bytes = response.generated_images[0].image.image_bytes
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
        image_bytes: bytes | None = None
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = base64.b64decode(
                    base64.b64encode(part.inline_data.data)
                ) if isinstance(part.inline_data.data, bytes) else part.inline_data.data
                break

        if not image_bytes:
            raise RuntimeError("Gemini chart image generation returned no image data.")

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


def bytes_to_data_uri(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Encode raw image bytes as an inline data URI."""
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime};base64,{b64}"
