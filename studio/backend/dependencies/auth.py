import os

from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from studio.backend.services.supabase_client import supabase

security = HTTPBearer()

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
    try:
        # Verify the JWT token by fetching the user profile
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
        return user_response.user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )
