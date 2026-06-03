"""
Export helper — downloads Canva-exported PNGs and writes caption/hashtag file.

After Claude Code executes the Canva MCP tools and calls `export-design`,
it will have a list of page image URLs. Pass those here to download them
and write the Instagram caption file.
"""
from pathlib import Path
import requests
from config import REQUEST_TIMEOUT


def download_slides(page_urls: list[str], output_dir: Path) -> list[Path]:
    """
    Download exported slide images from Canva export URLs.

    Args:
        page_urls: Ordered list of image URLs from Canva's export-design response.
        output_dir: Folder to save slides into.

    Returns:
        List of local file paths, in slide order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for i, url in enumerate(page_urls, start=1):
        ext = "png"
        dest = output_dir / f"slide_{i:02d}.{ext}"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        paths.append(dest)
        print(f"  [export] Saved {dest.name}")

    return paths


def write_caption_file(script: dict, output_dir: Path) -> Path:
    """Write Instagram caption + hashtags to caption.txt."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "caption.txt"

    caption = script.get("caption", "")
    hashtags = script.get("hashtags", [])
    hashtag_str = " ".join(f"#{tag}" for tag in hashtags)

    content = f"{caption}\n\n{hashtag_str}\n"
    dest.write_text(content, encoding="utf-8")
    print(f"  [export] Caption written to {dest.name}")
    return dest


def print_export_summary(output_dir: Path, slide_paths: list[Path], script: dict) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  CAROUSEL READY")
    print(sep)
    print(f"  Title      : {script.get('title', '')}")
    print(f"  Asset      : {script.get('market_tag', '')}")
    print(f"  Slides     : {len(slide_paths)}")
    print(f"  Meme       : {script.get('meme_search_query', '')}")
    print(f"  Output     : {output_dir}")
    print(f"{sep}\n")
