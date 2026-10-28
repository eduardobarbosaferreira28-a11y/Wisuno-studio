"""
Tests for fail-closed authentication and local dev bypass (AGENTS.md rule 7).

Acceptance criteria:
1. When Supabase is not configured (supabase is None):
   - Returns dev user ONLY when ENV == "local" and DEV_AUTH_BYPASS == "1"
   - Otherwise raises HTTP 503 "Authentication service not configured"
2. Startup checks:
   - When ENV != "local" (including unset or "production") and Supabase env vars are missing:
     logs error and raises RuntimeError
   - When ENV == "local" and vars are missing: startup succeeds
   - When vars are set: startup succeeds
   - startup_event() executes startup validation
3. Dev user role:
   - Defaults to "dev" (is_admin is False)
   - Becomes "admin" (is_admin is True) only when DEV_AUTH_ADMIN == "1"
   - Bypass works even when dev Supabase credentials are configured in local .env
4. Token cache:
   - When Supabase is configured, token verification is cached within TTL
   - Missing token when Supabase is configured raises 401 (unless bypass is active)
   - Expired token cache entry triggers re-fetch
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import app as studio_app
import pytest
from dependencies import auth
from fastapi import HTTPException


class FakeSupabaseUser:
    def __init__(self, user_id: str, email: str = "trader@example.com"):
        self.id = user_id
        self.email = email


class FakeUserResponse:
    def __init__(self, user):
        self.user = user


@pytest.fixture(autouse=True)
def clear_token_cache():
    auth._TOKEN_CACHE.clear()
    yield
    auth._TOKEN_CACHE.clear()


# ── Supabase unconfigured (supabase is None) ──────────────────────────────────


def test_bypass_off_by_default_raises_503(monkeypatch):
    monkeypatch.setattr(auth, "supabase", None)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(credentials=None))

    assert exc.value.status_code == 503
    assert exc.value.detail == "Authentication service not configured"


@pytest.mark.parametrize(
    ("env_val", "bypass_val"),
    [
        (None, "1"),
        ("", "1"),
        ("production", "1"),
        ("staging", "1"),
        ("local", None),
        ("local", ""),
        ("local", "0"),
        ("local", "false"),
    ],
)
def test_bypass_refused_without_both_local_and_bypass_flag(monkeypatch, env_val, bypass_val):
    monkeypatch.setattr(auth, "supabase", None)
    if env_val is None:
        monkeypatch.delenv("ENV", raising=False)
    else:
        monkeypatch.setenv("ENV", env_val)

    if bypass_val is None:
        monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    else:
        monkeypatch.setenv("DEV_AUTH_BYPASS", bypass_val)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(credentials=None))

    assert exc.value.status_code == 503
    assert exc.value.detail == "Authentication service not configured"


def test_bypass_succeeds_with_env_local_and_bypass_1(monkeypatch):
    monkeypatch.setattr(auth, "supabase", None)
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.delenv("DEV_AUTH_ADMIN", raising=False)

    user = asyncio.run(auth.get_current_user(credentials=None))
    assert user == {"id": "local_dev_user", "role": "dev"}
    assert auth.is_admin(user) is False


def test_bypass_succeeds_when_supabase_is_configured_locally(monkeypatch):
    """When .env points to dev Supabase, bypass still works locally without a session."""
    fake_client = MagicMock()
    monkeypatch.setattr(auth, "supabase", fake_client)
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.delenv("DEV_AUTH_ADMIN", raising=False)

    user = asyncio.run(auth.get_current_user(credentials=None))
    assert user == {"id": "local_dev_user", "role": "dev"}
    assert auth.is_admin(user) is False
    assert fake_client.auth.get_user.call_count == 0


def test_bypass_dev_user_admin_role_when_flag_set(monkeypatch):
    monkeypatch.setattr(auth, "supabase", None)
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("DEV_AUTH_ADMIN", "1")

    user = asyncio.run(auth.get_current_user(credentials=None))
    assert user == {"id": "local_dev_user", "role": "admin"}
    assert auth.is_admin(user) is True


# ── App Startup Checks ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "env_val",
    [None, "", "production", "staging"],
)
def test_startup_refuses_when_not_local_and_supabase_missing(monkeypatch, caplog, env_val):
    if env_val is None:
        monkeypatch.delenv("ENV", raising=False)
    else:
        monkeypatch.setenv("ENV", env_val)

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    with caplog.at_level(logging.ERROR, logger=studio_app.logger.name):
        with pytest.raises(RuntimeError) as exc:
            studio_app.validate_startup_config()

    assert "Supabase" in str(exc.value)
    assert any(
        r.levelno == logging.ERROR and "Supabase environment variables missing" in r.message
        for r in caplog.records
    )


def test_startup_allowed_when_env_local_without_supabase(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    # Must not raise
    studio_app.validate_startup_config()


def test_startup_allowed_when_supabase_vars_present(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://xyzcompany.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-123")

    # Must not raise
    studio_app.validate_startup_config()


def test_startup_event_triggers_validation(monkeypatch):
    """Ensure startup_event() invokes validate_startup_config()."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(studio_app.startup_event())

    assert "Supabase" in str(exc.value)


# ── Token verification and caching when Supabase is configured ────────────────


def test_token_missing_raises_401_when_supabase_configured(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(auth, "supabase", fake_client)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(credentials=None))

    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


def test_token_cache_hits_and_ttl(monkeypatch):
    fake_client = MagicMock()
    fake_user = FakeSupabaseUser("user_123", "trader@wisuno.com")
    fake_client.auth.get_user.return_value = FakeUserResponse(fake_user)
    monkeypatch.setattr(auth, "supabase", fake_client)

    creds = MagicMock()
    creds.credentials = "valid.jwt.token"

    # 1. First call hits client
    u1 = asyncio.run(auth.get_current_user(credentials=creds))
    assert u1.id == "user_123"
    assert fake_client.auth.get_user.call_count == 1

    # 2. Second call with same token hits cache
    u2 = asyncio.run(auth.get_current_user(credentials=creds))
    assert u2.id == "user_123"
    assert fake_client.auth.get_user.call_count == 1

    # 3. Fast-forward time past TTL -> cache miss and refetches
    current_time = [1000.0]
    monkeypatch.setattr(auth.time, "time", lambda: current_time[0])
    # populate at t=1000
    auth._TOKEN_CACHE.clear()
    asyncio.run(auth.get_current_user(credentials=creds))
    assert fake_client.auth.get_user.call_count == 2

    # Still valid at t=1050 (TTL=60s)
    current_time[0] = 1050.0
    asyncio.run(auth.get_current_user(credentials=creds))
    assert fake_client.auth.get_user.call_count == 2

    # Expired at t=1061.0
    current_time[0] = 1061.0
    asyncio.run(auth.get_current_user(credentials=creds))
    assert fake_client.auth.get_user.call_count == 3
