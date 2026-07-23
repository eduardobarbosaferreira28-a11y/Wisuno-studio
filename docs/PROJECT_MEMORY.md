# Project Memory — Wisuno Studio (in-depth app summary)

> Human-readable project memory kept **inside the repo** so it's visible in the IDE explorer.
> Claude Code's auto-recall reads a mirror from your user profile at
> `%USERPROFILE%\.claude\projects\c--Users-Eduardo-Desktop-Triache-Marketing-wisuno-carousel\memory\`.
> If you edit this file, tell Claude to "sync memory" so the profile copy updates too.

---

## 0. What this product is

**Wisuno Studio** is an internal web app for producing marketing content for Wisuno (a
multi-regulated CFD broker). It bundles four tools behind one login:

1. **Carousel Studio** — turn a news URL or pasted text into a swipeable Instagram carousel (HTML) + caption, in 6 languages.
2. **Video Studio** — turn a raw 4K talking-head video into a captioned, cut-down, music-scored vertical Reel.
3. **Gen Studio (Gen AI BETA)** — chat with Claude to generate brand-locked marketing images (Gemini 3 / Nano Banana Pro) and videos (Veo 3).
4. **Dashboard + Settings** — job history and (admin-only) dependency/API-key setup.

The repo root (`wisuno-carousel/`) also holds the **original standalone carousel pipeline**
(CLI scripts); the studio web app under `studio/` reuses that pipeline.

---

## 1. Tech stack & architecture

- **Backend:** FastAPI (`studio/backend/app.py`), served by Uvicorn. Production entrypoint module
  is `studio.backend.app:app`.
- **Frontend:** vanilla JS single-page app (no framework) served as static files by the same
  FastAPI app. `index.html` shell + `js/app.js` router; one controller per page.
- **Auth + data:** Supabase — JWT auth, Postgres tables, and a Storage bucket `wisuno-assets`
  (all generated assets are uploaded there so they survive Railway restarts).
- **AI providers:** Anthropic Claude (orchestration, scripts, cut analysis), Google Gemini 3 /
  Nano Banana Pro (images) + Veo 3 (video), ElevenLabs (Scribe transcription + music).
- **Media tooling (video):** ffmpeg, ImageMagick, Node.js + `hyperframes` (overlay renderer),
  Playwright Chromium, and a vendored `studio/repos/video-use` package.
- **Deploy:** Docker (`Dockerfile`, `python:3.12-slim` + ffmpeg/imagemagick/nodejs/hyperframes/
  playwright) on **Railway**, auto-deploying on push to `main`. GitHub repo:
  `eduardobarbosaferreira28-a11y/Wisuno-studio`. `.env` holds all API keys + Supabase creds.

### Backend layout (`studio/backend/`)
- `app.py` — FastAPI app: mounts `/css` + `/js` static, serves `index.html` / `login.html`,
  injects `/api/config.js` (Supabase public creds), `/api/me` (identity+role), `/health`,
  SPA fallback. Registers all routers. Adds project root + backend dir to `sys.path`.
- `routers/` — `carousel.py`, `video.py`, `higgsfield.py` (Gen Studio), `history.py`, `setup.py`.
- `services/` — `carousel_service.py`, `video_service.py`, `gen_service.py` (Gen Studio),
  `history_service.py`, `disclaimer.py`, `supabase_client.py`, `video_overlays.py`.
- `dependencies/auth.py` — Supabase JWT verification.
- `helpers/` — `build_karaoke_ass.py`, `build_overlays.py`, `hf_render.py` (video render helpers).

### Frontend layout (`studio/frontend/`)
- `index.html` — SPA shell: sidebar nav (Dashboard, Settings, Carousel, Video, Gen Studio) + a
  `page-view` div per tool. `login.html` is the separate auth page.
- `js/app.js` — client router (`app.navigate`), `apiFetch()` (auto-attaches Supabase JWT, forces
  JSON content-type), toast system, auth check, `/api/me` role gating.
- `js/carousel.js`, `js/video.js`, `js/higgsfield.js`, `js/dashboard.js`, `js/setup.js` — one
  controller object per page. `js/supabase.js` — Supabase client lib.
- `js/transcode.js` + `js/mediabunny.esm.js` — browser-side video crop/downscale before upload
  (see §3). Third-party libs are **vendored** (committed), not loaded from a CDN — `supabase.js`
  and `mediabunny.esm.js` are both committed jsDelivr/npm builds. There is no bundler and no
  `package.json`; scripts are plain globals cache-busted by a hand-bumped `?v=N`.
- `css/main.css` — all styling (CSS variables, `--orange`, components).

### Auth & multi-tenancy (`dependencies/auth.py`)
- `get_current_user` verifies the `Authorization: Bearer <jwt>` via `supabase.auth.get_user()`,
  with a 60s in-memory **token cache** (so a chunked upload's many requests cost one auth call).
- If Supabase isn't configured (local dev), it **bypasses** auth and returns a `local_dev_user`
  admin — that's why headless local API testing "works" without a real login.
- **Admins** = emails in `ADMIN_EMAILS` env (default `eduardo.b@wisuno.com`). Admins see all
  users' data; everyone else is isolated to their own `user_id` (per-user dashboard/history,
  session ownership checks).

### Supabase tables
- `jobs` — history log (`id`, `job_type` ∈ {carousel, video, gen_image, gen_video}, `status`,
  `details` JSON, `user_id`, `created_at`). Written and read via the **service-role** client
  (`admin_supabase`), which bypasses RLS; the anon client is only for verifying user JWTs.
  Per-user isolation is enforced **in Python** (`.eq("user_id", …)` / `ADMIN_EMAILS`), never by RLS.
  ⚠️ `output/studio_log.jsonl` is **not** a real backup — it sits on Railway's ephemeral disk (no
  volume) and dies with the container. The `jobs` table is the only durable record.
- `chat_sessions` — Gen Studio chats (`id`, `title`, `user_id`, `updated_at`).
- `chat_messages` — Gen Studio messages (`session_id`, `role`, `content`, `created_at`).

---

## 2. Carousel Studio

**Goal:** news URL or pasted text → self-contained swipeable HTML carousel + Instagram caption,
in up to 6 languages.

- **Pipeline service:** `services/carousel_service.py` runs a 5-step job in a thread pool with
  live progress: (1) extract article, (2) generate English script via Claude, (3) generate images,
  (4) translate to selected languages, (5) build carousel HTML. Uploads results to Supabase and
  logs to history.
- **Reused root pipeline:** `html_carousel.py` (orchestrator: `generate_script`,
  `generate_slide_images`, `translate_script`, `_slugify`, `_save_caption`), `content_extractor.py`
  (`extract_from_url`/`extract_from_text`), `image_generator.py` (Gemini images),
  `swipeable_carousel.py` (`build_swipeable_html` — the **locked design template**), and
  `slide_renderer.py` (per-slide HTML/CSS).
- **Languages:** en, zh-TW, zh-CN, th, sw (Kiswahili), pt-BR (Brazilian Portuguese), vi (Vietnamese).
- **Content types:** Market Insight, Promotional, Market Update, Educational.
- **Slides:** 4–8 (default 6); slide types cover / data_slide / analysis_slide / quote_slide /
  chart_slide / cta_slide. Output → `output/<slug>/`.
- **API:** `POST /api/carousel/run`, `GET /api/carousel/status/{job_id}`,
  `GET /api/carousel/download/{job_id}/{lang}/{file_type}`, `GET /api/carousel/caption/...`,
  `GET /api/carousel/preview/...`, `GET /api/carousel/languages`.

**Design ground truth:** `output/cpi-38-inflation-test/carousel.html` is the canonical visual
reference; `swipeable_carousel.py` is the template — never change its layout/spacing/colours
without explicit instruction. Canvas 1080×1350 (4:5), `#0A0A0A` bg, 180px safe zone.

---

## 3. Video Studio

**Goal:** raw 4K landscape talking-head → cut-down, captioned, music-scored 1080×1920 vertical Reel.

- **Pipeline service:** `services/video_service.py` — a 14-step spec (per `ANTIGRAVITY_REBUILD.md`)
  surfaced to the UI as 6 steps:
  0. Probe + portrait crop (centred 9:16 window → 1080×1920, for any source resolution).
     **Skipped entirely when the upload is already exactly 1080×1920** — see "Uploads" below.
  1. Transcribe with **ElevenLabs Scribe** (cached).
  2. Pack transcript to phrase-level markdown.
  3. **AI cut analysis via Claude** → proposed EDL (edit decision list) ranges.
  4. **Human approval** (user reviews/edits proposed cuts in the UI).
  5. Render: build EDL + **karaoke ASS subtitles**, extract graded segments, concat → base.mp4,
     render **HyperFrames** overlays (captions, slides, disclaimer, outro), composite via
     `render.py` with 2-pass loudnorm, generate background music (**ElevenLabs /v1/music**),
     mix audio → `final_music.mp4`.
- **Uploads:** the **uplink is the bottleneck**, not the server. The browser now crops/downscales
  to **exactly 1080×1920** before uploading (`js/transcode.js`, WebCodecs via vendored
  `mediabunny`), then sends 20 MB chunks **4-wide** via `/upload_chunk` + `/upload_complete`.
  A 4K source goes from ~2 GB / ~25 min to ~40 MB / seconds, and step 0's full-4K ffmpeg
  re-encode disappears because `_run_analysis` skips the crop on an exact 1080×1920 match.
  Rules that are load-bearing here (details in §8, 2026-07-13):
  - **Never resample the frame rate** and never use `MediaRecorder`/`captureStream` (VFR) — the
    render frame-locks karaoke captions to the file's `r_frame_rate`.
  - **Audio must survive** the transcode — Scribe transcribes the uploaded file.
  - Output must be `.mp4` (`ALLOWED_EXTS` rejects `.webm`); every failure path falls back to
    uploading the original file untouched.
  - The Supabase JWT is re-read per request (a long upload outlives it; a 401 forces a refresh).
- **Output:** `output/video/<slug>/edit/`.
- **API:** `POST /api/video/upload`, `/upload_chunk`, `/upload_complete`,
  `GET /api/video/status/{job_id}`, `POST /api/video/approve/{job_id}`,
  `GET /api/video/download/{job_id}`, `GET /api/video/stream/{job_id}`, `POST /api/video/retry/{job_id}`.
- **Deps:** ffmpeg, ImageMagick, Node + `hyperframes`, the vendored `studio/repos/video-use`
  helpers + `render.py`.

---

## 4. Gen Studio (Gen AI BETA) — most recent work

A chat UI where users ask Claude to generate marketing **images** (Nano Banana Pro / Gemini 3) and
**videos** (Veo 3). Separate from the carousel/video pipelines.

**Request flow:**
`studio/frontend/js/higgsfield.js` → `POST /api/higgsfield/chat` (`routers/higgsfield.py`) →
`gen_service.chat()` (`services/gen_service.py`) runs a **Claude tool-use loop** → Claude calls the
local tools `generate_image` / `generate_video` → those build a prompt and call Gemini/Veo.

- Images are synchronous (return a public URL immediately). Videos are async: a job id is returned
  and the frontend polls `GET /api/higgsfield/video_status/{job_id}` (8s interval, 12min timeout).
- Models: `gemini-3-pro-image-preview` (Nano Banana Pro) with fallback `gemini-2.5-flash-image`;
  `veo-3.0-generate-preview`; orchestrator `claude-sonnet-4-6`.
- Assets upload to Supabase `wisuno-assets` (`gen/images/`, `gen/videos/`, `gen/uploads/`).
- The CFD disclaimer is burned on **post-generation** via `services/disclaimer.py`
  (`overlay_disclaimer_on_image` / `_on_video`) — never asked of the model.
- "Interview mode": if a request is vague, Claude asks one question at a time with `[Option]`
  suggestions (rendered as buttons in the UI).
- Chat history persists in Supabase `chat_sessions` / `chat_messages`; sidebar lists sessions.

### Features built (commit `fed94cb`, branch `main`)
1. **Brand + logo LOCKED into every Gemini/Veo prompt.** `gen_service.BRAND_GUIDELINE_BLOCK` +
   `_apply_brand()` prepend the Wisuno brand to every prompt regardless of Claude's output.
   `_load_brand_logo()` reads `Wisuno Logo/White-Colored.png` and feeds it to Nano Banana Pro as a
   `types.Part.from_bytes`, so the real logo lands top-right, undistorted. Veo only accepts one
   `image=` (reserved for user uploads), so it gets the logo described in text.
2. **Upload from computer → visual reference.** `POST /api/higgsfield/upload` stores the image to
   Supabase and returns a URL. `ChatRequest.reference_image_urls` carries them; the router attaches
   them to Claude's message as image blocks AND downloads bytes (`_download_image`) threaded through
   `chat()` → `_execute_tool()` → generators. Image → image-to-image; video → Veo first frame.
   Tools expose `use_reference_image` so Claude can choose to ignore the upload.
3. **Add context → persistent per-chat text box.** `ChatRequest.context` is appended to the system prompt.
4. **Browse the web → Anthropic native server tool** `{"type":"web_search_20250305","name":"web_search","max_uses":5}`,
   gated by `ChatRequest.web_enabled`; added to the tools list only when enabled. Server-tool result
   blocks are ignored by the local loop (it only executes `block.type == "tool_use"`).

**Frontend:** attachment toolbar (Upload / Add context / Browse web) in the input area of
`index.html`; styles `.hf-tool-btn` / `.hf-attach-chip` in `css/main.css`; wiring (`uploadImage`,
`renderAttachments`, context box, web toggle, payload + reference thumbnails) in `js/higgsfield.js`.

**SDKs (verified):** anthropic 0.89.0 (forwards the web_search dict, no beta header), google-genai
1.70.0 (`generate_videos(image=...)`, `types.Image(image_bytes, mime_type)`, `types.Part.from_bytes`).

---

## 5. Canonical brand values (decided in this work)

- **Accent orange = `#FF6700`** (NOT `#FF6B00`). `config.py` is the source of truth.
- **Body font = General Sans** (brand canonical). Headlines = **Urbanist**.
- **Inter is only the Google-Fonts web substitute** for General Sans — the rendered carousels
  (`slide_renderer.py`, `swipeable_carousel.py`) load Inter because General Sans isn't on Google
  Fonts. The brand *spec* says General Sans; the *render* uses Inter. Don't change the carousels'
  `font-family:'Inter'`.
- Other tokens: bg `#0A0A0A`, light `#FAFAFA`, text `#FFFFFF`/`#CCCCCC`, disclaimer grey `#888888`,
  down/red `#EF4444`.
- **Why:** the repo was inconsistent (config.py said `#FF6700`/General Sans while Gen Studio,
  carousels, CLAUDE.md and app UI used `#FF6B00`/Inter). Eduardo chose the PDF values as canonical;
  the unify pass changed ~105 occurrences across backend, templates, app CSS/JS, and docs.
- **Apply:** always use `#FF6700`; never `#FF6B00`.

---

## 6. API surface (quick reference)

- **Auth/system:** `GET /api/me`, `GET /api/config.js`, `GET /health`.
- **Carousel:** `POST /api/carousel/run`, `GET /status/{id}`, `GET /download/{id}/{lang}/{type}`,
  `GET /caption/{id}/{lang}`, `GET /preview/{id}/{lang}`, `GET /languages`,
  `POST /api/carousel/daily` (admin — auto-pick today's story + build),
  `GET /api/carousel/today` (admin — preview the pick, no build).
- **Video:** `POST /api/video/upload` `/upload_chunk` `/upload_complete`, `GET /status/{id}`,
  `POST /approve/{id}`, `GET /download/{id}`, `GET /stream/{id}`, `POST /retry/{id}`.
- **Gen Studio:** `POST /api/higgsfield/upload`, `POST /api/higgsfield/chat`,
  `GET /video_status/{id}`, `GET /sessions`, `GET /sessions/{id}/messages`.
- **History:** `GET /api/history`.
- **Setup (admin):** `GET /api/setup/check`, `POST /install-hyperframes`,
  `GET /install-hyperframes/status`, `POST /save-key`.

---

## 7. Run & deploy

- **Run studio locally:** `cd studio/backend && python -m uvicorn app:app --host 127.0.0.1 --port 8123`.
  Needs `.env` with `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (+ optional
  `SUPABASE_URL`/`SUPABASE_ANON_KEY`, `ELEVENLABS_API_KEY`, `ADMIN_EMAILS`). Authenticated endpoints
  need a Supabase JWT (login), so headless API testing of `/chat`/`/upload` isn't possible — test
  generation in-process by calling `gen_service.chat()`.
- **Run original carousel CLI:** `python html_carousel.py --url https://…` (or `--script …json`,
  `--no-images`). Output → `output/<slug>/`.
- **Deploy:** push to `main` → Railway auto-builds the Dockerfile and deploys. Production CMD:
  `uvicorn studio.backend.app:app --host 0.0.0.0 --port ${PORT}`.
- **Railway has no volume** (`volumeMounts: []`). Nothing on disk survives a deploy or restart —
  not `output/`, not any cache. Anything that must persist goes to Supabase (DB or Storage).
- **Dockerfile constraints for HyperFrames** (all three are required; see §8, 2026-07-13):
  `unzip` (to extract chrome-headless-shell), **Node 22+**, and `hyperframes browser ensure` at
  **build** time so Chrome is baked into the image instead of downloaded inside a request.
  `hyperframes` is **pinned to 0.7.18** in both the Dockerfile *and*
  `POST /api/setup/install-hyperframes` — an unpinned install silently defeats the pin.

---

## 8. Debugging sessions (changelog)

### 2026-07-13 — Chrome in the image, job history writes, and a 30-min → ~35 s video upload
Commits `407de14`, `6f278dc`, `7e63de5`, `841b92a`.

**1. Every video render failed: "no zip archiver is available".** The image installed
`hyperframes` but never provisioned the browser it drives. `python:3.12-slim` ships no `unzip`,
nothing pre-fetched Chrome, and with no Railway volume the cache never survived a restart — so
each render re-downloaded 114 MB of chrome-headless-shell inside a request and then failed to
unpack it. Fixed by installing `unzip`, moving to Node 22 (HyperFrames requires 22+), and running
`hyperframes browser ensure` at **build** time.
- *The tell was a version mismatch:* pinned hyperframes 0.7.18 wants Chrome **131**, but the
  failing runtime asked for Chrome **152**. The container's global had been upgraded past the pin
  by `POST /api/setup/install-hyperframes`, which ran `npm install -g hyperframes` **unpinned**
  (latest = 0.7.55 → Chrome 152). That endpoint was also quietly undoing the caption-drift pin
  from `82f26c7`. **Now pinned.**
- `npx` *does* honour a globally-installed package (verified) — `hf_render.py` calling
  `npx hyperframes` is fine. Don't "fix" it.
- Don't assert the baked browser via `hyperframes browser path`: it decorates its output when
  stdout isn't a TTY, so command substitution yields junk and the build fails. (It prints a clean
  path on a Windows TTY, which hides this locally.) Assert on the extracted binary with `find`.

**2. No job history after 2026-07-10 — with no deploy and no commit on that date.** It was a
*write* failure while reads stayed healthy (newest `jobs` row was 07-10T07:50; `/api/history`
still served its full 100-row page). Three things made it possible *and* invisible:
- `log_job` inserted via the **anon** client with no user JWT — running as the Postgres `anon`
  role, fully exposed to RLS. Writes (and reads) now use the **service-role** client.
- `details` went into a `jsonb` column straight from `str(exc)`, and renderer errors carry raw
  ANSI escapes and a NUL byte, which Postgres rejects in `jsonb` outright. Now sanitized+truncated.
- Failures were swallowed by a bare `print()` plus `except: pass` at every call site. Now logged.
- Also: the video *analysis* failure path logged without a `user_id`, so those rows landed with a
  NULL owner and were invisible to every non-admin.

**3. Reaching the cut-approval screen took >30 min.** Not the probe, not ffmpeg: the container was
still *receiving the upload* (~0.7 MB/s, 0.1 vCPU — nothing was computing). Two bugs:
- The uploader captured the Supabase JWT **once** before the chunk loop, so a long upload outlived
  the token and every remaining chunk 401'd while the retries replayed the dead credential. Now
  re-read per request, with a forced `refreshSession()` on 401.
- We were spending 25 minutes uploading 4K pixels the server discards in step 0. The browser now
  crops to exactly 1080×1920 first (§3). **Result in production: a Sony 4K clip arrived as
  `1080×1920 h264 23.98fps 38.8MB`, and upload → proposed cuts took ~35 s.**
- Verified in headless Chromium against a 3840×2160 @ `24000/1001` clip before shipping: output
  1080×1920, `r_frame_rate` still exactly `24000/1001`, AAC audio intact.
- Vendor browser libs as **`.js`, not `.mjs`** — `/js` is served by Starlette `StaticFiles`, which
  types files via Python `mimetypes`; a module import fails outright on a non-JS MIME type.

**Still open:** an *audio-first* pipeline would put approval at ~2–3 min (Claude's cut analysis
needs only the transcript, and transcription needs only audio, so the video could upload in the
background). Render-side: captions and disclaimer are two *full-length sequential* Chromium
renders, and `extract_all_segments` uses `max_workers=2` despite advertising 4.

### 2026-06-29 — Karaoke captions drifting behind the speaker
Commits `d0ef016`, `82f26c7`, `baa64fa` (+ `e0fb2f0` on 07-11). Three independent causes, all
making captions fall progressively further behind as the edit progressed:
1. **A/V drift accumulation** — the source is 23.976 fps but `extract_segment` forced `-r 24`.
   Fixed by snapping every cut to a real frame (`probe_fps`, `snap_duration_to_frame`, `apad` /
   `-shortest` / `-fps_mode cfr`).
2. **HyperFrames seeking by progress, not seconds** — the Dockerfile installed `hyperframes`
   **unpinned**, and newer builds seek GSAP timelines by progress (0..1) instead of absolute
   seconds, stretching every caption cue across the whole clip. Fixed by **pinning 0.7.18** and
   padding the caption timeline to the full composition duration.
3. **The main cause** — `build_karaoke_ass` even-distributed words whenever Claude's `quote`
   word-count differed from the transcript. Fixed by never even-distributing.

`e0fb2f0` (07-11) then replaced the hard-coded `1215:2160:1312:0` crop (which crashed 9 video jobs
on 07-07 on non-4K sources) with a computed centred 9:16 window for any resolution.

> **This is why the frame rate rules in §3 exist.** Anything that changes the uploaded file's
> `r_frame_rate` reintroduces this bug, and it only shows up in the *final render*.

### 2026-06-24 — Pipeline reliability, test suite + CI, and daily auto-pick carousel
Three builds shipped to `main` (commits `1c45af6`, `d6a28dc`, `aeccb30`, `0b2dcb4`,
`6b90bef`, `fed3245`). The CI workflow needed a PAT with `workflow` scope to push.

**1. Pipeline reliability (`1c45af6`).** The carousel pipeline had single points of failure.
- New **`retry_utils.py`** (repo root, shared by CLI + studio): `retry(fn, *, attempts, base_delay,
  backoff, exceptions, on_retry)` — generic exponential backoff. `image_generator` was refactored
  onto it.
- **Claude calls hardened:** `html_carousel._anthropic_client()` now builds the client with
  `max_retries=3, timeout=60.0` (used by `generate_script` + `translate_script`); same applied to
  `news_picker._claude_pick`. So a slow/overloaded Claude can no longer hang or kill a job.
- **`image_generator.generate_chart_image`** now retries (was 0); **`content_extractor.extract_from_url`**
  retries transient network errors (`httpx.RequestError`) but still fails fast on 4xx/5xx.
- **Partial-success surfaced:** `carousel_service` tracks a per-job `warnings` list; when a Supabase
  upload silently falls back to a local-only URL, it adds a warning and the `/status` response now
  returns `warnings` (so the UI can say "local download only" instead of a clean "done").
- **Structured logging:** new **`studio/backend/logging_config.py`** (`configure_logging()` called at
  `app.py` startup, honors `LOG_LEVEL`); backend `print()` diagnostics → `logger`. Left the CLI
  progress `print()`s in `html_carousel.py` / `news_picker.py` alone (user-facing console output).

**2. Test suite + CI (`d6a28dc` + `0b2dcb4`).** Was zero automated coverage.
- **pytest** under `tests/` (`pytest.ini` sets `testpaths = tests/unit tests/integration`).
  `tests/conftest.py` sets sys.path (root + studio/backend) and provides offline fakes — a
  `FakeAnthropicClient` and a `sample_script` fixture. **All tests run fully offline.**
- Unit: `retry_utils`, `_slugify`/`_save_caption`, `translate_script` JSON-repair (mocked Claude),
  full `build_swipeable_html` render (asserts disclaimer fragment on every slide + logo data-URI),
  `news_picker` scoring/dedupe/blocklist + recency, `RunRequest.validate_languages`. Integration:
  carousel router via `TestClient` with auth + job layer stubbed.
- Stale root `test_*.py` (live API pings, **no `__main__` guard → ran on import**) moved to
  `tests/manual/check_*.py` so pytest never collects them.
- **`.github/workflows/ci.yml`** runs `pytest` on push/PR to `main` (no secrets — all calls mocked).
- Added **`requirements-dev.txt`** (test deps, kept out of the Docker image) and added
  `feedparser` + `yfinance` to `requirements.txt` (news_picker needs them at runtime; were unpinned —
  would have broken the deployed daily feature).

**3. Daily auto-pick carousel (`aeccb30`, `6b90bef`, `fed3245`).** Exposed the existing
`news_picker` + `daily_workflow` logic (previously CLI-only) in the Studio UI.
- **`POST /api/carousel/daily`** (admin): runs `news_picker.pick_top_article()` via
  `asyncio.to_thread` (it does blocking RSS/yfinance HTTP + a Claude call), then reuses `start_job`
  with the picked article's URL. Returns `{job_id, languages, article}`.
- **`GET /api/carousel/today`** (admin): dry-run preview of the pick (maps to
  `daily_workflow.py --dry-run`). Language normalization factored into a shared
  `_normalize_languages()` used by both `/run` and `/daily`.
- **Frontend:** admin-only "✨ Generate from today's top story" button, placed **above** the
  Article URL / Paste Text tabs (top of the input card); reuses the existing progress/poll UI and
  shows the picked headline + rationale. `carousel.js?v=` bumped (→ 18).
- **2-day recency guarantee (`6b90bef`):** `news_picker._score` / `pick_top_article` gained
  `max_age_hours` + `require_dated` params. Previously the age cap only applied to articles with a
  parseable publish date — **undated articles passed through at any age**. The `/daily` + `/today`
  endpoints now pass `max_age_hours=48, require_dated=True`, so picks are guaranteed ≤2 days old with
  a confirmable date. `daily_workflow.py` is unchanged (defaults preserve the prior 20h behavior).

**Lessons:** (a) any per-request external call in a job pipeline needs a retry/timeout or one blip
kills the whole job; (b) a "silent fallback" (upload failed → local URL) must surface as a warning,
not a clean success; (c) test files that run on import will fire live API calls under pytest — guard
or relocate them; (d) recency filters that only apply "when a date exists" leak stale undated items.


**Symptom:** running a Portuguese (pt-BR) carousel generation in the Studio left some text
untranslated — e.g. `data_slide` values like "Near 2 month high" and "~$4,310/oz" stayed in English
while the rest of the slide was translated.

**Root cause:** Studio and CLI both translate via `html_carousel.translate_script()`, whose
`_TRANSLATE_PROMPT` explicitly listed `data_points[].value` (and `featured_number`) under "keep
UNCHANGED — return byte-for-byte." Those fields hold free-text values ("Near 2 month high"), not
just pure numbers, so the byte-for-byte rule pinned the English words. The static UI labels
(`_SLIDE_LABELS` "WHY IT MATTERS" eyebrow, `_DISCLAIMER_TEXT`) already had full pt-BR coverage, so
the gap was purely in the translated script.

**Fix (commit `c24769f` on `main`):** `html_carousel.py` `_TRANSLATE_PROMPT` —
1. Moved `data_points[].value` into the "translate EVERY field" list.
2. Added a mixed number+word rule: keep numerals / currency symbols / percentages / tickers as-is,
   but translate surrounding words/units (e.g. "Near 2 month high" → translate words, keep digit "2";
   "~$4,310/oz" → keep "~$4,310", localize "/oz"; "10:1"/"$1,000" with no words → keep byte-for-byte).
   Never leave English words like "Near/high/low/above/below/per".
3. Folded `featured_number` into the same mixed-value rule and dropped it (and
   `data_points[].value`) from the keep-unchanged list. Only structural/non-visible keys remain
   pinned (slide_number, type, direction, background_image_description, chart_type, chart_asset,
   content_type).

**Lesson:** "value" fields in the script schema carry prose, not just numbers — translation rules
must split *preserve the number* from *translate the words*, not blanket-pin the whole field.

### 2026-06-18 — Video Studio large-upload reliability ("upload failed at chunk N/M")
**Symptom:** chunked video uploads aborted mid-way (e.g. "Upload failed at chunk 4/39", later
"1/5"). The chunk number was just wherever the connection happened to drop — not deterministic.

**Root cause:** every chunk POST (`/api/video/upload_chunk`) ran the `get_current_user` dependency,
which called `supabase.auth.get_user(token)` — a **live network round-trip to Supabase auth per
chunk**. A 39-chunk upload fired 39 rapid auth calls, tripping Supabase's rate limit; a single 401
then aborted the whole upload because the frontend had **no retry**.

**Fixes (commits `6b980c9`, `5e314a7` on `main`):**
1. `dependencies/auth.py` — added a 60s in-memory **token-verification cache** keyed by SHA-256 of
   the JWT, so a multi-request burst (chunked upload) costs **one** auth call instead of one per
   chunk. Also added `except HTTPException: raise` so the explicit 401 isn't re-wrapped by the broad
   `except Exception` as `Authentication failed: 401: …`. No new dependency/env var; chosen over
   local HS256 JWT verification because newer Supabase projects use asymmetric signing keys (a local
   verify could silently break auth on Railway).
2. `frontend/js/video.js` — each chunk now **retries up to 4× with linear backoff** (1s/2s/3s),
   rebuilding `FormData` per attempt (the blob stream is single-use); the failure message now
   includes the HTTP status, e.g. `Upload failed at chunk 1/5 (HTTP 401)`, for future diagnosis.
3. `frontend/index.html` — bumped `video.js?v=14` → `?v=15`. The retry fix initially appeared not to
   work because browsers kept serving the **cached old `video.js`** (the no-suffix error string was
   the tell). `index.html` is served no-cache, so bumping the `?v=` query forces a fresh fetch.

**Note:** commit `5e314a7` also swept in pre-existing uncommitted `index.html` changes (the Gen
Studio context/upload/browse-web toolbar HTML — the counterpart to the already-committed
`higgsfield.js`); coherent and intended, but not reflected in that commit's message.

**Lesson:** any per-request auth that hits the network will be hammered by chunked uploads — cache
it. And always bump the asset `?v=` when shipping a frontend JS change, or the browser keeps the
old file.
