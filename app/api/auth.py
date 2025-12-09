from fastapi import APIRouter, Depends, status

from app.models import User
from app.schemas.auth import UserResponse
from app.utils.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("", status_code=status.HTTP_200_OK, response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get current authenticated user information.
    
    Requires a valid Supabase JWT token in the Authorization header.
    
    Returns:
        User information if authenticated successfully.
    """
    return UserResponse(
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
    )

