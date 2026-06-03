"""
Generate slide images using Google Gemini Imagen API.
Saves images locally and uploads them to a free hosting service to get public URLs
that can be passed to Canva's upload-asset-from-url tool.

Usage:
    python generate_slide_images.py

Outputs:
    - PNG files in output/the-inflation-monster-returns/images/
    - Prints public URLs for each image
"""
import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OUTPUT_DIR = Path("output/the-inflation-monster-returns/images")

# Image prompts per slide — dark financial editorial style to match Wisuno brand
SLIDE_IMAGES = {
    "cover": (
        "Close-up of a gasoline fuel pump price display showing very high prices, "
        "dramatic dark red atmospheric lighting, professional editorial photography, "
        "dark moody financial news style, near-black background, "
        "high contrast, cinematic quality"
    ),
    "data": (
        "Abstract financial data dashboard with glowing upward red inflation arrows "
        "and percentage numbers on a near-black background, "
        "dark moody financial visualization, professional editorial style, "
        "economic data concept, cinematic lighting"
    ),
    "analysis1": (
        "Oil refinery at night with industrial flares and dramatic dark sky, "
        "global energy supply chain concept, "
        "dark atmospheric professional photography, near-black tones, "
        "orange industrial glow, editorial quality"
    ),
    "analysis2": (
        "Federal Reserve building Washington DC exterior at dusk, "
        "dark dramatic sky, monetary policy concept, "
        "professional editorial photography, near-black tones, "
        "institutional finance theme, cinematic quality"
    ),
}


def generate_imagen4(prompt: str) -> bytes:
    """Generate image using Google Imagen 4 via google-genai SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="3:4",
            safety_filter_level="block_low_and_above",
            output_mime_type="image/png",
        ),
    )
    return response.generated_images[0].image.image_bytes


def generate_gemini_flash_image(prompt: str) -> bytes:
    """Fallback: generate image using gemini-2.5-flash-image."""
    from google import genai
    from google.genai import types
    import base64

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            return base64.b64decode(part.inline_data.data)
    raise ValueError("No image data in Gemini response")


def upload_catbox(image_bytes: bytes, filename: str) -> str:
    """Upload to catbox.moe (free, no auth, permanent) and return public URL."""
    resp = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (filename, image_bytes, "image/png")},
        timeout=60,
    )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"Unexpected catbox response: {url}")
    return url


def upload_litterbox(image_bytes: bytes, filename: str) -> str:
    """Upload to litterbox.catbox.moe (free, 24h expiry) and return public URL."""
    resp = requests.post(
        "https://litterbox.catbox.moe/resources/internals/api.php",
        data={"reqtype": "fileupload", "time": "24h"},
        files={"fileToUpload": (filename, image_bytes, "image/png")},
        timeout=60,
    )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"Unexpected litterbox response: {url}")
    return url


def main() -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    for name, prompt in SLIDE_IMAGES.items():
        print(f"\n[{name}] Generating image...")
        save_path = OUTPUT_DIR / f"{name}.png"

        # Try Imagen 4 first, fall back to Gemini Flash Image
        image_bytes = None
        for attempt, gen_fn in enumerate([generate_imagen4, generate_gemini_flash_image], 1):
            try:
                image_bytes = gen_fn(prompt)
                print(f"  Generated ({['Imagen4', 'Gemini Flash Image'][attempt-1]}), {len(image_bytes):,} bytes")
                break
            except Exception as e:
                print(f"  Attempt {attempt} failed: {e}")

        if not image_bytes:
            print(f"  SKIPPED — could not generate image for {name}")
            continue

        save_path.write_bytes(image_bytes)
        print(f"  Saved: {save_path}")

        # Upload to get public URL
        url = None
        for upload_fn in [upload_catbox, upload_litterbox]:
            try:
                url = upload_fn(image_bytes, f"wisuno_{name}.png")
                print(f"  URL: {url}")
                break
            except Exception as e:
                print(f"  Upload attempt failed: {e}")

        if url:
            results[name] = url
        else:
            print(f"  WARNING: Could not get public URL for {name}")

        time.sleep(1)  # polite rate limiting

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))

    # Save results to file for reference
    results_path = OUTPUT_DIR / "image_urls.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to: {results_path}")

    return results


if __name__ == "__main__":
    main()
