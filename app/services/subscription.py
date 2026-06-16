from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription


async def get_subscription_status(
    db: AsyncSession, user_id: int
) -> tuple[str, str | None, datetime | None]:
    """Return (status, plan, expires_at) for the user's subscription.

    "pro": a currently-valid grant exists (canonical filter: status=='active' AND
    expires_at > now() — see app/models/subscription.py). Applied directly in the
    query rather than checked in Python, so this stays correct even if a user ends
    up with more than one status=='active' row.
    "expired": no currently-valid grant, but a past active grant exists.
    "none": never granted a subscription (pending/rejected requests don't count).
    """
    now = datetime.now(timezone.utc)

    current = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
        )
    ).scalars().first()
    if current is not None:
        return "pro", current.plan_name, current.expires_at

    lapsed = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == "active")
            .order_by(Subscription.granted_at.desc())
        )
    ).scalars().first()
    if lapsed is None:
        return "none", None, None
    return "expired", lapsed.plan_name, lapsed.expires_at
