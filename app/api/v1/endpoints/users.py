from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.goals import GOAL_LABELS, GoalsUpdateRequest
from app.schemas.healing_path import HealingPathResponse, UserStatsResponse
from app.schemas.mood import MoodSummaryEntry
from app.schemas.profile import ProfileUpdateRequest
from app.services.goals import update_user_goals
from app.services.healing_path import get_healing_path, get_user_stats
from app.services.mood import get_mood_summary
from app.services.profile import update_profile

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/users/me", response_model=UserResponse)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await update_profile(db, current_user, payload)
    return updated


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


@router.get("/users/me/mood-summary", response_model=list[MoodSummaryEntry])
async def get_mood_summary_endpoint(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return sparse mood entries for the last N days — used by the AI chatbot sidebar."""
    return await get_mood_summary(db, current_user.id, days)


@router.get("/users/me/stats", response_model=UserStatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user activity stats: exercises completed and current mood streak."""
    return await get_user_stats(db, current_user.id)


@router.get("/users/me/healing-path", response_model=HealingPathResponse)
async def healing_path(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's healing path progress across core self-care tasks."""
    return await get_healing_path(db, current_user.id)
