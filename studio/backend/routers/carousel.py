"""
studio/backend/routers/carousel.py
====================================
REST API for the Carousel Studio tool.

POST  /api/carousel/run                        → start job
GET   /api/carousel/status/{job_id}            → poll progress
GET   /api/carousel/download/{job_id}/{lang}/{file_type}  → download file
GET   /api/carousel/caption/{job_id}/{lang}    → get caption text
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from dependencies.auth import get_current_user, user_id_of, is_admin
from services.carousel_service import (
    ALL_LANGUAGES,
    LANGUAGE_FLAGS,
    get_job,
    list_recent,
    start_job,
)

router = APIRouter(prefix="/api/carousel", tags=["carousel"])


# ── Request models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    url:          str | None = None
    text:         str | None = None
    num_slides:   int        = Field(default=6, ge=4, le=8)
    content_type: str        = "market_insight"
    skip_images:  bool       = False
    languages:    list[str]  = ["en"]

    def validate_languages(self) -> list[str]:
        valid = set(ALL_LANGUAGES.keys())
        langs = [lc for lc in self.languages if lc in valid]
        if "en" not in langs:
            langs.insert(0, "en")   # English always required
        return langs


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_carousel(req: RunRequest, user: dict = Depends(get_current_user)):
    """Start a carousel generation job. Returns job_id for polling."""
    if not req.url and not req.text:
        raise HTTPException(400, "Provide either 'url' or 'text'.")

    content_type = req.content_type if req.content_type in (
        "market_insight", "market_update", "educational", "promotional"
    ) else "market_insight"

    languages = req.validate_languages()

    job_id = start_job(
        url=req.url,
        text=req.text,
        num_slides=req.num_slides,
        content_type=content_type,
        skip_images=req.skip_images,
        languages=languages,
        user_id=user_id_of(user),
    )
    return {"job_id": job_id, "languages": languages}


@router.get("/status/{job_id}")
async def job_status(job_id: str, user: dict = Depends(get_current_user)):
    """Poll job progress. Returns steps array + status."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    if job.get("user_id") != user_id_of(user) and not is_admin(user):
        raise HTTPException(404, f"Job '{job_id}' not found.")

    # Build a clean response (don't expose internal paths directly)
    result_files = {}
    for lang, info in job.get("files", {}).items():
        result_files[lang] = {
            "language_name": info["language_name"],
            "flag":          info["flag"],
            "size_kb":       info["size_kb"],
            "carousel_url":  f"/api/carousel/download/{job_id}/{lang}/carousel",
            "caption_url":   f"/api/carousel/download/{job_id}/{lang}/caption",
            "caption_text_url": f"/api/carousel/caption/{job_id}/{lang}",
        }

    return {
        "job_id":       job_id,
        "status":       job["status"],
        "current_step": job["current_step"],
        "steps":        job["steps"],
        "languages":    job["languages"],
        "error":        job.get("error"),
        "files":        result_files,
    }


@router.get("/download/{job_id}/{lang}/{file_type}")
async def download_file(job_id: str, lang: str, file_type: str):
    """Download a carousel HTML or caption TXT file."""
    job = get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Job not ready or not found.")

    lang_files = job.get("files", {}).get(lang)
    if not lang_files:
        raise HTTPException(404, f"No files for language '{lang}'.")

    if file_type == "carousel":
        path = Path(lang_files["carousel_path"])
        filename = lang_files["carousel_filename"]
        media_type = "text/html"
    elif file_type == "caption":
        path = Path(lang_files["caption_path"])
        filename = lang_files["caption_filename"]
        media_type = "text/plain"
    else:
        raise HTTPException(400, "file_type must be 'carousel' or 'caption'.")

    if not path.exists():
        raise HTTPException(404, "File not found on disk.")

    return FileResponse(
        str(path),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/caption/{job_id}/{lang}")
async def get_caption_text(job_id: str, lang: str):
    """Return caption text as plain text for copy-to-clipboard."""
    job = get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Job not ready or not found.")

    lang_files = job.get("files", {}).get(lang)
    if not lang_files:
        raise HTTPException(404, f"No files for language '{lang}'.")

    path = Path(lang_files["caption_path"])
    if not path.exists():
        raise HTTPException(404, "Caption file not found.")

    text = path.read_text(encoding="utf-8")
    return PlainTextResponse(text)


@router.get("/preview/{job_id}/{lang}")
async def preview_carousel(job_id: str, lang: str):
    """Serve carousel HTML inline for iframe preview (no Content-Disposition attachment)."""
    job = get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Job not ready or not found.")

    lang_files = job.get("files", {}).get(lang)
    if not lang_files:
        raise HTTPException(404, f"No files for language '{lang}'.")

    path = Path(lang_files["carousel_path"])
    if not path.exists():
        raise HTTPException(404, "File not found on disk.")

    return FileResponse(str(path), media_type="text/html")


@router.get("/languages")
async def get_languages():
    """Return supported language codes and names."""
    return {
        code: {"name": name, "flag": LANGUAGE_FLAGS.get(code, "🌐")}
        for code, name in ALL_LANGUAGES.items()
    }
