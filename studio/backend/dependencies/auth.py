from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from studio.backend.services.supabase_client import supabase

security = HTTPBearer()

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
