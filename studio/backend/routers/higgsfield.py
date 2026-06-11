import os
import json
from uuid import UUID
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from supabase import create_client, Client

from services import gen_service
from dependencies.auth import get_current_user, user_id_of, is_admin

router = APIRouter(prefix="/api/higgsfield", tags=["higgsfield"])

# Get Supabase Client
def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Missing Supabase credentials")
    return create_client(url, key)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    messages: List[ChatMessage] # Full history including the new user message

@router.post("/chat")
async def handle_chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    sb = get_supabase()
    session_id = req.session_id
    uid = user_id_of(user)

    try:
        # 1. Ensure Session exists (and belongs to this user)
        if not session_id:
            # Create a new session owned by the current user
            first_user_msg = next((m.content for m in req.messages if m.role == "user"), "New Chat")
            title = first_user_msg[:50] + "..." if len(first_user_msg) > 50 else first_user_msg
            res = sb.table("chat_sessions").insert({"title": title, "user_id": uid}).execute()
            if not res.data:
                raise HTTPException(status_code=500, detail="Failed to create session")
            session_id = res.data[0]["id"]
        else:
            # Verify the existing session belongs to this user (admins bypass)
            owner = sb.table("chat_sessions").select("user_id").eq("id", session_id).limit(1).execute()
            if owner.data and owner.data[0].get("user_id") not in (uid, None) and not is_admin(user):
                raise HTTPException(status_code=404, detail="Session not found")

        # 2. Get the latest user message to save to DB immediately
        latest_user_message = req.messages[-1]
        sb.table("chat_messages").insert({
            "session_id": session_id,
            "role": latest_user_message.role,
            "content": latest_user_message.content
        }).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # 3. Format messages for Anthropic
    anthropic_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    
    # 4. Call Higgsfield Service
    system_prompt = (
        "You are the Wisuno Gen Studio AI. You generate marketing visuals using Google's "
        "image and video models via two tools:\n"
        "- generate_image: Nano Banana Pro (Gemini 3). Static images, ready instantly.\n"
        "- generate_video: Veo 3. ~8 second videos with audio; renders asynchronously over "
        "2-4 minutes and appears in the chat automatically when ready.\n\n"
        "INTERVIEW MODE (PRE-GENERATION):\n"
        "If the user's request is vague or missing key details (Action/Subject, Visual Style/Lighting, Tone/Audience), DO NOT generate immediately. Instead, ask ONE clarifying question at a time to build the perfect prompt.\n"
        "When asking a question, you MUST provide exactly 3 suggested answers formatted using the following markdown syntax at the end of your response:\n"
        "[Option] First suggested answer\n"
        "[Option] Second suggested answer\n"
        "[Option] Third suggested answer\n\n"
        "SMART DEFAULTS (Do not ask the user for these unless they specify otherwise):\n"
        "- Image Requests: Default to 4:5 Instagram Post format.\n"
        "- Video Requests: Default to 9:16 Reels/TikTok format.\n"
        "- Banner Requests: Default to 16:9 landscape.\n\n"
        "CRITICAL GENERATION INSTRUCTIONS:\n"
        "1. For images: the tool returns a markdown image link — embed it verbatim in your final reply so it displays.\n"
        "2. For videos: do NOT include any link or placeholder URL. Just tell the user the video is rendering; the app shows it automatically when done.\n"
        "3. Wisuno Brand Guidelines: Neon Orange #FF6B00, Obsidian Black #0A0A0A, Cloud Mist #FAFAFA, Urbanist/Inter fonts. Weave these into your generation prompts.\n"
        "4. Disclaimer: The required CFD risk disclaimer is added AUTOMATICALLY to the bottom of every generated image and video by the system. Do NOT ask the model to render any disclaimer text in your prompts, and do NOT include disclaimer text yourself — it is handled for you. Keep the visual area near the bottom edge relatively clean so the disclaimer remains readable."
    )

    started_video_jobs: list = []
    try:
        result = await gen_service.chat(anthropic_msgs, system_prompt, session_id=session_id, user_id=uid)
        assistant_reply = result["reply"]
        started_video_jobs = result.get("video_jobs", [])
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'exceptions'):
            sub_errs = ", ".join(repr(sub_e) for sub_e in e.exceptions)
            err_msg += f" | Sub-errors: {sub_errs}"
        assistant_reply = f"Error communicating with AI: {err_msg}"

    # 5. Save assistant reply to DB
    try:
        sb.table("chat_messages").insert({
            "session_id": session_id,
            "role": "assistant",
            "content": assistant_reply
        }).execute()
    except Exception as e:
        # We don't want to crash the endpoint if saving the assistant's reply fails,
        # we can just append it to the reply or log it.
        assistant_reply += f"\n\n[Warning: Failed to save reply to history: {str(e)}]"
    
    return {
        "session_id": session_id,
        "reply": assistant_reply,
        "video_jobs": started_video_jobs,
    }


@router.get("/video_status/{job_id}")
def video_status(job_id: str, user: dict = Depends(get_current_user)):
    """Poll the status of an async Veo video render. Persists the finished video to chat history once."""
    job = gen_service.get_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown video job")

    # When the video first completes, save it into the session history so it
    # survives a chat reload. Guarded by `persisted` so we only insert once.
    if job.get("status") == "done" and job.get("url") and not job.get("persisted"):
        sid = job.get("session_id")
        if sid:
            try:
                sb = get_supabase()
                sb.table("chat_messages").insert({
                    "session_id": sid,
                    "role": "assistant",
                    "content": f"![Generated video]({job['url']})",
                }).execute()
            except Exception as e:  # noqa: BLE001
                print(f"[higgsfield] Failed to persist video message: {e}")
        job["persisted"] = True

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "url": job.get("url"),
        "error": job.get("error"),
    }


@router.get("/sessions")
def get_sessions(user: dict = Depends(get_current_user)):
    sb = get_supabase()
    query = sb.table("chat_sessions").select("*")
    if not is_admin(user):
        query = query.eq("user_id", user_id_of(user))
    res = query.order("updated_at", desc=True).execute()
    return {"sessions": res.data}

@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    sb = get_supabase()
    # Verify the session belongs to this user (admins bypass).
    owner = sb.table("chat_sessions").select("user_id").eq("id", session_id).limit(1).execute()
    if owner.data and owner.data[0].get("user_id") not in (user_id_of(user), None) and not is_admin(user):
        raise HTTPException(status_code=404, detail="Session not found")
    res = sb.table("chat_messages").select("*").eq("session_id", session_id).order("created_at", desc=False).execute()
    return {"messages": res.data}
