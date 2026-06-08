from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.subscription import Subscription
from app.models.system_error import SystemError
from app.models.user import User
from app.schemas.admin import AdminStatsResponse

router = APIRouter()


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(tz=timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    active_users = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.last_active_at >= start_of_month)
        )
    ).scalar_one()

    monthly_revenue = (
        await db.execute(
            select(func.coalesce(func.sum(Subscription.amount_vnd), 0))
            .select_from(Subscription)
            .where(
                Subscription.status == "active",
                Subscription.expires_at > now,
                Subscription.granted_at >= start_of_month,
            )
        )
    ).scalar_one()

    unresolved_errors = (
        await db.execute(
            select(func.count())
            .select_from(SystemError)
            .where(SystemError.status == "open")
        )
    ).scalar_one()

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        monthly_revenue_vnd=monthly_revenue,
        unresolved_errors=unresolved_errors,
    )
