from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.feedback import FeedbackCreate, FeedbackResponse, format_feedback_id

router = APIRouter()

RATE_LIMIT_PER_HOUR = 5


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    body: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    window_start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    recent_count = (
        await db.execute(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.user_id == current_user.id, Feedback.created_at >= window_start)
        )
    ).scalar_one()
    if recent_count >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Feedback rate limit exceeded, try again later")

    feedback = Feedback(
        user_id=current_user.id,
        rating=body.rating,
        categories=body.categories,
        positive_comment=body.positive_comment,
        improvement_comment=body.improvement_comment,
        allow_contact=body.allow_contact,
        source_page=body.source_page,
        app_version=body.app_version,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return FeedbackResponse(
        id=format_feedback_id(feedback.id),
        rating=feedback.rating,
        categories=feedback.categories,
        positive_comment=feedback.positive_comment,
        improvement_comment=feedback.improvement_comment,
        allow_contact=feedback.allow_contact,
        source_page=feedback.source_page,
        app_version=feedback.app_version,
        status=feedback.status,
        created_at=feedback.created_at,
    )
