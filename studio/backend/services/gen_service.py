"""
Gen Studio generation service — Google Gemini backend.

Replaces the previous Higgsfield MCP integration. Gives Claude two local tools:

  - generate_image : Nano Banana Pro (gemini-3-pro-image-preview), with automatic
                     fallback to standard Nano Banana (gemini-2.5-flash-image) when
                     the Pro model is overloaded. Synchronous — returns a public URL.
  - generate_video : Veo 3 (veo-3.0-generate-preview). Asynchronous — starts a
                     background render job and returns a job id immediately. The
                     finished video is polled by the frontend via /video_status.

Generated assets are uploaded to the Supabase `wisuno-assets` bucket (same bucket
used by the carousel and video pipelines) so they survive Railway restarts.
"""
import os
import time
import uuid
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types

from services.supabase_client import upload_to_storage
from services.disclaimer import overlay_disclaimer_on_image, overlay_disclaimer_on_video

logger = logging.getLogger(__name__)

# ── Models ────────────────────────────────────────────────────────────────────
IMAGE_MODEL_PRO   = "gemini-3-pro-image-preview"   # "Nano Banana Pro"
IMAGE_MODEL_FLASH = "gemini-2.5-flash-image"        # "Nano Banana" (fallback)
VIDEO_MODEL       = "veo-3.0-generate-preview"      # Veo 3
CLAUDE_MODEL      = "claude-sonnet-4-6"
ASSET_BUCKET      = "wisuno-assets"

# ── Gemini client (lazy singleton) ────────────────────────────────────────────
_genai_client: Optional[genai.Client] = None


def _client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not found in environment.")
        _genai_client = genai.Client(api_key=key)
    return _genai_client


def _is_overloaded(exc: Exception) -> bool:
    """True for transient 'model overloaded' / rate-limit style errors."""
    text = str(exc).lower()
    return any(s in text for s in ("503", "unavailable", "overloaded", "high demand", "429", "resource_exhausted"))


# ── Video job store (in-memory; the app runs a single uvicorn worker) ──────────
# job_id -> {status: rendering|done|error, url, error, prompt, session_id, persisted}
VIDEO_JOBS: Dict[str, Dict[str, Any]] = {}


def get_video_job(job_id: str) -> Optional[Dict[str, Any]]:
    return VIDEO_JOBS.get(job_id)


# ── Claude tool schemas ───────────────────────────────────────────────────────
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "generate_image",
        "description": (
            "Generate a marketing image from a text prompt using Google's Nano Banana Pro "
            "(Gemini 3) image model. Returns a public URL to the generated PNG. Use this for "
            "banners, social posts, product shots, ad creatives, and any static visual. "
            "The image is ready immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Detailed visual description: subject, style, lighting, composition, "
                        "colour palette, and any exact on-image text to render."
                    ),
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "4:5", "3:4", "9:16", "16:9", "4:3"],
                    "description": "Image aspect ratio. Default 4:5 for Instagram posts.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_video",
        "description": (
            "Generate a short (~8 second) marketing video WITH native audio from a text prompt "
            "using Google's Veo 3 model. This starts an asynchronous render that takes about "
            "2-4 minutes. It returns a job id immediately; the finished video appears in the "
            "chat automatically when ready. Use for Reels, TikToks, promo clips, and ads."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Detailed description of the video: subject, action, camera movement, "
                        "mood, setting, and any spoken dialogue or sound effects."
                    ),
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["9:16", "16:9"],
                    "description": "Video aspect ratio. Default 9:16 for Reels/TikTok.",
                },
            },
            "required": ["prompt"],
        },
    },
]


# ── Image generation (synchronous, blocking — run via asyncio.to_thread) ──────
def _extract_image_bytes(response) -> Optional[bytes]:
    for cand in (response.candidates or []):
        if not cand.content or not cand.content.parts:
            continue
        for part in cand.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                return inline.data
    return None


def _generate_image_blocking(prompt: str, aspect_ratio: str) -> str:
    """Generate an image and return its public Supabase URL. Raises on hard failure."""
    client = _client()
    last_exc: Optional[Exception] = None

    # 1) Try Nano Banana Pro (with aspect-ratio control), retrying transient overloads.
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL_PRO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                ),
            )
            image_bytes = _extract_image_bytes(response)
            if image_bytes:
                return _store_image(image_bytes)
            last_exc = RuntimeError("Pro model returned no image data.")
            break  # non-transient: fall through to fallback model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_overloaded(exc) and attempt < 2:
                time.sleep(4)
                continue
            break

    # 2) Fall back to standard Nano Banana (gemini-2.5-flash-image).
    logger.warning("Nano Banana Pro unavailable (%s); falling back to %s", last_exc, IMAGE_MODEL_FLASH)
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL_FLASH,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            image_bytes = _extract_image_bytes(response)
            if image_bytes:
                return _store_image(image_bytes)
            last_exc = RuntimeError("Fallback model returned no image data.")
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_overloaded(exc) and attempt < 2:
                time.sleep(4)
                continue
            break

    raise RuntimeError(f"Image generation failed: {last_exc}")


def _store_image(image_bytes: bytes) -> str:
    # Burn the regulatory disclaimer onto every generated image.
    try:
        image_bytes = overlay_disclaimer_on_image(image_bytes)
    except Exception:  # noqa: BLE001
        logger.exception("Disclaimer overlay on image failed; storing image without it")

    asset_id = uuid.uuid4().hex[:12]
    tmp = Path(tempfile.gettempdir()) / f"gen_img_{asset_id}.png"
    tmp.write_bytes(image_bytes)
    try:
        url = upload_to_storage(ASSET_BUCKET, f"gen/images/{asset_id}.png", str(tmp), "image/png")
    finally:
        tmp.unlink(missing_ok=True)
    if not url:
        raise RuntimeError("Image was generated but could not be uploaded to storage.")
    return url


# ── Video generation (async job) ──────────────────────────────────────────────
def _generate_video_blocking(prompt: str, aspect_ratio: str, job_id: str) -> str:
    """Generate a Veo 3 video, upload it, and return its public Supabase URL."""
    client = _client()
    operation = client.models.generate_videos(
        model=VIDEO_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            number_of_videos=1,
            generate_audio=True,
        ),
    )

    waited = 0
    while not operation.done:
        time.sleep(10)
        waited += 10
        if waited > 600:  # 10 minute safety cap
            raise TimeoutError("Veo render exceeded 10 minutes.")
        operation = client.operations.get(operation)

    if operation.error:
        raise RuntimeError(f"Veo render failed: {operation.error}")

    generated = (operation.response.generated_videos or []) if operation.response else []
    if not generated:
        reasons = getattr(operation.response, "rai_media_filtered_reasons", None)
        raise RuntimeError(f"Veo returned no video (content may have been filtered). {reasons or ''}".strip())

    video = generated[0].video
    client.files.download(file=video)
    tmp = Path(tempfile.gettempdir()) / f"gen_vid_{job_id}.mp4"
    video.save(str(tmp))

    # Burn the regulatory disclaimer into the rendered video. If the overlay
    # fails, fall back to the original render rather than discarding it.
    tmp_disc = Path(tempfile.gettempdir()) / f"gen_vid_{job_id}_disc.mp4"
    upload_src = tmp
    try:
        overlay_disclaimer_on_video(tmp, tmp_disc)
        upload_src = tmp_disc
    except Exception:  # noqa: BLE001
        logger.exception("Disclaimer overlay on video failed; uploading video without it")

    try:
        url = upload_to_storage(ASSET_BUCKET, f"gen/videos/{job_id}.mp4", str(upload_src), "video/mp4")
    finally:
        tmp.unlink(missing_ok=True)
        tmp_disc.unlink(missing_ok=True)
    if not url:
        raise RuntimeError("Video was rendered but could not be uploaded to storage.")
    return url


async def _run_video_job(job_id: str, prompt: str, aspect_ratio: str) -> None:
    try:
        url = await asyncio.to_thread(_generate_video_blocking, prompt, aspect_ratio, job_id)
        VIDEO_JOBS[job_id].update(status="done", url=url, error=None)
        logger.info("Video job %s finished: %s", job_id, url)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Video job %s failed", job_id)
        VIDEO_JOBS[job_id].update(status="error", url=None, error=str(exc))


# ── Tool execution ────────────────────────────────────────────────────────────
async def _execute_tool(name: str, tool_input: Dict[str, Any], session_id: Optional[str]) -> Tuple[str, Optional[str]]:
    """Run a tool. Returns (text_result_for_claude, started_video_job_id_or_None)."""
    if name == "generate_image":
        prompt = tool_input.get("prompt", "")
        aspect = tool_input.get("aspect_ratio", "4:5")
        try:
            url = await asyncio.to_thread(_generate_image_blocking, prompt, aspect)
            return (
                "Image generated successfully. You MUST embed it in your reply to the user "
                f"using this exact markdown so it displays: ![generated image]({url})",
                None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Image generation failed")
            return (f"Image generation failed: {exc}. Apologise to the user and suggest trying again.", None)

    if name == "generate_video":
        prompt = tool_input.get("prompt", "")
        aspect = tool_input.get("aspect_ratio", "9:16")
        job_id = uuid.uuid4().hex[:12]
        VIDEO_JOBS[job_id] = {
            "status": "rendering",
            "url": None,
            "error": None,
            "prompt": prompt,
            "session_id": session_id,
            "persisted": False,
        }
        asyncio.create_task(_run_video_job(job_id, prompt, aspect))
        return (
            f"Video render started (job {job_id}). It will take 2-4 minutes and will appear in the "
            "chat automatically when ready. Tell the user their video is rendering now. Do NOT include "
            "any markdown link or placeholder URL — the app displays the finished video automatically.",
            job_id,
        )

    return (f"Unknown tool: {name}", None)


# ── Chat entry point ──────────────────────────────────────────────────────────
async def chat(messages: List[Dict[str, Any]], system_prompt: str = "",
               session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the Claude tool-use loop with the Gemini generation tools.
    Returns {"reply": str, "video_jobs": [job_id, ...]}.
    """
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment.")

    anthropic = AsyncAnthropic(api_key=anthropic_api_key)
    current_messages = list(messages)
    started_video_jobs: List[str] = []

    while True:
        response = await anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=current_messages,
            tools=TOOLS,
        )
        current_messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            return {"reply": final_text, "video_jobs": started_video_jobs}

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Claude invoking tool: %s", block.name)
                result_text, vjob = await _execute_tool(block.name, block.input, session_id)
                if vjob:
                    started_video_jobs.append(vjob)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        current_messages.append({"role": "user", "content": tool_results})
