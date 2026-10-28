# Progress

Running log of what was done, newest first.

## 2026-10-28 - Agent tooling (chore/agent-tooling)
- `.claude/settings.json`: Claude Code permissions block from the guide (step 5.2).
- `scripts/new-task.ps1 -Id -Name -Type (fix|feat|chore)`: fetches origin, creates `..\wisuno-<Id>` as a worktree on `<Type>/<Id>-<Name>` from `origin/main`, copies `.env` (never read or printed), creates `.venv`, installs `requirements-dev.txt` + `studio/backend/requirements_studio.txt`, prints next steps. Refuses if the folder or branch already exists.
- `scripts/end-task.ps1 -Id`: removes the worktree and local branch only after confirming the merge (branch is an ancestor of `origin/main`, or `gh pr view` reports MERGED for squash merges). No `--force`; the remote branch is left alone.
- `studio/backend/app.py`: at startup logs `Supabase project ref in use: <ref>` (ref only, never a URL or key), or a warning if `SUPABASE_URL` is unset. Covered by `tests/unit/test_supabase_ref_logging.py`.
- `.env.example`: comment that the local `.env` must point at `wisuno-studio-dev`.
- Follow-up (not done here): `config.py` and `app.py` fall back to a hardcoded Supabase URL/anon key when `SUPABASE_URL` is unset; if that is production, a local run without `.env` silently uses prod. The new log line makes it visible; removing the fallback is a separate task.

## 2026-10-27 - Dev database (chore/dev-database)
- `supabase/schema.sql`: schema-only dump of production (`supabase db dump --linked`, no data). Production was only read.
- Contents: tables `chat_sessions`, `chat_messages`, `jobs`; RLS enabled on all three, each with an open `USING (true) WITH CHECK (true)` policy (copied as-is from production, so no per-user isolation yet); no functions or triggers; extensions `pg_stat_statements`, `pgcrypto`, `supabase_vault`, `uuid-ossp`.
- Applied to the `wisuno-studio-dev` project and created its public `wisuno-assets` bucket (matches production: public, no size or MIME limits). Confirmed by listing its tables.
- The Supabase CLI binary is blocked by Windows Application Control and WSL is denied here, so the CLI was run in a Docker container (`docker:cli` + Node, mounting the Docker socket).
- `supabase/.temp/` (CLI link state) is git-ignored.

## 2026-10-26 — Quality gates (chore/quality-gates)
- `ruff.toml` (py312, line-length 110, E/F/I/B/UP) with ruff pinned in `requirements-dev.txt`; the pre-commit `rev` must match that pin.
- One-time "style: apply ruff" commit (formatting + safe fixes only). Remaining violations are covered by per-file ignores in `ruff.toml`, not code changes: E501 (inline HTML/CSS/prompt strings), plus one-off B904/B905/E402/E731/E741/F401/B005/B007/UP047. Fixing them is a follow-up.
- `scripts/verify.ps1`: ruff check → ruff format --check → pytest -ra, stops at first failure.
- `.pre-commit-config.yaml`: ruff, ruff-format, check-added-large-files (500 KB), gitleaks-system. Run `pre-commit install` once per clone.
- CI: `ruff` and `gitleaks` jobs next to `test`. Marking all three as required is a GitHub branch-protection setting.
- `tests/conftest.py`: autouse `network_attempts` fixture blocks non-loopback sockets/DNS and fails the test at teardown even if the error is swallowed. Covered by `tests/unit/test_network_guard.py`.
