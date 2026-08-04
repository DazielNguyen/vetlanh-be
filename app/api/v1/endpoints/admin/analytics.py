from datetime import date, datetime, time, timezone

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.subscription import Subscription
from app.models.telemetry import Event
from app.models.user import User
from app.schemas.telemetry import (
    ACTIVE_EVENT_NAMES,
    ConversionRateResponse,
    FeatureUsageRow,
    MauRow,
    PageViewRow,
)

router = APIRouter(prefix="/analytics")


def _day_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(to_date, time.max, tzinfo=timezone.utc)
    return start, end


@router.get("/conversion-rate", response_model=ConversionRateResponse)
async def get_conversion_rate(
    joined_from: date = Query(...),
    joined_to: date = Query(...),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end = _day_bounds(joined_from, joined_to)

    joined_count = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.created_at >= start, User.created_at <= end)
        )
    ).scalar_one()

    converted_count = (
        await db.execute(
            select(func.count(distinct(User.id)))
            .select_from(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                User.created_at >= start,
                User.created_at <= end,
                Subscription.granted_at.is_not(None),
            )
        )
    ).scalar_one()

    rate = converted_count / joined_count if joined_count else 0.0

    return ConversionRateResponse(
        joined_count=joined_count,
        converted_count=converted_count,
        conversion_rate=rate,
    )


@router.get("/feature-usage", response_model=list[FeatureUsageRow])
async def get_feature_usage(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end = _day_bounds(from_, to)

    rows = (
        await db.execute(
            select(Event.event_name, func.count())
            .where(Event.created_at >= start, Event.created_at <= end)
            .group_by(Event.event_name)
            .order_by(func.count().desc())
        )
    ).all()

    return [FeatureUsageRow(event_name=event_name, count=count) for event_name, count in rows]


@router.get("/mau", response_model=list[MauRow])
async def get_mau(
    months: int = Query(default=6, ge=1, le=24),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(tz=timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    earliest_month_start = current_month_start - relativedelta(months=months - 1)

    month_bucket = func.date_trunc("month", Event.created_at).label("month_bucket")
    rows = (
        await db.execute(
            select(month_bucket, func.count(distinct(Event.user_id)))
            .where(
                Event.created_at >= earliest_month_start,
                Event.event_name.in_(ACTIVE_EVENT_NAMES),
                Event.user_id.is_not(None),
            )
            .group_by(month_bucket)
        )
    ).all()

    counts_by_month = {bucket.strftime("%Y-%m"): count for bucket, count in rows}

    result = []
    for i in range(months):
        month_start = earliest_month_start + relativedelta(months=i)
        key = month_start.strftime("%Y-%m")
        result.append(MauRow(month=key, active_users=counts_by_month.get(key, 0)))

    return result


@router.get("/page-views", response_model=list[PageViewRow])
async def get_page_views(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end = _day_bounds(from_, to)

    day_bucket = func.date_trunc("day", Event.created_at).label("day_bucket")
    rows = (
        await db.execute(
            select(day_bucket, func.count())
            .where(
                Event.created_at >= start,
                Event.created_at <= end,
                Event.event_name == "page_view",
            )
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()

    return [PageViewRow(date=bucket.strftime("%Y-%m-%d"), count=count) for bucket, count in rows]
