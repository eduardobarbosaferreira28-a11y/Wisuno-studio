# 001 — Auth fails closed
Type: fix · Area: auth · Branch: fix/001-auth-fail-closed
## Goal
Ensure auth fails closed: if Supabase is not configured, deny requests with 503 unless ENV == "local" AND DEV_AUTH_BYPASS == "1", in which case return a dev user with role "dev" (or "admin" if DEV_AUTH_ADMIN == "1"). Refuse startup in production if Supabase env vars are missing.
## For bugs: how to reproduce
With no Supabase configured (supabase is None), requesting an endpoint without credentials currently returns `{"id": "local_dev_user", "role": "admin"}` regardless of environment.
## Acceptance criteria
- [x] If Supabase is not configured: return the dev user ONLY when `ENV == "local"` AND `DEV_AUTH_BYPASS == "1"`; otherwise raise HTTP 503 "Authentication service not configured" — test: unit
- [x] At app startup (`studio/backend/app.py`), if `ENV != "local"` and Supabase env variables are missing or empty, log an error and refuse to start (raise RuntimeError) — test: unit
- [x] The dev user's role is "dev", not "admin", unless `DEV_AUTH_ADMIN == "1"` — test: unit
- [x] Token cache still caches valid tokens and honors TTL — test: unit
- [x] `.env.example` documents ENV, DEV_AUTH_BYPASS, DEV_AUTH_ADMIN — test: manual
- [x] All tests mock Supabase; no live network calls — test: unit
## Out of scope
Frontend UI changes beyond honoring backend auth responses.
## Plan (approved)
1. Tests first: write `tests/unit/test_auth_fail_closed.py` covering all acceptance criteria and edge cases.
2. Update `studio/backend/dependencies/auth.py`:
   - Support `HTTPBearer(auto_error=False)` or handle missing credentials gracefully so bypass works cleanly without token header.
   - When supabase is None:
     - Check `os.getenv("ENV") == "local"` and `os.getenv("DEV_AUTH_BYPASS") == "1"`.
     - If matched, check `os.getenv("DEV_AUTH_ADMIN") == "1"`: if true role is "admin", else role is "dev". User is `{"id": "local_dev_user", "role": ...}`.
     - If not matched, raise `HTTPException(status_code=503, detail="Authentication service not configured")`.
   - When supabase is present: token verification with cache remains intact.
3. Update `studio/backend/app.py` startup event / startup validation:
   - Check if `os.getenv("ENV") != "local"` and (`not os.getenv("SUPABASE_URL")` or `not os.getenv("SUPABASE_ANON_KEY")`).
   - If missing, log error via `logging_config` and raise `RuntimeError("Production startup failed: Supabase configuration missing")`.
4. Update `.env.example` with documentation for `ENV`, `DEV_AUTH_BYPASS`, `DEV_AUTH_ADMIN`.
5. Run `.\scripts\verify.ps1` to ensure all tests pass and formatting is clean.
6. Update `docs/PROGRESS.md`.
## Notes from manual check
Removed production fallback URLs/keys from config.py and /api/config.js. Startup logs verify only project ref or 'set'/'missing' state, never secrets.
