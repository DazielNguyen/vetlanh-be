from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import PendingSubmitRequest, PendingSubmitResponse

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("/pending", response_model=PendingSubmitResponse, status_code=201)
async def submit_pending_subscription(
    body: PendingSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Guard: one pending record per user — reject if already has status='pending'
    existing = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.id,
                Subscription.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A pending subscription request already exists for this user",
        )

    sub = Subscription(
        user_id=current_user.id,
        status="pending",
        plan_name=body.plan_name,
        duration_months=body.duration_months,
        amount_vnd=body.amount_vnd,
        transfer_date=body.transfer_date,
        transfer_note=body.transfer_note,
    )
    db.add(sub)
    await db.flush()
    return PendingSubmitResponse(id=sub.id)
