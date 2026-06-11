"""
studio/backend/services/history_service.py
==========================================
Manages the studio_log.jsonl history of all completed and failed jobs.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from studio.backend.services.supabase_client import supabase

# Project output root
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_FILE = OUTPUT_DIR / "studio_log.jsonl"

def log_job(job_id: str, job_type: str, status: str, details: dict, user_id: str | None = None):
    """
    Append a job summary to studio_log.jsonl
    job_type: 'video' | 'carousel' | 'gen_image' | 'gen_video'
    status: 'done' or 'error'
    details: Dict containing paths, duration, etc.
    user_id: owning user's id (for per-user dashboard isolation)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "details": details,
        "user_id": user_id,
    }

    if supabase:
        try:
            supabase.table("jobs").insert({
                "id": job_id,
                "job_type": job_type,
                "status": status,
                "details": details,
                "user_id": user_id,
            }).execute()
            # If inserting into Supabase succeeded, we still append to local log for backup
        except Exception as e:
            print(f"Error logging to Supabase: {e}")
            
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def get_history(limit: int = 100, user_id: str | None = None, admin: bool = False) -> list[dict]:
    """
    Read the latest jobs from Supabase or fallback to studio_log.jsonl.
    Non-admins only see their own jobs (filtered by user_id); admins see everything.
    """
    if supabase:
        try:
            query = supabase.table("jobs").select("*")
            if not admin:
                query = query.eq("user_id", user_id)
            res = query.order("created_at", desc=True).limit(limit).execute()
            print(f"DEBUG: Supabase returned {len(res.data)} rows")
            entries = []
            for row in res.data:
                entries.append({
                    "timestamp": row.get("created_at", ""),
                    "job_id": row.get("id", ""),
                    "job_type": row.get("job_type", ""),
                    "status": row.get("status", ""),
                    "details": row.get("details", {}),
                    "user_id": row.get("user_id"),
                })
            return entries
        except Exception as e:
            print(f"Error reading from Supabase: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to local file
            pass

    if not LOG_FILE.exists():
        return []
    
    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    
    # Return latest first
    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return entries[:limit]
