"""
Higgsfield text-to-image wrapper for generating carousel cover backgrounds.
Uses the Seedream v4 model via the higgsfield-client SDK.

Drop-in replacement for the equivalent functions in image_generator.py.
The SDK's subscribe() call blocks until the job completes (handles polling
internally), so no manual polling is needed.
"""
import os
import time
from pathlib import Path

import httpx

from config import HIGGSFIELD_API_KEY

# The SDK reads credentials from HF_KEY (preferred) or HF_API_KEY env var.
# We set HF_KEY here so the user only needs HIGGSFIELD_API_KEY in their .env.
if HIGGSFIELD_API_KEY and not os.environ.get("HF_KEY") and not os.environ.get("HF_API_KEY"):
    os.environ["HF_KEY"] = HIGGSFIELD_API_KEY

import higgsfield_client  # noqa: E402  (import after env var is set)

# Seedream v4 — high-quality photorealistic text-to-image
_MODEL = "bytedance/seedream/v4/text-to-image"

_BG_STYLE = (
    " Dark moody financial photography. Deep blacks, dramatic cinematic lighting, "
    "long shadows. No text, no watermarks, no logos. High contrast, editorial quality, "
    "photorealistic."
)


def generate_background_image(
    description: str,
    output_path: Path | None = None,
    retries: int = 2,
) -> bytes:
    """Generate a dark background image from a text description (Higgsfield Seedream v4).

    Matches the signature of image_generator.generate_background_image() so
    html_carousel.py can swap them without any other changes.
    """
    prompt = description.strip().rstrip(".") + "." + _BG_STYLE

    for attempt in range(retries + 1):
        try:
            result = higgsfield_client.subscribe(
                _MODEL,
                arguments={
                    "prompt": prompt,
                    "aspect_ratio": "9:16",   # portrait — closest to the 3:4 canvas
                    "resolution": "2K",
                },
            )
            image_url = result["images"][0]["url"]
            image_bytes = httpx.get(image_url, timeout=60).content

            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_bytes)

            return image_bytes

        except Exception as exc:
            if attempt < retries:
                time.sleep(3)
                continue
            raise RuntimeError(
                f"Higgsfield background image generation failed: {exc}"
            ) from exc
