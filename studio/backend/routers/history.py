"""
studio/backend/routers/history.py
==================================
Serves job history for the Dashboard.
"""
from __future__ import annotations

from fastapi import APIRouter
from services.history_service import get_history

router = APIRouter(prefix="/api/history", tags=["history"])

@router.get("")
async def fetch_history(limit: int = 100):
    return {"history": get_history(limit)}
