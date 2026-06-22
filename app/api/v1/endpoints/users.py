from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, is_admin_user
from app.core.rate_limit import limiter
from app.core.upload import save_upload
from app.models.user import User
from app.schemas.auth import AvatarResponse, EmailChangeRequest, MessageResponse, UserResponse
from app.schemas.goals import GOAL_LABELS, GoalsUpdateRequest
from app.schemas.healing_path import HealingPathResponse, UserStatsResponse
from app.schemas.mood import MoodSummaryEntry
from app.schemas.profile import ProfileUpdateRequest
from app.services.email import send_email_change_alert, send_email_change_confirmation
from app.services.goals import update_user_goals
from app.services.settings import request_email_change
from app.services.healing_path import get_healing_path, get_user_stats
from app.services.mood import get_mood_summary
from app.services.profile import update_profile
from app.services.subscription import get_subscription_status

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_status, sub_plan, sub_expires_at = await get_subscription_status(db, current_user.id)
    return UserResponse.model_validate(current_user).model_copy(
        update={
            "is_admin": is_admin_user(current_user),
            "subscription_status": sub_status,
            "subscription_plan": sub_plan,
            "subscription_expires_at": sub_expires_at,
        }
    )


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


_MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/users/me/avatar", response_model=AvatarResponse)
@limiter.limit("10/minute")
async def upload_avatar(
    request: Request,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.size is not None and file.size > _MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Kích thước file không được vượt quá 5MB.")
    if file.size is None:
        contents = await file.read()
        if len(contents) > _MAX_AVATAR_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Kích thước file không được vượt quá 5MB.")
        await file.seek(0)

    avatar_url = await save_upload(file, "avatars")
    current_user.avatar_url = avatar_url
    await db.commit()
    return AvatarResponse(avatar_url=avatar_url)


@router.patch("/users/me/email", response_model=MessageResponse)
@limiter.limit("3/hour")
async def change_email(
    request: Request,
    body: EmailChangeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_email = current_user.email
    token = await request_email_change(db, current_user, body.new_email, body.current_password)
    background_tasks.add_task(send_email_change_confirmation, body.new_email, token)
    if old_email:
        background_tasks.add_task(send_email_change_alert, old_email)
    return MessageResponse(message="Email xác thực đã được gửi đến địa chỉ mới của bạn.")
