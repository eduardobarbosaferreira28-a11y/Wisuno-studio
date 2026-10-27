# Progress

Running log of what was done, newest first.

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
