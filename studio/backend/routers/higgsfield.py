import os
import json
import uuid
import tempfile
from pathlib import Path
from uuid import UUID
from typing import List, Optional, Dict, Any, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from pydantic import BaseModel
from supabase import create_client, Client

from services import gen_service
from services.supabase_client import upload_to_storage
from dependencies.auth import get_current_user, user_id_of, is_admin

router = APIRouter(prefix="/api/higgsfield", tags=["higgsfield"])

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Get Supabase Client
def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Missing Supabase credentials")
    return create_client(url, key)


def _download_image(url: str) -> Optional[Tuple[bytes, str]]:
    """Fetch an uploaded reference image and return (bytes, mime_type)."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "image/png").split(";")[0].strip()
        if not mime.startswith("image/"):
            mime = "image/png"
        return resp.content, mime
    except Exception as e:  # noqa: BLE001
        print(f"[higgsfield] Failed to download reference image {url}: {e}")
        return None


@router.post("/upload")
async def upload_reference_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload a reference image from the user's computer; returns its public URL."""
    suffix = Path(file.filename or "image.png").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, f"Unsupported image format '{suffix}'. Use: {', '.join(sorted(ALLOWED_IMAGE_EXTS))}")

    asset_id = uuid.uuid4().hex[:12]
    tmp = Path(tempfile.gettempdir()) / f"gen_upload_{asset_id}{suffix}"
    try:
        tmp.write_bytes(await file.read())
        content_type = file.content_type or f"image/{suffix.lstrip('.')}"
        url = upload_to_storage(gen_service.ASSET_BUCKET, f"gen/uploads/{asset_id}{suffix}", str(tmp), content_type)
    finally:
        tmp.unlink(missing_ok=True)

    if not url:
        raise HTTPException(500, "Upload failed: could not store image.")
    return {"url": url}


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    messages: List[ChatMessage] # Full history including the new user message
    reference_image_urls: Optional[List[str]] = None  # Uploaded visual references (this turn)
    context: Optional[str] = None  # Persistent campaign brief / notes for this chat
    web_enabled: bool = False  # Allow Claude to use the native web_search tool

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

    # 3. Format messages for Anthropic. Attach any uploaded reference images to the
    #    latest user turn as image blocks so Claude can see them, and download the
    #    bytes to hand to the Gemini/Veo generators for image-to-image / image-to-video.
    anthropic_msgs: List[Dict[str, Any]] = [{"role": m.role, "content": m.content} for m in req.messages]
    reference_images: List[Tuple[bytes, str]] = []
    if req.reference_image_urls:
        image_blocks = []
        for url in req.reference_image_urls:
            image_blocks.append({"type": "image", "source": {"type": "url", "url": url}})
            downloaded = _download_image(url)
            if downloaded:
                reference_images.append(downloaded)
        # Convert the last user message's plain text into a content-block list + images.
        for i in range(len(anthropic_msgs) - 1, -1, -1):
            if anthropic_msgs[i]["role"] == "user":
                text = anthropic_msgs[i]["content"]
                blocks = image_blocks + ([{"type": "text", "text": text}] if text else [])
                anthropic_msgs[i]["content"] = blocks
                break

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
        "3. Wisuno Brand Guidelines: Neon Orange #FF6700, Obsidian Black #0A0A0A, Cloud Mist #FAFAFA, Urbanist/General Sans fonts. Weave these into your generation prompts. (The brand guideline and the Wisuno logo are also enforced automatically by the system on every generation — they are locked.)\n"
        "4. Disclaimer: The required CFD risk disclaimer is added AUTOMATICALLY to the bottom of every generated image and video by the system. Do NOT ask the model to render any disclaimer text in your prompts, and do NOT include disclaimer text yourself — it is handled for you. Keep the visual area near the bottom edge relatively clean so the disclaimer remains readable.\n"
        "5. Reference images: If the user uploaded an image, it is available to the tools. Use generate_image with use_reference_image=true to edit/restyle it (image-to-image), or generate_video with use_reference_image=true to animate it (image-to-video). Set use_reference_image=false to ignore the upload and generate fresh.\n"
        "6. Web search: When the web_search tool is available, use it to ground requests that need current facts, figures, prices, or trends before generating."
    )

    # Inject the persistent campaign context (if any) so it shapes every prompt this turn.
    if req.context and req.context.strip():
        system_prompt += (
            "\n\nCAMPAIGN CONTEXT (apply this to everything you generate this chat):\n"
            f"{req.context.strip()}"
        )

    started_video_jobs: list = []
    try:
        result = await gen_service.chat(
            anthropic_msgs, system_prompt, session_id=session_id, user_id=uid,
            reference_images=reference_images, web_enabled=req.web_enabled,
        )
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
