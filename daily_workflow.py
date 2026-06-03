"""
daily_workflow.py
=================
Daily orchestrator for the Wisuno carousel pipeline.

  1. Pick today's top financial article via news_picker.py
  2. Run the full html_carousel.py pipeline on that URL
  3. Log the run to output/daily_log.jsonl and output/latest_run.json

Usage:
  python daily_workflow.py           # standard run
  python daily_workflow.py --dry-run # pick article only, skip carousel build
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Ensure stdout/stderr handle Unicode on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import OUTPUT_DIR
from news_picker import pick_top_article
import html_carousel

# ── Config ────────────────────────────────────────────────────────────────────

MAX_RETRIES    = 2      # retries if news_picker returns nothing
LOG_FILE       = OUTPUT_DIR / "daily_log.jsonl"
LATEST_FILE    = OUTPUT_DIR / "latest_run.json"

SEPARATOR = "═" * 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(entry: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _save_latest(data: dict) -> None:
    LATEST_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    started_at = _now_iso()
    print(f"\n{SEPARATOR}")
    print("  WISUNO DAILY CAROUSEL WORKFLOW")
    print(f"  {datetime.now().strftime('%A, %d %B %Y — %H:%M local')}")
    print(f"{SEPARATOR}\n")

    # ── Step 1: Pick article ──────────────────────────────────────────────────
    print("▶ Step 1 — Picking today's top article…\n")
    article = None
    for attempt in range(1, MAX_RETRIES + 2):
        article = pick_top_article(verbose=True)
        if article:
            break
        if attempt <= MAX_RETRIES:
            print(f"  Retry {attempt}/{MAX_RETRIES} — trying again…\n")

    if not article:
        msg = "No suitable articles found today after all retries. Skipping run."
        print(f"\n  ⚠  {msg}")
        _log({
            "timestamp": started_at,
            "status":    "skipped",
            "reason":    msg,
        })
        return

    print(f"  Title    : {article['title']}")
    print(f"  URL      : {article['url']}")
    print(f"  Source   : {article['source']}")
    print(f"  Score    : {article['score']}")
    print(f"  Rationale: {article.get('rationale', '')}\n")

    if dry_run:
        print("  [dry-run] Skipping carousel generation.")
        _log({
            "timestamp": started_at,
            "status":    "dry_run",
            "article":   article,
        })
        return

    # ── Step 2: Generate carousels ────────────────────────────────────────────
    print("▶ Step 2 — Running carousel pipeline…\n")
    try:
        out_dir = html_carousel.run(url=article["url"])
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"\n  ✗ Carousel pipeline failed: {exc}", file=sys.stderr)
        print(tb, file=sys.stderr)
        _log({
            "timestamp": started_at,
            "status":    "error",
            "article":   article,
            "error":     str(exc),
            "traceback": tb,
        })
        sys.exit(1)

    # ── Step 3: Log success ───────────────────────────────────────────────────
    from html_carousel import LANGUAGES  # noqa — import here to avoid circular at top
    carousel_files = {
        lang: str(out_dir / f"carousel_{lang}.html")
        for lang in LANGUAGES
    }

    log_entry = {
        "timestamp":     started_at,
        "finished_at":   _now_iso(),
        "status":        "success",
        "article":       article,
        "output_dir":    str(out_dir),
        "carousel_files": carousel_files,
    }
    _log(log_entry)
    _save_latest(log_entry)

    print(f"\n{SEPARATOR}")
    print("  ✓ DAILY RUN COMPLETE")
    print(f"  Output : {out_dir}")
    for lang, path in carousel_files.items():
        print(f"  [{lang:5s}] file:///{Path(path).as_posix()}")
    print(f"{SEPARATOR}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Wisuno Daily Carousel Workflow")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pick article only — skip carousel generation.",
    )
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
