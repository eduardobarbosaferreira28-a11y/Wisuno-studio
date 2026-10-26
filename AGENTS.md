# AGENTS.md — single source of truth for Claude Code, Codex and Antigravity

## Product
Wisuno Studio: internal web app producing marketing content for Wisuno, a regulated CFD broker.
Tools: Carousel Studio (news → swipeable HTML carousel + caption, 6 languages), Video Studio (raw talking-head → captioned vertical Reel), Gen Studio (chat → brand-locked images/videos), Dashboard + Settings.
Details: docs/ARCHITECTURE.md. Carousel design rules: docs/CAROUSEL_TEMPLATE.md.

## Stack
Python 3.12 · FastAPI (studio/backend/app.py) · vanilla JS SPA (studio/frontend, no bundler) · Supabase (auth, Postgres, Storage bucket wisuno-assets) · Anthropic, Gemini/Veo, ElevenLabs, Higgsfield · ffmpeg, Playwright · Docker on Railway (auto-deploys main).

## Commands (Windows PowerShell)
- Activate: .venv\Scripts\Activate.ps1
- Run app: uvicorn studio.backend.app:app --reload --port 8000
- Verify: .\scripts\verify.ps1   (ruff check, ruff format --check, pytest)
- Tests only: pytest -ra
- Link skills for Claude Code (once per clone, cmd): cmd /c mklink /J .claude\skills .agents\skills
- Add a dependency: ASK FIRST, then pin it in the right requirements file

## Repo map
studio/backend/routers (HTTP) · studio/backend/services (logic) · studio/backend/dependencies/auth.py (auth) · studio/frontend/js (one controller per page) · root *.py (carousel pipeline, reused by the Studio) · compliance/ (regulatory text, see rule 4) · tests/unit, tests/integration · docs · tasks

## Hard rules
1. Never push to main; main deploys to production. One task = one branch = one worktree; every change is a PR.
2. Plan first from tasks/NNN-*.md; wait for approval before editing files.
3. Tests never make live calls: Anthropic, Gemini, ElevenLabs, Higgsfield, Supabase and HTTP are always mocked.
4. Regulatory disclaimer text lives only in compliance/disclaimer.py. Never edit it. Every generated asset must include it (tests enforce this).
5. swipeable_carousel.py layout, spacing and colours are locked; change them only when the task file says so.
6. Never use the Supabase service-role key in frontend code. Any server code using the service-role client must enforce per-user isolation and have a test proving user A cannot read user B's data.
7. Auth fails closed: no request is authenticated without a verified token, except the explicit local bypass (ENV=local and DEV_AUTH_BYPASS=1).
8. Never edit vendored code: studio/repos/video-use/**, studio/frontend/js/supabase.js, studio/frontend/js/mediabunny.esm.js.
9. Never read or print .env files. Never point local runs at the production Supabase project.
10. Never weaken, skip or delete a test. Same error twice: stop and explain.
11. Done = .\scripts\verify.ps1 green with output shown + docs/PROGRESS.md updated.

## Conventions
Routers stay thin; logic goes in services · type hints on new Python · Pydantic models for request/response bodies · logging via logging_config, never print · user-facing errors never include stack traces or keys.

## Review
Reviewers use docs/REVIEW.md item by item.

## Gotchas
(append only when a lint rule or test cannot catch it; see docs/GARDEN.md)
