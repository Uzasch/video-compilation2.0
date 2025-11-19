from fastapi import APIRouter, HTTPException, Depends
from api.models import LoginRequest, LoginResponse, User
from services.supabase import get_supabase_client

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Simple login - just check if username exists.
    No password required as per requirements.
    """
    supabase = get_supabase_client()

    try:
        # Check if user exists in profiles table
        result = supabase.table("profiles").select("*").eq("username", request.username).execute()

        if result.data and len(result.data) > 0:
            user_data = result.data[0]
            user = User(**user_data)
            return LoginResponse(user=user, message="Login successful")
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.post("/logout")
async def logout():
    """Logout endpoint (placeholder for future session management)"""
    return {"message": "Logout successful"}

@router.get("/me", response_model=User)
async def get_current_user(user_id: str):
    """
    Get current user details.
    In production, this would use a session token.
    For now, user_id is passed as query parameter.
    """
    supabase = get_supabase_client()

    try:
        result = supabase.table("profiles").select("*").eq("id", user_id).execute()

        if result.data and len(result.data) > 0:
            return User(**result.data[0])
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")
