"""
CLI helper to download exported Canva slide PNGs after Claude Code
completes the Canva MCP tool calls.

USAGE:
  python download_slides.py <output_dir> <url1> <url2> ...

EXAMPLE:
  python download_slides.py "output/the-dollar-rises" https://export.canva.com/page1.png https://...
"""
import sys
from pathlib import Path
from exporter import download_slides, print_export_summary
import json


def main():
    if len(sys.argv) < 3:
        print("Usage: python download_slides.py <output_dir> <url1> <url2> ...")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    urls = sys.argv[2:]

    print(f"\nDownloading {len(urls)} slide(s) to {output_dir}…")
    paths = download_slides(urls, output_dir)

    script_file = output_dir / "script.json"
    script = json.loads(script_file.read_text(encoding="utf-8")) if script_file.exists() else {}
    print_export_summary(output_dir, paths, script)


if __name__ == "__main__":
    main()
