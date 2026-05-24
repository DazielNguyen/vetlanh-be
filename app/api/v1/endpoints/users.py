from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
