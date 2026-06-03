"""
studio/backend/services/history_service.py
==========================================
Manages the studio_log.jsonl history of all completed and failed jobs.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# Project output root
BACKEND_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_FILE = OUTPUT_DIR / "studio_log.jsonl"

def log_job(job_id: str, job_type: str, status: str, details: dict):
    """
    Append a job summary to studio_log.jsonl
    job_type: 'video' or 'carousel'
    status: 'done' or 'error'
    details: Dict containing paths, duration, etc.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "details": details,
    }
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def get_history(limit: int = 100) -> list[dict]:
    """
    Read the latest jobs from studio_log.jsonl, descending order.
    """
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
