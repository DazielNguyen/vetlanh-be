from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import AdminUserListResponse, AdminUserRow

router = APIRouter()


def _subscription_status(status: str | None, expires_at: datetime | None) -> str:
    now = datetime.now(tz=timezone.utc)
    if status == "active" and expires_at and expires_at > now:
        return "Pro"
    if status == "expired" or (status == "active" and expires_at and expires_at <= now):
        return "Expired"
    return "None"


def _build_query(search: str | None):
    # Window function: rank subscriptions per user by created_at, keep rank=1 (latest)
    sub_ranked = (
        select(
            Subscription.user_id,
            Subscription.status,
            Subscription.expires_at,
            func.row_number()
            .over(
                partition_by=Subscription.user_id,
                order_by=Subscription.created_at.desc(),
            )
            .label("rn"),
        ).subquery()
    )

    q = (
        select(
            User,
            sub_ranked.c.status.label("sub_status"),
            sub_ranked.c.expires_at.label("sub_expires"),
        ).outerjoin(
            sub_ranked,
            (sub_ranked.c.user_id == User.id) & (sub_ranked.c.rn == 1),
        )
    )

    if search:
        # Escape SQL wildcard chars so user input is treated as a literal substring.
        safe = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if safe:
            pattern = f"%{safe}%"
            q = q.where(
                User.username.ilike(pattern, escape="\\")
                | User.display_name.ilike(pattern, escape="\\")
            )
    return q


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    base = _build_query(search)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(base.offset((page - 1) * limit).limit(limit))
    ).all()

    items = [
        AdminUserRow(
            id=row.User.id,
            username=row.User.username,
            displayName=row.User.display_name,
            accountType=row.User.account_type,
            subscriptionStatus=_subscription_status(row.sub_status, row.sub_expires),
            subscriptionExpiry=row.sub_expires,
            joinDate=row.User.created_at,
            lastActiveAt=row.User.last_active_at,
            isVerified=row.User.is_verified,
            isActive=row.User.is_active,
        )
        for row in rows
    ]

    return AdminUserListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/users/{user_id}/approve", response_model=AdminUserRow)
async def approve_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually verify a user account — for accounts stuck unverified
    (e.g. email verification link never clicked or never received)."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified and user.is_active:
        raise HTTPException(status_code=409, detail="User is already verified and active")

    user.is_verified = True
    user.is_active = True
    user.verification_token = None
    user.verification_token_expires_at = None
    await db.flush()  # commit happens in get_db on response success

    sub_row = (
        await db.execute(
            select(Subscription.status, Subscription.expires_at)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).first()
    sub_status, sub_expires = sub_row if sub_row else (None, None)

    return AdminUserRow(
        id=user.id,
        username=user.username,
        displayName=user.display_name,
        accountType=user.account_type,
        subscriptionStatus=_subscription_status(sub_status, sub_expires),
        subscriptionExpiry=sub_expires,
        joinDate=user.created_at,
        lastActiveAt=user.last_active_at,
        isVerified=user.is_verified,
        isActive=user.is_active,
    )
