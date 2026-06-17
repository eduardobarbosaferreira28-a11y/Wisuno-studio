import os
import time
import hashlib

from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from studio.backend.services.supabase_client import supabase

security = HTTPBearer()

# ── Token verification cache ───────────────────────────────────────────────────
# `supabase.auth.get_user()` is a live network round-trip to Supabase's auth
# server. A chunked upload fires one auth call PER chunk (e.g. 39 for an 800 MB
# video), which is slow and trips Supabase's rate limit — a single 429 then
# raises 401 and aborts the whole upload. We cache successful verifications by
# token for a short TTL so a multi-request burst (chunked upload) costs one auth
# call instead of dozens. Revocation/expiry is still honored within the TTL
# window, which is negligible for this internal tool.
_TOKEN_CACHE: dict[str, tuple[float, object]] = {}
_TOKEN_CACHE_TTL = 60.0  # seconds


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _cache_get(token: str):
    entry = _TOKEN_CACHE.get(_cache_key(token))
    if not entry:
        return None
    expires_at, user = entry
    if time.time() >= expires_at:
        _TOKEN_CACHE.pop(_cache_key(token), None)
        return None
    return user


def _cache_put(token: str, user) -> None:
    # Opportunistically evict expired entries so the dict can't grow unbounded.
    now = time.time()
    if len(_TOKEN_CACHE) > 256:
        for k, (exp, _) in list(_TOKEN_CACHE.items()):
            if now >= exp:
                _TOKEN_CACHE.pop(k, None)
    _TOKEN_CACHE[_cache_key(token)] = (now + _TOKEN_CACHE_TTL, user)

# Emails that get full admin visibility (see every user's data). Overridable via
# the ADMIN_EMAILS env var (comma-separated). Defaults to the owner account.
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "eduardo.b@wisuno.com").split(",")
    if e.strip()
}


def _field(user, key):
    """Read a field from either the Supabase User object or the dev-bypass dict."""
    if isinstance(user, dict):
        return user.get(key)
    return getattr(user, key, None)


def user_id_of(user) -> str | None:
    return _field(user, "id")


def email_of(user) -> str | None:
    e = _field(user, "email")
    return e.lower() if e else None


def is_admin(user) -> bool:
    if isinstance(user, dict) and user.get("role") == "admin":
        return True
    e = email_of(user)
    return bool(e and e in ADMIN_EMAILS)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifies the JWT token from the Authorization header using Supabase.
    Returns the user data if valid, otherwise raises a 401.
    """
    if not supabase:
        # If Supabase is not configured yet (e.g. local testing without .env), allow bypass
        # In production, you would strictly raise an error here.
        return {"id": "local_dev_user", "role": "admin"}
        
    token = credentials.credentials

    cached = _cache_get(token)
    if cached is not None:
        return cached

    try:
        # Verify the JWT token by fetching the user profile
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
        _cache_put(token, user_response.user)
        return user_response.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )
