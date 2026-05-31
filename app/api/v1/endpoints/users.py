from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.goals import GOAL_LABELS, GoalsUpdateRequest
from app.services.goals import update_user_goals

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/users/me/goals", response_model=UserResponse)
async def set_goals(
    payload: GoalsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await update_user_goals(db, current_user, payload.goals)
    return updated


@router.get("/users/me/goals/available")
async def available_goals():
    """Return the full list of selectable goals with display labels."""
    return {"goals": [{"value": k.value, "label": v} for k, v in GOAL_LABELS.items()]}
