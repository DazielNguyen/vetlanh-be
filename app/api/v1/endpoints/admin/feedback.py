from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.feedback import Feedback, FeedbackAuditLog
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.feedback import (
    AdminFeedbackListResponse,
    AdminFeedbackRow,
    AdminFeedbackStatsResponse,
    AdminFeedbackUpdate,
    CategoryCount,
    Category as CategoryType,
    FeedbackUserSummary,
    Status as StatusType,
    SubscriptionStatus as SubscriptionStatusType,
    format_feedback_id,
    parse_feedback_id,
)

router = APIRouter()

SORTABLE_FIELDS = {"created_at": Feedback.created_at, "rating": Feedback.rating}
SortParam = Literal["created_at", "-created_at", "rating", "-rating"]
UNRESOLVED_STATUSES = ("new", "reviewing", "planned")


def _subscription_status(status: str | None, expires_at: datetime | None) -> str:
    now = datetime.now(tz=timezone.utc)
    if status == "active" and expires_at and expires_at > now:
        return "pro"
    if status == "expired" or (status == "active" and expires_at and expires_at <= now):
        return "expired"
    return "none"


def _subscription_status_expr(sub_status_col, sub_expires_col, now: datetime):
    """SQL equivalent of _subscription_status(), for filtering/joining in the list query."""
    active_not_expired = and_(sub_status_col == "active", sub_expires_col.is_not(None), sub_expires_col > now)
    expired = or_(
        sub_status_col == "expired",
        and_(sub_status_col == "active", sub_expires_col.is_not(None), sub_expires_col <= now),
    )
    return case((active_not_expired, literal("pro")), (expired, literal("expired")), else_=literal("none"))


def _latest_subscription_subquery():
    return select(
        Subscription.user_id,
        Subscription.status,
        Subscription.expires_at,
        func.row_number()
        .over(partition_by=Subscription.user_id, order_by=Subscription.created_at.desc())
        .label("rn"),
    ).subquery()


def _resolve_feedback_id(formatted_id: str) -> int:
    raw_id = parse_feedback_id(formatted_id)
    if raw_id is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return raw_id


def _to_row(feedback: Feedback, user: User, subscription_status: str) -> AdminFeedbackRow:
    return AdminFeedbackRow(
        id=format_feedback_id(feedback.id),
        rating=feedback.rating,
        categories=feedback.categories,
        positive_comment=feedback.positive_comment,
        improvement_comment=feedback.improvement_comment,
        allow_contact=feedback.allow_contact,
        source_page=feedback.source_page,
        app_version=feedback.app_version,
        status=feedback.status,
        internal_note=feedback.internal_note,
        created_at=feedback.created_at,
        user=FeedbackUserSummary(
            id=user.id,
            display_name=user.display_name,
            email=user.email,
            subscription_status=subscription_status,
        ),
    )


async def _latest_subscription(db: AsyncSession, user_id: int) -> tuple[str | None, datetime | None]:
    row = (
        await db.execute(
            select(Subscription.status, Subscription.expires_at)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).first()
    return (row.status, row.expires_at) if row else (None, None)


@router.get("/feedback", response_model=AdminFeedbackListResponse)
async def list_admin_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    rating: int | None = Query(default=None, ge=1, le=5),
    category: CategoryType | None = Query(default=None),
    status: StatusType | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    allow_contact: bool | None = Query(default=None),
    subscription_status: SubscriptionStatusType | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    sort: SortParam = Query(default="-created_at"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    sub_ranked = _latest_subscription_subquery()
    now = datetime.now(tz=timezone.utc)
    sub_status_expr = _subscription_status_expr(sub_ranked.c.status, sub_ranked.c.expires_at, now).label(
        "subscription_status"
    )

    query = (
        select(Feedback, User, sub_status_expr)
        .join(User, Feedback.user_id == User.id)
        .outerjoin(sub_ranked, (sub_ranked.c.user_id == User.id) & (sub_ranked.c.rn == 1))
    )

    if rating is not None:
        query = query.where(Feedback.rating == rating)
    if category is not None:
        query = query.where(Feedback.categories.any(category))
    if status is not None:
        query = query.where(Feedback.status == status)
    if allow_contact is not None:
        query = query.where(Feedback.allow_contact == allow_contact)
    if subscription_status is not None:
        query = query.where(sub_status_expr == subscription_status)
    if created_from is not None:
        query = query.where(Feedback.created_at >= created_from)
    if created_to is not None:
        query = query.where(Feedback.created_at <= created_to)
    if search:
        safe = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if safe:
            pattern = f"%{safe}%"
            query = query.where(
                User.display_name.ilike(pattern, escape="\\")
                | User.email.ilike(pattern, escape="\\")
                | Feedback.positive_comment.ilike(pattern, escape="\\")
                | Feedback.improvement_comment.ilike(pattern, escape="\\")
            )

    desc = sort.startswith("-")
    sort_col = SORTABLE_FIELDS.get(sort[1:] if desc else sort, Feedback.created_at)
    query = query.order_by(sort_col.desc() if desc else sort_col.asc())

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).all()

    items = [_to_row(row.Feedback, row.User, row.subscription_status) for row in rows]
    return AdminFeedbackListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/feedback/stats", response_model=AdminFeedbackStatsResponse)
async def get_admin_feedback_stats(
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if created_from is not None:
        filters.append(Feedback.created_at >= created_from)
    if created_to is not None:
        filters.append(Feedback.created_at <= created_to)

    total = (await db.execute(select(func.count()).where(*filters).select_from(Feedback))).scalar_one()
    average_rating = (await db.execute(select(func.avg(Feedback.rating)).where(*filters))).scalar_one()
    unresolved = (
        await db.execute(
            select(func.count()).select_from(Feedback).where(*filters, Feedback.status.in_(UNRESOLVED_STATUSES))
        )
    ).scalar_one()
    # Independent of created_from/created_to: always a rolling 30-day trend signal.
    last_30_days = (
        await db.execute(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.created_at >= datetime.now(tz=timezone.utc) - timedelta(days=30))
        )
    ).scalar_one()

    rating_rows = (
        await db.execute(select(Feedback.rating, func.count()).where(*filters).group_by(Feedback.rating))
    ).all()
    rating_distribution = {str(r): 0 for r in range(1, 6)}
    for rating_value, count in rating_rows:
        rating_distribution[str(rating_value)] = count

    category_rows = (
        await db.execute(
            select(func.unnest(Feedback.categories).label("category"), func.count())
            .where(*filters)
            .group_by("category")
            .order_by(func.count().desc())
        )
    ).all()

    return AdminFeedbackStatsResponse(
        total=total,
        average_rating=round(float(average_rating), 2) if average_rating is not None else 0.0,
        unresolved=unresolved,
        last_30_days=last_30_days,
        rating_distribution=rating_distribution,
        top_categories=[CategoryCount(category=c, count=n) for c, n in category_rows],
    )


@router.get("/feedback/{feedback_id}", response_model=AdminFeedbackRow)
async def get_admin_feedback(
    feedback_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    feedback = await db.get(Feedback, _resolve_feedback_id(feedback_id))
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    user = await db.get(User, feedback.user_id)
    sub_status, sub_expires = await _latest_subscription(db, user.id)
    return _to_row(feedback, user, _subscription_status(sub_status, sub_expires))


@router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackRow)
async def update_admin_feedback(
    feedback_id: str,
    body: AdminFeedbackUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    feedback = await db.get(Feedback, _resolve_feedback_id(feedback_id))
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    old_status = feedback.status
    # "internal_note" in body.model_fields_set distinguishes "field omitted" from
    # "field explicitly sent as null" — both parse to None otherwise, which would
    # make an explicit clear silently fall back to the old note.
    note_provided = "internal_note" in body.model_fields_set
    effective_note = body.internal_note if note_provided else feedback.internal_note
    if body.status == "dismissed" and not effective_note:
        raise HTTPException(status_code=422, detail="internal_note is required when dismissing feedback")

    if note_provided:
        feedback.internal_note = body.internal_note
    if body.status is not None:
        feedback.status = body.status
        db.add(
            FeedbackAuditLog(
                feedback_id=feedback.id,
                admin_user_id=admin.id,
                old_status=old_status,
                new_status=body.status,
            )
        )

    await db.flush()
    await db.refresh(feedback)

    user = await db.get(User, feedback.user_id)
    sub_status, sub_expires = await _latest_subscription(db, user.id)
    return _to_row(feedback, user, _subscription_status(sub_status, sub_expires))
