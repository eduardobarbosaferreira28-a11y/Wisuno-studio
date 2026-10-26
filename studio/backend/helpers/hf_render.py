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


_MANIFEST = "hyperframe.manifest.json"


def _manifest_candidates() -> list[Path]:
    """Where the installed HyperFrames CLI keeps its runtime manifest.

    The CLI looks for it next to its own cli.js, then falls back to a monorepo
    path (<prefix>/core/dist) that never exists in an npm install. A 2026-10-07
    rebuild of the Railway image hit that fallback ("Missing manifest at
    /usr/lib/core/dist/..."), so we locate the file ourselves and pass it in via
    PRODUCER_HYPERFRAME_MANIFEST_PATH.
    """
    out: list[Path] = []
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True,
                              timeout=30, shell=os.name == "nt").stdout.strip()
        if root:
            out.append(Path(root) / "hyperframes" / "dist" / _MANIFEST)
    except Exception:
        pass
    hf_bin = shutil.which("hyperframes")
    if hf_bin:
        out.append(Path(os.path.realpath(hf_bin)).parent / _MANIFEST)
    for prefix in ("/usr/lib", "/usr/local/lib"):
        out.append(Path(prefix) / "node_modules" / "hyperframes" / "dist" / _MANIFEST)
    return out


def _render_env() -> tuple[dict, str]:
    """Env for the render subprocess + a diagnostics string for error messages."""
    env = dict(os.environ)
    if env.get("PRODUCER_HYPERFRAME_MANIFEST_PATH"):
        return env, f"manifest override: {env['PRODUCER_HYPERFRAME_MANIFEST_PATH']}"
    cands = _manifest_candidates()
    found = next((c for c in cands if c.is_file()), None)
    if found:
        env["PRODUCER_HYPERFRAME_MANIFEST_PATH"] = str(found)
        return env, f"manifest: {found}"
    return env, "manifest NOT found; looked in: " + ", ".join(str(c) for c in cands)


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

    env, diag = _render_env()
    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=str(slot_dir.resolve()),
        env=env,
    )

    # Force garbage collection to release Chromium/Node memory immediately
    gc.collect()

    if result.returncode != 0:
        raise RuntimeError(
            f"HyperFrames render failed (exit {result.returncode}) [{diag}]:\n"
            f"STDOUT: {result.stdout[-600:]}\n"
            f"STDERR: {result.stderr[-600:]}"
        )
