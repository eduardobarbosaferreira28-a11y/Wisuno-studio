"""
studio/backend/services/carousel_service.py
============================================
Carousel pipeline service — wraps the existing html_carousel workflow
with per-step progress tracking and multi-language support.

Supports 5 languages: en, zh-TW, zh-CN, th, sw (Kiswahili)
"""
from __future__ import annotations

import json
import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_DIR.parent.parent          # wisuno-carousel/

for p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Lazy imports from existing carousel codebase ──────────────────────────────
# (imported inside functions to avoid import errors at module load time)

ALL_LANGUAGES = {
    "en":    "English",
    "zh-TW": "Traditional Chinese (繁體中文)",
    "zh-CN": "Simplified Chinese (简体中文)",
    "th":    "Thai (ภาษาไทย)",
    "sw":    "Kiswahili",
}

LANGUAGE_FLAGS = {
    "en":    "🇬🇧",
    "zh-TW": "🇹🇼",
    "zh-CN": "🇨🇳",
    "th":    "🇹🇭",
    "sw":    "🇰🇪",
}

STEP_LABELS = [
    "Fetch & extract article",
    "Generate script with AI",
    "Generate images",
    "Translate to selected languages",
    "Build carousel files",
]

# ── In-memory job store ───────────────────────────────────────────────────────
_jobs: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)


def _make_job(languages: list[str]) -> dict:
    return {
        "status": "pending",   # pending | running | done | error
        "steps": [{"label": lbl, "status": "pending"} for lbl in STEP_LABELS],
        "current_step": -1,
        "languages": languages,
        "error": None,
        "output_dir": None,
        "files": {},           # {lang_code: {carousel, caption, ...}}
    }


def _step_start(job: dict, idx: int):
    job["current_step"] = idx
    job["steps"][idx]["status"] = "running"


def _step_done(job: dict, idx: int):
    job["steps"][idx]["status"] = "done"


def _step_error(job: dict, idx: int, msg: str):
    job["steps"][idx]["status"] = "error"
    job["steps"][idx]["error"] = msg


# ── Public API ────────────────────────────────────────────────────────────────

def start_job(
    *,
    url: str | None,
    text: str | None,
    num_slides: int,
    content_type: str,
    skip_images: bool,
    languages: list[str],
) -> str:
    job_id = str(uuid.uuid4())
    job = _make_job(languages)
    _jobs[job_id] = job
    _executor.submit(_run, job_id, url, text, num_slides, content_type, skip_images, languages)
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_recent(limit: int = 20) -> list[dict]:
    items = [{"job_id": jid, **j} for jid, j in _jobs.items()]
    return items[-limit:]


# ── Pipeline runner (executes in thread pool) ─────────────────────────────────

def _run(job_id: str, url, text, num_slides, content_type, skip_images, languages):
    job = _jobs[job_id]
    job["status"] = "running"

    try:
        # ── Lazy imports ──────────────────────────────────────────────────────
        import html_carousel as _hc
        from config import OUTPUT_DIR
        from content_extractor import extract_from_url, extract_from_text
        from swipeable_carousel import build_swipeable_html

        # ── STEP 1 — Extract article ──────────────────────────────────────────
        _step_start(job, 0)
        if url:
            article_text = extract_from_url(url)
            en_script = None
        elif text:
            article_text = extract_from_text(text)
            en_script = None
        else:
            raise ValueError("Provide either a URL or article text.")
        _step_done(job, 0)

        # ── STEP 2 — Generate English script ──────────────────────────────────
        _step_start(job, 1)
        en_script = _hc.generate_script(article_text, num_slides, content_type=content_type)
        job["topic"] = en_script.get("title", "Carousel")
        _step_done(job, 1)

        # Set up output directory
        slug = _hc._slugify(en_script.get("title", "carousel"))
        output_dir = OUTPUT_DIR / slug
        images_dir = output_dir / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "script.json").write_text(
            json.dumps(en_script, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _hc._save_caption(en_script, output_dir / "caption_en.txt")

        # ── STEP 3 — Generate images ──────────────────────────────────────────
        _step_start(job, 2)
        if skip_images:
            slide_images: dict[int, str] = {}
            job["steps"][2]["status"] = "done"
            job["steps"][2]["note"]   = "Skipped (skip_images=true)"
        else:
            images_dir.mkdir(parents=True, exist_ok=True)
            try:
                slide_images = _hc.generate_slide_images(en_script, images_dir)
                if not slide_images:
                    job["steps"][2]["note"] = "⚠ No images returned — text-only slides"
            except Exception as img_err:
                # Don't fail the whole job — continue with no images
                slide_images = {}
                job["steps"][2]["note"] = f"⚠ Image generation failed: {img_err}"
                print(f"[carousel_service] Image generation error (non-fatal): {img_err}")
        _step_done(job, 2)

        # ── STEP 4 — Translate to selected languages ───────────────────────────
        _step_start(job, 3)
        scripts: dict[str, dict] = {"en": en_script}
        non_en = [lc for lc in languages if lc != "en"]
        for lang_code in non_en:
            # html_carousel.translate_script now supports "sw" too
            translated = _hc.translate_script(en_script, lang_code)
            scripts[lang_code] = translated
            (output_dir / f"script_{lang_code}.json").write_text(
                json.dumps(translated, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _hc._save_caption(translated, output_dir / f"caption_{lang_code}.txt")
        _step_done(job, 3)

        # ── STEP 5 — Build carousel HTML ──────────────────────────────────────
        _step_start(job, 4)
        files: dict[str, dict] = {}
        for lang_code, script in scripts.items():
            html_content = build_swipeable_html(script, slide_images, language=lang_code)
            carousel_name = f"carousel_{lang_code}.html"
            caption_name  = f"caption_{lang_code}.txt"
            out_path = output_dir / carousel_name
            out_path.write_text(html_content, encoding="utf-8")
            files[lang_code] = {
                "carousel_path":     str(out_path),
                "caption_path":      str(output_dir / caption_name),
                "carousel_filename": carousel_name,
                "caption_filename":  caption_name,
                "size_kb":           round(len(html_content) / 1024),
                "language_name":     ALL_LANGUAGES.get(lang_code, lang_code),
                "flag":              LANGUAGE_FLAGS.get(lang_code, "🌐"),
            }
        _step_done(job, 4)

        job["output_dir"] = str(output_dir)
        job["files"]      = files
        job["status"]     = "done"
        
        # Log to history
        try:
            from services.history_service import log_job
            # build files summary
            file_links = []
            for lc, f in files.items():
                file_links.append({"lang": lc, "url": f"/api/carousel/download/{job_id}/{lc}/carousel"})
            log_job(job_id, "carousel", "done", {"topic": job.get("topic", "Carousel"), "files": file_links})
        except Exception as e:
            print(f"[carousel_service] History log failed: {e}")

    except Exception as exc:
        tb = traceback.format_exc()
        job["status"] = "error"
        job["error"]  = str(exc)
        # Mark current running step as error
        for step in job["steps"]:
            if step["status"] == "running":
                step["status"] = "error"
        print(f"[carousel_service] Job {job_id} failed:\n{tb}")
        
        # Log to history
        try:
            from services.history_service import log_job
            log_job(job_id, "carousel", "error", {"topic": job.get("topic", "Carousel"), "error": str(exc)})
        except Exception:
            pass
