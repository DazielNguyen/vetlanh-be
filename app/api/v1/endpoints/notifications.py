"""Notification preference endpoints — US-031."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.notification import NotificationPreferenceOut, NotificationPreferenceUpdate, ShouldNotifyResponse
from app.services.notification import get_preference, should_notify, should_remind_exercise, update_preference

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/preference", response_model=NotificationPreferenceOut)
async def get_notification_preference(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-031: Get current notification preference (created with defaults if first call)."""
    return await get_preference(db, current_user.id)


@router.patch("/preference", response_model=NotificationPreferenceOut)
async def update_notification_preference(
    payload: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-031: Update notification preference fields."""
    return await update_preference(db, current_user.id, payload)


@router.get("/should-notify", response_model=ShouldNotifyResponse)
async def check_should_notify(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-031: Mobile calls this to decide whether to show a check-in reminder right now."""
    return await should_notify(db, current_user.id)


@router.get("/exercise-reminder", response_model=ShouldNotifyResponse)
async def check_exercise_reminder(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-032: Mobile calls this to decide whether to show a daily exercise reminder."""
    return await should_remind_exercise(db, current_user.id)
