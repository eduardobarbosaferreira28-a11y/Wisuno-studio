"""
studio/backend/routers/video.py
================================
REST API for the Video Studio.

POST  /api/video/upload                      → upload MP4, start analysis job
GET   /api/video/status/{job_id}             → poll progress + proposed cuts
POST  /api/video/approve/{job_id}            → submit approved cuts → start render
GET   /api/video/download/{job_id}           → download final.mp4
"""
from __future__ import annotations

import shutil
import uuid
import glob
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dependencies.auth import get_current_user
from services.video_service import (
    STEP_LABELS,
    VIDEO_OUTPUT_ROOT,
    approve_cuts,
    get_job,
    start_analysis,
    start_render,
)

router = APIRouter(prefix="/api/video", tags=["video"])

UPLOAD_DIR = VIDEO_OUTPUT_ROOT / "_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


# ── Upload & start analysis ───────────────────────────────────────────────────

@router.post("/upload")
async def upload_video(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload an MP4 and start the analysis pipeline. Returns job_id. (Legacy single-file)"""
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported format '{suffix}'. Use: {', '.join(ALLOWED_EXTS)}")

    safe_name  = f"{Path(file.filename or 'video').stem}_{uuid.uuid4().hex[:6]}{suffix}"
    dest_path  = UPLOAD_DIR / safe_name
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    size_mb = dest_path.stat().st_size / (1024 * 1024)
    job_id  = start_analysis(str(dest_path))

    return {
        "job_id":    job_id,
        "filename":  file.filename,
        "size_mb":   round(size_mb, 1),
        "message":   "Analysis started — poll /api/video/status/{job_id}",
    }


# ── Chunked Uploads ───────────────────────────────────────────────────────────

@router.post("/upload_chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Receive a single file chunk and append it to a temporary chunk file."""
    chunk_dir = UPLOAD_DIR / f"_chunks_{upload_id}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = chunk_dir / f"{chunk_index:04d}.part"
    with chunk_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
        
    return {"status": "ok", "chunk_index": chunk_index}


@router.post("/upload_complete")
async def upload_complete(
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    user: dict = Depends(get_current_user)
):
    """Stitch all chunks together, verify count, and start analysis."""
    chunk_dir = UPLOAD_DIR / f"_chunks_{upload_id}"
    if not chunk_dir.exists():
        raise HTTPException(404, "Upload session not found")
        
    # Verify we have all chunks
    parts = sorted(glob.glob(str(chunk_dir / "*.part")))
    if len(parts) != total_chunks:
        raise HTTPException(400, f"Missing chunks: expected {total_chunks}, got {len(parts)}")
        
    suffix = Path(filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported format '{suffix}'. Use: {', '.join(ALLOWED_EXTS)}")
        
    safe_name  = f"{Path(filename or 'video').stem}_{uuid.uuid4().hex[:6]}{suffix}"
    dest_path  = UPLOAD_DIR / safe_name
    
    # Stitch chunks
    with dest_path.open("wb") as dest_file:
        for part_path in parts:
            with open(part_path, "rb") as part_file:
                shutil.copyfileobj(part_file, dest_file)
                
    # Cleanup chunks
    shutil.rmtree(chunk_dir, ignore_errors=True)
    
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    job_id  = start_analysis(str(dest_path))

    return {
        "job_id":    job_id,
        "filename":  filename,
        "size_mb":   round(size_mb, 1),
        "message":   "Analysis started — poll /api/video/status/{job_id}",
    }


# ── Status polling ────────────────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def job_status(job_id: str, user: dict = Depends(get_current_user)):
    """Poll analysis + render progress. Returns steps, proposed cuts, probe info."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")

    return {
        "job_id":         job_id,
        "status":         job["status"],
        "current_step":   job["current_step"],
        "steps":          job["steps"],
        "probe":          job.get("probe"),
        "proposed_cuts":  job.get("proposed_cuts", []),
        "approved_cuts":  job.get("approved_cuts"),
        "render_path":    job.get("render_path"),
        "error":          job.get("error"),
        "download_url":   f"/api/video/download/{job_id}" if job.get("render_path") else None,
    }


# ── Approve cuts & start render ───────────────────────────────────────────────

class ApproveRequest(BaseModel):
    cuts:             list[dict]
    grade:            str  = "neutral_punch"
    include_graphics: bool = True
    include_music:    bool = True


@router.post("/approve/{job_id}")
async def approve_and_render(job_id: str, req: ApproveRequest, user: dict = Depends(get_current_user)):
    """Submit the approved cut list and kick off the full render pipeline."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    if job["status"] not in ("awaiting_approval", "done", "error", "rendering"):
        raise HTTPException(400, f"Job is not ready for approval (status: {job['status']})")

    if not req.cuts:
        raise HTTPException(400, "Cuts list cannot be empty.")

    approve_cuts(job_id, req.cuts)
    started = start_render(
        job_id,
        grade            = req.grade,
        include_graphics = req.include_graphics,
        include_music    = req.include_music,
    )
    if not started:
        raise HTTPException(500, "Failed to start render.")

    total = sum(c["end"] - c["start"] for c in req.cuts)
    return {
        "ok":      True,
        "job_id":  job_id,
        "cuts":    len(req.cuts),
        "total_s": round(total, 1),
        "message": "Render started — poll /api/video/status/{job_id}",
    }


# ── Download final video ──────────────────────────────────────────────────────

@router.get("/download/{job_id}")
async def download_final(job_id: str):
    """Stream the final rendered MP4."""
    job = get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Render not complete or job not found.")

    path = Path(job["render_path"])
    if not path.exists():
        raise HTTPException(404, "Output file not found on disk.")

    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@router.get("/stream/{job_id}")
async def stream_video(job_id: str):
    """Serve the final MP4 for inline <video> playback (supports Range requests)."""
    job = get_job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Render not complete or job not found.")

    path = Path(job["render_path"])
    if not path.exists():
        raise HTTPException(404, "Output file not found on disk.")

    # FileResponse without Content-Disposition: attachment → browser plays inline
    # and FastAPI/Starlette handles Range headers automatically
    return FileResponse(str(path), media_type="video/mp4")


class RetryRequest(BaseModel):
    step_index:       int
    grade:            str  = "neutral_punch"
    include_graphics: bool = True
    include_music:    bool = True

@router.post("/retry/{job_id}")
async def retry_step(job_id: str, req: RetryRequest, user: dict = Depends(get_current_user)):
    """Retry a failed step in the video pipeline."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found.")
    if job["status"] != "error":
        raise HTTPException(400, "Can only retry jobs in 'error' status.")
    
    step_idx = req.step_index
    if not (0 <= step_idx < len(job["steps"])):
        raise HTTPException(400, "Invalid step index.")
    
    if step_idx == 5:
        # Retry render
        if job.get("approved_cuts") is None:
            raise HTTPException(400, "Cuts not approved yet.")
        started = start_render(
            job_id,
            grade=req.grade,
            include_graphics=req.include_graphics,
            include_music=req.include_music,
            retry_step=step_idx
        )
        if not started:
            raise HTTPException(500, "Failed to restart render.")
    else:
        # Retry analysis (for simplicity, we restart analysis since it's cached mostly)
        # Reset steps 0-3
        for i in range(4):
            job["steps"][i]["status"] = "pending"
            job["steps"][i].pop("error", None)
            job["steps"][i].pop("note", None)
        job["status"] = "pending"
        job["error"] = None
        # Call start_analysis again but without redefining the job
        from services.video_service import _executor, _run_analysis
        _executor.submit(_run_analysis, job_id, job["video_path"])
        
    return {"ok": True, "message": "Retrying..."}
