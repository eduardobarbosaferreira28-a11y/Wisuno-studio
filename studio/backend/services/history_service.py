"""
studio/backend/services/history_service.py
==========================================
Manages the studio_log.jsonl history of all completed and failed jobs.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from studio.backend.services.supabase_client import admin_supabase

logger = logging.getLogger(__name__)

# Project output root
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_FILE = OUTPUT_DIR / "studio_log.jsonl"

# Longest error/detail string we'll persist. Renderer failures embed whole subprocess
# dumps, and a multi-KB blob is useless in a dashboard row.
MAX_DETAIL_CHARS = 2000

# ANSI escape sequences (colour codes, cursor moves, the spinner's \x1b[1G\x1b[J) and
# bare control characters. Postgres rejects NUL bytes in jsonb outright, and the rest is
# terminal noise that only corrupts the stored value.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(value):
    """Recursively strip ANSI/control junk from strings in a details payload.

    Subprocess output (notably HyperFrames' Chrome-download spinner) carries raw
    escape sequences that a jsonb column will not accept.
    """
    if isinstance(value, str):
        text = _CTRL_RE.sub("", _ANSI_RE.sub("", value)).strip()
        if len(text) > MAX_DETAIL_CHARS:
            text = text[:MAX_DETAIL_CHARS] + "… (truncated)"
        return text
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def log_job(job_id: str, job_type: str, status: str, details: dict, user_id: str | None = None):
    """
    Append a job summary to studio_log.jsonl
    job_type: 'video' | 'carousel' | 'gen_image' | 'gen_video'
    status: 'done' or 'error'
    details: Dict containing paths, duration, etc.
    user_id: owning user's id (for per-user dashboard isolation)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    details = _clean(details or {})

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "details": details,
        "user_id": user_id,
    }

    if admin_supabase:
        try:
            admin_supabase.table("jobs").insert({
                "id": job_id,
                "job_type": job_type,
                "status": status,
                "details": details,
                "user_id": user_id,
            }).execute()
            # If inserting into Supabase succeeded, we still append to local log for backup
        except Exception:
            # Never swallow this silently: the jobs table is the ONLY durable record
            # (studio_log.jsonl sits on an ephemeral disk and dies with the container).
            logger.exception(
                "[history] Supabase insert failed for job %s (%s/%s) — it will NOT "
                "appear on the dashboard.", job_id, job_type, status,
            )

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def get_history(limit: int = 100, user_id: str | None = None, admin: bool = False) -> list[dict]:
    """
    Read the latest jobs from Supabase or fallback to studio_log.jsonl.
    Non-admins only see their own jobs (filtered by user_id); admins see everything.
    """
    if admin_supabase:
        try:
            # Service-role client bypasses RLS; per-user isolation is enforced here,
            # in Python, by the user_id filter below.
            query = admin_supabase.table("jobs").select("*")
            if not admin:
                query = query.eq("user_id", user_id)
            res = query.order("created_at", desc=True).limit(limit).execute()
            logger.info("[history] Supabase returned %d rows", len(res.data))
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
        except Exception:
            logger.exception("[history] Supabase read failed — falling back to local log.")

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
