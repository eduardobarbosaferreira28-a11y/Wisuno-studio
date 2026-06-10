import os
import json
from uuid import UUID
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from supabase import create_client, Client

from services.higgsfield_service import chat_with_higgsfield

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
async def handle_chat(req: ChatRequest):
    sb = get_supabase()
    session_id = req.session_id

    # 1. Ensure Session exists
    if not session_id:
        # Create a new session
        first_user_msg = next((m.content for m in req.messages if m.role == "user"), "New Chat")
        title = first_user_msg[:50] + "..." if len(first_user_msg) > 50 else first_user_msg
        res = sb.table("chat_sessions").insert({"title": title}).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create session")
        session_id = res.data[0]["id"]
    
    # 2. Get the latest user message to save to DB immediately
    latest_user_message = req.messages[-1]
    sb.table("chat_messages").insert({
        "session_id": session_id,
        "role": latest_user_message.role,
        "content": latest_user_message.content
    }).execute()

    # 3. Format messages for Anthropic
    anthropic_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    
    # 4. Call Higgsfield Service
    system_prompt = (
        "You are the Wisuno Gen Studio AI. You have tools available to generate promotional banners, short promo videos, and manage Soul IDs using Higgsfield AI.\n\n"
        "INTERVIEW MODE (PRE-GENERATION):\n"
        "If the user's request is vague or missing key details (Action/Subject, Visual Style/Lighting, Tone/Audience), DO NOT generate immediately. Instead, ask ONE clarifying question at a time to build the perfect prompt.\n"
        "When asking a question, you MUST provide exactly 3 suggested answers formatted using the following markdown syntax at the end of your response:\n"
        "[Option] First suggested answer\n"
        "[Option] Second suggested answer\n"
        "[Option] Third suggested answer\n\n"
        "SMART DEFAULTS (Do not ask the user for these unless they specify otherwise):\n"
        "- Image Requests: Default to 4:5 Instagram Post format.\n"
        "- Video Requests: Default to 9:16 Reels/TikTok format.\n"
        "- Banner Requests: Default to standard web banner sizes (e.g. 16:9 landscape).\n\n"
        "CRITICAL GENERATION INSTRUCTIONS:\n"
        "1. ALWAYS return the URL to the generated asset in your final response.\n"
        "2. Wisuno Brand Guidelines: Neon Orange #FF6B00, Obsidian Black #0A0A0A, Cloud Mist #FAFAFA, Urbanist/Inter fonts.\n"
        "3. Disclaimer: All generations MUST include the disclaimer text: 'CFD trading carries a high level of risk and may not be suitable for all investors. This content is for educational purposes only and does not constitute financial or investment advice. Regulated by CMA, UAE. Trade responsibly.'\n"
        "4. Disclaimer Placement: Place the disclaimer at the bottom of the asset (bottom: 180px, left: 180px, right: 180px), using a legible font (15px) and a subtle color (#888888)."
    )
    
    try:
        assistant_reply = await chat_with_higgsfield(anthropic_msgs, system_prompt)
    except Exception as e:
        assistant_reply = f"Error communicating with AI: {str(e)}"
        
    # 5. Save assistant reply to DB
    sb.table("chat_messages").insert({
        "session_id": session_id,
        "role": "assistant",
        "content": assistant_reply
    }).execute()
    
    return {
        "session_id": session_id,
        "reply": assistant_reply
    }

@router.get("/sessions")
def get_sessions():
    sb = get_supabase()
    res = sb.table("chat_sessions").select("*").order("updated_at", desc=True).execute()
    return {"sessions": res.data}

@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    sb = get_supabase()
    res = sb.table("chat_messages").select("*").eq("session_id", session_id).order("created_at", desc=False).execute()
    return {"messages": res.data}
