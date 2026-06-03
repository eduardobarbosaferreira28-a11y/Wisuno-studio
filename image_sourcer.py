"""
Image sourcing — Google Custom Search API (image search).

Finds one high-quality photo per content slide and downloads it locally.
These images are passed to the Canva builder as right-panel illustrations.

Setup:
  1. Create a Programmable Search Engine at https://programmablesearchengine.google.com
     - Turn ON "Search the entire web" and "Image search"
     - Copy the Search engine ID (cx)
  2. Create an API key at https://console.cloud.google.com → APIs → Custom Search API
     - Enable the "Custom Search API"
     - Copy the key
  3. Add GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID to your .env
"""
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID, REQUEST_TIMEOUT

_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Minimum dimensions to consider an image "high quality"
_MIN_WIDTH  = 800
_MIN_HEIGHT = 600


def search_slide_images(slides: list[dict], market_tag: str, output_dir: Path) -> dict[int, dict]:
    """
    For each content slide, search Google Images for a relevant photo.

    Args:
        slides:     List of slide dicts from the carousel script.
        market_tag: Top-level asset tag (e.g. "GOLD", "EQUITIES").
        output_dir: Folder to save downloaded images.

    Returns:
        Dict mapping slide_number -> image_info dict:
        {
          "url":        str,   # original source URL
          "local_path": Path,  # downloaded file
          "query":      str,   # search query used
        }
        Only includes slides for which an image was successfully found.
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        print("  [images] GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not set — skipping image search")
        return {}

    results: dict[int, dict] = {}
    for slide in slides:
        if slide.get("type") != "content":
            continue

        slide_num = slide["slide_number"]
        query = _build_query(slide, market_tag)
        print(f"  [images] Slide {slide_num}: searching '{query}'")

        img = _search_one(query, output_dir, f"slide_{slide_num:02d}_img")
        if img:
            img["query"] = query
            results[slide_num] = img
            print(f"  [images] Slide {slide_num}: saved {img['local_path'].name}")
        else:
            print(f"  [images] Slide {slide_num}: no result found, slide will be text-only")

    return results


def _build_query(slide: dict, market_tag: str) -> str:
    """Derive a Google Image search query from slide content."""
    headline = slide.get("headline", "")
    icon = slide.get("icon_suggestion", "")

    icon_terms = {
        "chart_up":    "stock market rally chart",
        "chart_down":  "stock market crash chart",
        "dollar":      "dollar currency finance",
        "oil_barrel":  "oil barrel crude petroleum",
        "warning":     "financial risk warning",
        "globe":       "global economy world markets",
        "clock":       "trading session market hours",
        "shield":      "financial regulation compliance",
        "arrow_right": "market momentum growth",
    }
    icon_hint = icon_terms.get(icon, "financial markets")

    return f"{market_tag} {headline} {icon_hint} professional photo"


def _search_one(query: str, output_dir: Path, filename_stem: str) -> dict | None:
    """Run a Google Custom Search and download the first qualifying image."""
    params = {
        "key":        GOOGLE_CSE_API_KEY,
        "cx":         GOOGLE_CSE_ID,
        "q":          query,
        "searchType": "image",
        "imgSize":    "xlarge",
        "imgType":    "photo",
        "safe":       "active",
        "num":        8,
    }

    try:
        resp = requests.get(_CSE_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except requests.RequestException as e:
        print(f"  [images] Google CSE request failed: {e}")
        return None

    for item in items:
        img_meta = item.get("image", {})
        width  = img_meta.get("width",  0)
        height = img_meta.get("height", 0)
        url    = item.get("link", "")

        if not url or width < _MIN_WIDTH or height < _MIN_HEIGHT:
            continue

        local_path = _download(url, output_dir, filename_stem)
        if local_path:
            return {"url": url, "local_path": local_path}

    return None


def _download(url: str, output_dir: Path, filename_stem: str) -> Path | None:
    """Download an image from URL; return local path or None on failure."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    content_type = resp.headers.get("content-type", "")
    if "jpeg" in content_type or "jpg" in content_type:
        ext = "jpg"
    elif "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"
    else:
        # Fall back to URL extension
        suffix = Path(urlparse(url).path).suffix.lstrip(".")
        ext = suffix if suffix in {"jpg", "jpeg", "png", "webp"} else "jpg"

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{filename_stem}.{ext}"

    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return dest
    except OSError:
        return None
