import uuid
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionActiveRow,
    SubscriptionGrantRequest,
    SubscriptionPendingRow,
)

router = APIRouter()


def _pending_row(sub: Subscription, user: User) -> SubscriptionPendingRow:
    return SubscriptionPendingRow(
        id=sub.id,
        username=user.username,
        displayName=user.display_name,
        plan=sub.plan_name,
        duration=sub.duration_months,
        transferDate=sub.transfer_date,
        note=sub.transfer_note,
        amount_vnd=sub.amount_vnd,
    )


def _active_row(sub: Subscription, user: User) -> SubscriptionActiveRow:
    return SubscriptionActiveRow(
        id=sub.id,
        username=user.username,
        displayName=user.display_name,
        plan=sub.plan_name,
        grantedAt=sub.granted_at,
        expiresAt=sub.expires_at,
    )


@router.get("/subscriptions/pending", response_model=list[SubscriptionPendingRow])
async def list_pending_subscriptions(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .where(Subscription.status == "pending")
            .order_by(Subscription.created_at.desc())
        )
    ).all()
    return [_pending_row(sub, user) for sub, user in rows]


@router.get("/subscriptions/active", response_model=list[SubscriptionActiveRow])
async def list_active_subscriptions(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(tz=timezone.utc)
    rows = (
        await db.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .where(Subscription.status == "active", Subscription.expires_at > now)
            .order_by(Subscription.granted_at.desc())
        )
    ).all()
    return [_active_row(sub, user) for sub, user in rows]


@router.post("/subscriptions/{sub_id}/grant", response_model=SubscriptionActiveRow)
async def grant_subscription(
    sub_id: uuid.UUID,
    body: SubscriptionGrantRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(Subscription, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if sub.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending subscriptions can be granted")

    months = body.duration_months or sub.duration_months
    if not months or months < 1:
        raise HTTPException(status_code=422, detail="duration_months is required and must be >= 1")

    now = datetime.now(tz=timezone.utc)
    sub.status = "active"
    sub.granted_at = now
    # relativedelta handles calendar-correct month arithmetic (Jan 31 + 1M = Feb 28)
    sub.expires_at = now + relativedelta(months=months)
    sub.duration_months = months
    await db.flush()

    user = await db.get(User, sub.user_id)
    return _active_row(sub, user)


@router.post("/subscriptions/{sub_id}/reject", response_model=SubscriptionPendingRow)
async def reject_subscription(
    sub_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(Subscription, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if sub.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending subscriptions can be rejected")

    sub.status = "rejected"
    sub.rejected_at = datetime.now(tz=timezone.utc)
    await db.flush()

    user = await db.get(User, sub.user_id)
    return _pending_row(sub, user)
