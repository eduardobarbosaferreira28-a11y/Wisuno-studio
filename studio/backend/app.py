"""
studio/backend/app.py
======================
Wisuno Studio — FastAPI application entry point.
Serves the frontend SPA and exposes API routers.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add studio/backend/ to sys.path so `from routers import ...` resolves correctly
BACKEND_DIR  = Path(__file__).parent
PROJECT_ROOT = BACKEND_DIR.parent.parent  # wisuno-carousel/

for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from routers import setup as setup_router  # noqa: E402

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

REACT_DIST = BACKEND_DIR.parent / "react-frontend" / "dist"
OLD_FRONTEND = BACKEND_DIR.parent / "frontend"

if REACT_DIST.exists():
    print("Serving React Frontend")
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST / "assets")), name="assets")
    
    @app.get("/api/config.js")
    def get_config_js():
        url = os.getenv("SUPABASE_URL", "https://wkfwjdwjpavgzugwcgte.supabase.co")
        key = os.getenv("SUPABASE_ANON_KEY", "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF")
        return Response(
            content=f"window.ENV = {{ SUPABASE_URL: '{url}', SUPABASE_ANON_KEY: '{key}' }};",
            media_type="application/javascript"
        )
    
    # Provide a catch-all route for SPA navigation
    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_react_app(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        return REACT_DIST / "index.html"
else:
    print("Serving Vanilla Frontend")
    app.mount("/css", StaticFiles(directory=str(OLD_FRONTEND / "css")), name="css")
    app.mount("/js",  StaticFiles(directory=str(OLD_FRONTEND / "js")),  name="js")
    
    @app.get("/")
    async def serve_vanilla_index():
        return FileResponse(OLD_FRONTEND / "index.html")
    @app.get("/login")
    async def serve_vanilla_login():
        return FileResponse(OLD_FRONTEND / "login.html")

# ── Routers ───────────────────────────────────────────────────────────────────

from routers import carousel as carousel_router  # noqa: E402
from routers import video    as video_router     # noqa: E402
from routers import history  as history_router   # noqa: E402

app.include_router(setup_router.router)
app.include_router(carousel_router.router)
app.include_router(video_router.router)
app.include_router(history_router.router)


# ── Job Cleanup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Cleanup temporary video edit directories older than 7 days."""
    import time
    import shutil
    
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
    target = FRONTEND_DIR / full_path
    if target.exists() and target.is_file():
        return FileResponse(str(target))
        
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.get("/")
async def serve_root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)
