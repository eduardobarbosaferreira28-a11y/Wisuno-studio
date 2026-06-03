"""
Meme generation — uses Gemini 2.5 Flash Image to generate a financial reaction meme image (PNG).
"""
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_IMAGE_MODEL

_EMOTION_STYLE = {
    "panic":     "a stressed trader watching red screens in chaos, wide-eyed panic energy",
    "greed":     "an excited, money-hungry person with dollar signs in their eyes, rubbing hands",
    "confusion": "a confused person scratching their head surrounded by charts and question marks",
    "calm":      "a completely unbothered, zen person relaxing while markets crash around them",
    "disbelief": "a jaw-dropped person staring in shock at a trading screen",
    "euphoria":  "a person celebrating wildly, throwing money, pure unhinged joy",
}


def find_meme(query: str, output_dir: Path, emotion: str = "") -> dict:
    """
    Generate a meme image with Gemini and save it to output_dir.

    Returns:
        {
          "url":        None,          # locally generated — no remote URL
          "local_path": Path,          # saved PNG path
          "source":     "gemini",
          "title":      str,
        }
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")

    prompt = _build_prompt(query, emotion)
    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            mime = part.inline_data.mime_type or "image/png"
            ext = "jpg" if "jpeg" in mime else "png"
            output_dir.mkdir(parents=True, exist_ok=True)
            dest = output_dir / f"meme.{ext}"
            dest.write_bytes(part.inline_data.data)
            return {
                "url":        None,
                "local_path": dest,
                "source":     "gemini",
                "title":      query,
            }

    raise RuntimeError(
        f"Gemini did not return an image for query: '{query}'. "
        "Check your GEMINI_API_KEY or try a different meme_search_query."
    )


def _build_prompt(query: str, emotion: str) -> str:
    style = _EMOTION_STYLE.get(emotion, "an expressive reaction face with trading screens in the background")
    return (
        f"Create a funny internet meme image for a financial trading audience. "
        f"Scene: {style}. "
        f"Context: {query}. "
        f"Style: classic meme format — bold, high-contrast, expressive character. "
        f"Do NOT include any text or captions in the image itself. "
        f"Square composition. Clean white or simple background behind the character."
    )
