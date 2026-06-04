"""
studio/backend/helpers/hf_render.py
=====================================
Thin wrapper to run HyperFrames renders.
Finds npx.cmd via shutil.which and calls it directly as a subprocess list —
no shell=True, no quoting issues, works on Python 3.14+ Windows.
"""
from __future__ import annotations
import gc
import os
import subprocess
import shutil
from pathlib import Path

# Limit Chromium memory usage in headless mode
os.environ.setdefault("PLAYWRIGHT_CHROMIUM_SANDBOX", "0")


def _npx() -> str:
    """Return the full path to npx (npx.cmd on Windows). Raises if not found."""
    path = shutil.which("npx")
    if not path:
        raise RuntimeError(
            "npx not found on PATH. Install Node.js 22 LTS: "
            "winget install OpenJS.NodeJS.LTS"
        )
    return path


def check_hyperframes() -> None:
    """Raise RuntimeError if HyperFrames is not installed."""
    npx = _npx()
    result = subprocess.run(
        [npx, "hyperframes", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "HyperFrames not found. Run: npm install -g hyperframes\n"
            f"Details: {result.stderr.strip()[:300]}"
        )


def render_hyperframes(
    slot_dir: Path,
    output_path: Path,
    fmt: str = "mp4",
) -> None:
    """
    Run: npx hyperframes render <slot_dir> -o <output_path> [--format mov] --quality standard
    Calls npx.cmd directly as a list — no shell, no quoting issues.
    Raises RuntimeError on failure.
    """
    npx = _npx()
    cmd = [
        npx, "hyperframes", "render",
        str(slot_dir.resolve()),
        "-o", str(output_path.resolve()),
        "--quality", "standard",
    ]
    if fmt == "mov":
        cmd += ["--format", "mov"]

    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=str(slot_dir.resolve()),
    )

    # Force garbage collection to release Chromium/Node memory immediately
    gc.collect()

    if result.returncode != 0:
        raise RuntimeError(
            f"HyperFrames render failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout[-600:]}\n"
            f"STDERR: {result.stderr[-600:]}"
        )
