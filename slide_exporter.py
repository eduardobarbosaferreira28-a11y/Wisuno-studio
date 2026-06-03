"""
Playwright-based HTML → PNG exporter for Wisuno carousel slides.

Each HTML file is loaded in a headless Chromium browser at exactly 1080×1350 px,
Google Fonts are allowed to load (networkidle wait), then a screenshot is taken.

SETUP (one-time):
  pip install playwright
  playwright install chromium
"""
from pathlib import Path


def export_slides_to_png(
    html_paths: list[Path],
    output_dir: Path,
    filename_prefix: str = "slide",
) -> list[Path]:
    """
    Screenshot a list of HTML files and save as PNGs.

    Args:
        html_paths:      Ordered list of .html slide files.
        output_dir:      Destination folder (created if absent).
        filename_prefix: PNG name prefix — output is <prefix>_01.png, etc.

    Returns:
        List of saved PNG paths in slide order.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed.\n"
            "Run: pip install playwright && playwright install chromium"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    png_paths: list[Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1080, "height": 1350},
            device_scale_factor=1,
        )
        page = context.new_page()

        for i, html_path in enumerate(html_paths, start=1):
            slide_num = f"{i:02d}"
            out_png = output_dir / f"{filename_prefix}_{slide_num}.png"

            # Use file:// URI so local assets (embedded base64) resolve correctly.
            # networkidle waits for Google Fonts to finish loading.
            page.goto(f"file:///{html_path.as_posix()}")
            page.wait_for_load_state("networkidle", timeout=15_000)

            page.screenshot(
                path=str(out_png),
                clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
                type="png",
            )
            png_paths.append(out_png)
            print(f"  ✓ Slide {slide_num} → {out_png.name}")

        browser.close()

    return png_paths
