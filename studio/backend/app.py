"""
studio/backend/app.py
======================
Wisuno Studio — FastAPI application entry point.
Serves the frontend SPA and exposes API routers.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add studio/backend/ to sys.path so `from routers import ...` resolves correctly
BACKEND_DIR = Path(__file__).parent
PROJECT_ROOT = BACKEND_DIR.parent.parent  # wisuno-carousel/

for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dependencies.auth import email_of, get_current_user, is_admin, user_id_of  # noqa: E402
from logging_config import configure_logging  # noqa: E402
from routers import setup as setup_router  # noqa: E402

configure_logging()
logger = logging.getLogger(__name__)


def supabase_project_ref(url: str | None) -> str | None:
    """Return the project ref from a Supabase URL (`https://<ref>.supabase.co`), or None.

    Only the hostname's first label is returned, never the full URL, so nothing
    sensitive can leak into logs.
    """
    if not url:
        return None
    host = urlparse(url.strip()).hostname or ""
    ref = host.split(".", 1)[0]
    return ref or None


def validate_startup_config() -> None:
    """Refuse startup if in non-local environment and Supabase credentials are missing."""
    env = os.getenv("ENV", "").strip().lower()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_anon = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if env != "local":
        if not supabase_url or not supabase_anon:
            logger.error(
                "Refusing startup: Supabase environment variables missing (SUPABASE_URL=%s, SUPABASE_ANON_KEY=%s, ENV=%s)",
                "set" if supabase_url else "missing",
                "set" if supabase_anon else "missing",
                env or "unset",
            )
            raise RuntimeError("Supabase configuration missing in non-local environment")


def log_supabase_project_ref() -> None:
    """Log which Supabase project ref this process uses (ref only, never a key)."""
    from config import SUPABASE_URL

    ref = supabase_project_ref(SUPABASE_URL)
    if ref:
        logger.info("Supabase project ref in use: %s", ref)
    else:
        logger.warning("SUPABASE_URL not set or unparseable; no Supabase project in use")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Wisuno Studio",
    description="Internal tool for carousel and video content production",
    version="1.0.0",
)

# Allow localhost origins (dev comfort — no external access expected)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────

OLD_FRONTEND = BACKEND_DIR.parent / "frontend"

print("Serving Vanilla Frontend")
app.mount("/css", StaticFiles(directory=str(OLD_FRONTEND / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(OLD_FRONTEND / "js")), name="js")


@app.get("/api/config.js")
def get_config_js():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    return Response(
        content=f"window.ENV = {{ SUPABASE_URL: '{url}', SUPABASE_ANON_KEY: '{key}' }};",
        media_type="application/javascript",
    )


@app.get("/api/me")
async def whoami(user: dict = Depends(get_current_user)):
    """Identity + role for the logged-in user, used by the frontend to gate admin-only UI."""
    return {
        "user_id": user_id_of(user),
        "email": email_of(user),
        "is_admin": is_admin(user),
    }


@app.get("/")
async def serve_vanilla_index():
    return FileResponse(
        OLD_FRONTEND / "index.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/login")
async def serve_vanilla_login():
    return FileResponse(OLD_FRONTEND / "login.html")


# ── Routers ───────────────────────────────────────────────────────────────────

from routers import carousel as carousel_router  # noqa: E402
from routers import higgsfield as higgsfield_router
from routers import history as history_router  # noqa: E402
from routers import video as video_router  # noqa: E402

app.include_router(setup_router.router)
app.include_router(carousel_router.router)
app.include_router(video_router.router)
app.include_router(history_router.router)
app.include_router(higgsfield_router.router)


# ── Job Cleanup ───────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    """Validate startup config and cleanup temporary video edit directories older than 7 days."""
    validate_startup_config()
    # Show which Supabase project this process uses (ref only), so local runs can confirm dev.
    log_supabase_project_ref()

    import shutil
    import time

    seven_days_ago = time.time() - (7 * 24 * 60 * 60)
    video_output = PROJECT_ROOT / "output" / "video"
    if video_output.exists():
        for slug_dir in video_output.iterdir():
            if not slug_dir.is_dir():
                continue
            edit_dir = slug_dir / "edit"
            if edit_dir.exists() and edit_dir.is_dir():
                # Check modification time of the edit directory
                if edit_dir.stat().st_mtime < seven_days_ago:
                    try:
                        shutil.rmtree(edit_dir)
                        print(f"[app.py] Cleaned up old temp dir: {edit_dir}")
                    except Exception as e:
                        print(f"[app.py] Failed to clean up {edit_dir}: {e}")


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Wisuno Studio", "version": "1.0.0"}


# ── SPA fallback — serve index.html for all unknown routes ───────────────────


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    target = OLD_FRONTEND / full_path
    if target.exists() and target.is_file():
        return FileResponse(str(target))

    index = OLD_FRONTEND / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)
