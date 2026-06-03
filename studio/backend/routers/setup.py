"""
studio/backend/routers/setup.py
================================
Dependency checker for Wisuno Studio.
Checks for: FFmpeg, Node.js, HyperFrames, video-use, and API keys in .env
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/setup", tags=["setup"])

# Root of the wisuno-carousel project (two levels up from studio/backend/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
VIDEO_USE_RENDER = PROJECT_ROOT / "studio" / "repos" / "video-use" / "helpers" / "render.py"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 15) -> tuple[bool, str]:
    """Run a subprocess and return (success, output). Uses shell=True on Windows for npm/npx."""
    import platform
    use_shell = (platform.system() == "Windows")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=use_shell,
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except FileNotFoundError:
        return False, "Not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as exc:
        return False, str(exc)


def _read_env() -> dict[str, str]:
    """Read key=value pairs from .env file (without loading into os.environ)."""
    keys: dict[str, str] = {}
    if not ENV_FILE.exists():
        return keys
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            keys[k.strip()] = v.strip()
    return keys


def _write_env_key(key: str, value: str) -> None:
    """Set or update a single key in the .env file."""
    lines = []
    updated = False
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines.append(f"{key}={value}")
                updated = True
            else:
                lines.append(line)
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Check endpoint ─────────────────────────────────────────────────────────────

@router.get("/check")
async def check_dependencies():
    """Return a JSON report of all dependencies and API keys."""
    report: dict[str, dict] = {}

    # ── FFmpeg ──────────────────────────────────────────────────────────────
    ok, out = _run(["ffmpeg", "-version"])
    version = out.splitlines()[0] if ok and out else None
    report["ffmpeg"] = {
        "installed": ok,
        "version": version,
        "required_for": "Video pipeline (crop, composite, audio mix)",
        "install_hint": "Download from https://ffmpeg.org/download.html and add to PATH",
    }

    # ── Node.js ─────────────────────────────────────────────────────────────
    ok, out = _run(["node", "--version"])
    node_ver = out.strip() if ok else None
    node_ok = False
    if ok and node_ver:
        try:
            major = int(node_ver.lstrip("v").split(".")[0])
            node_ok = major >= 18  # allow 18+ (22 LTS recommended)
        except ValueError:
            node_ok = True  # can't parse, assume ok
    report["nodejs"] = {
        "installed": node_ok,
        "version": node_ver,
        "required_for": "HyperFrames HTML→video renderer",
        "install_hint": "Install Node.js 22 LTS from https://nodejs.org",
    }

    # ── HyperFrames ─────────────────────────────────────────────────────────
    # Try `hyperframes --version` directly first (if globally installed)
    hf_ok, hf_out = _run(["hyperframes", "--version"])
    if not hf_ok:
        # Try via npx (may download on first use — use short timeout)
        hf_ok, hf_out = _run(["npx", "--yes", "hyperframes", "--version"], timeout=30)
    report["hyperframes"] = {
        "installed": hf_ok,
        "version": hf_out.splitlines()[0] if hf_ok and hf_out else None,
        "required_for": "Rendering HTML compositions to MP4/MOV",
        "install_hint": "Run: npm install -g hyperframes",
        "can_auto_install": True,
    }

    # ── video-use ───────────────────────────────────────────────────────────
    vu_ok = VIDEO_USE_RENDER.exists()
    report["video_use"] = {
        "installed": vu_ok,
        "version": None,
        "required_for": "Final video composite render (render.py)",
        "install_hint": (
            "Run: git clone https://github.com/browser-use/video-use "
            f"{VIDEO_USE_RENDER.parent.parent.parent}"
        ),
        "path_checked": str(VIDEO_USE_RENDER),
    }

    # ── API Keys ─────────────────────────────────────────────────────────────
    env_vals = _read_env()
    api_keys = {}
    for key, label, required_for in [
        ("ANTHROPIC_API_KEY",  "Claude (Anthropic)",     "Carousel script generation + cut analysis"),
        ("ELEVENLABS_API_KEY", "ElevenLabs",             "Video transcription + music generation"),
        ("GEMINI_API_KEY",     "Google Gemini",          "Carousel image generation"),
        ("HIGGSFIELD_API_KEY", "Higgsfield (optional)",  "Alternative cover image generation"),
        ("GOOGLE_CSE_API_KEY", "Google Search (optional)", "Slide image sourcing"),
    ]:
        val = env_vals.get(key, "")
        is_set = bool(val) and not val.startswith("sk-ant-...") and not val.startswith("your-")
        api_keys[key] = {
            "label": label,
            "set": is_set,
            "required_for": required_for,
            "preview": (val[:8] + "…") if is_set else None,
        }

    # ── Summary ──────────────────────────────────────────────────────────────
    carousel_ready = (
        api_keys["ANTHROPIC_API_KEY"]["set"]
        and api_keys["GEMINI_API_KEY"]["set"]
    )
    video_ready = (
        report["ffmpeg"]["installed"]
        and report["nodejs"]["installed"]
        and report["hyperframes"]["installed"]
        and report["video_use"]["installed"]
        and api_keys["ANTHROPIC_API_KEY"]["set"]
        and api_keys["ELEVENLABS_API_KEY"]["set"]
    )

    return {
        "tools": report,
        "api_keys": api_keys,
        "summary": {
            "carousel_ready": carousel_ready,
            "video_ready": video_ready,
            "all_tools_ok": all(v["installed"] for v in report.values()),
        },
    }


# ── Install HyperFrames ───────────────────────────────────────────────────────

_install_status: dict[str, str] = {"state": "idle", "log": ""}


@router.post("/install-hyperframes")
async def install_hyperframes(background_tasks: BackgroundTasks):
    """Run `npm install -g hyperframes` in the background."""
    if _install_status["state"] == "running":
        return {"status": "already_running"}

    def _do_install():
        _install_status["state"] = "running"
        _install_status["log"] = ""
        import platform
        try:
            result = subprocess.run(
                "npm install -g hyperframes",
                capture_output=True,
                text=True,
                timeout=180,
                shell=True,  # shell=True needed on Windows for npm.cmd
            )
            _install_status["log"] = result.stdout + result.stderr
            _install_status["state"] = "done" if result.returncode == 0 else "error"
        except Exception as exc:
            _install_status["log"] = str(exc)
            _install_status["state"] = "error"

    background_tasks.add_task(_do_install)
    return {"status": "started"}


@router.get("/install-hyperframes/status")
async def install_hyperframes_status():
    return _install_status


# ── Save API key ──────────────────────────────────────────────────────────────

class SaveKeyRequest(BaseModel):
    key: str
    value: str

ALLOWED_KEYS = {
    "ANTHROPIC_API_KEY",
    "ELEVENLABS_API_KEY",
    "GEMINI_API_KEY",
    "HIGGSFIELD_API_KEY",
    "GOOGLE_CSE_API_KEY",
    "GOOGLE_CSE_ID",
}

@router.post("/save-key")
async def save_api_key(req: SaveKeyRequest):
    """Write a single API key to the .env file."""
    if req.key not in ALLOWED_KEYS:
        return JSONResponse({"error": f"Key '{req.key}' is not allowed."}, status_code=400)
    if not req.value.strip():
        return JSONResponse({"error": "Value cannot be empty."}, status_code=400)
    _write_env_key(req.key, req.value.strip())
    return {"ok": True, "key": req.key}
