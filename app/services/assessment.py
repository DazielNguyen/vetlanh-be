from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.schemas.assessment import PHQ9ReminderResponse, Severity

_REMINDER_DAYS = 14
_HISTORY_DEFAULT_LIMIT = 50


def calculate_phq9(answers: list[int]) -> tuple[int, str]:
    """Return (score, severity) using DSM-5 PHQ-9 cutoffs."""
    score = sum(answers)
    if score <= 4:
        severity = Severity.MINIMAL
    elif score <= 9:
        severity = Severity.MILD
    elif score <= 14:
        severity = Severity.MODERATE
    else:
        severity = Severity.SEVERE
    return score, severity


async def submit_phq9(db: AsyncSession, user_id: int, answers: list[int]) -> Assessment:
    score, severity = calculate_phq9(answers)
    q1, q2, q3, q4, q5, q6, q7, q8, q9 = answers
    assessment = Assessment(
        user_id=user_id,
        q1=q1, q2=q2, q3=q3, q4=q4, q5=q5,
        q6=q6, q7=q7, q8=q8, q9=q9,
        score=score,
        severity=severity,
    )
    db.add(assessment)
    await db.flush()
    await db.refresh(assessment)
    return assessment


async def get_latest_phq9(db: AsyncSession, user_id: int) -> Assessment | None:
    result = await db.execute(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_phq9_history(
    db: AsyncSession,
    user_id: int,
    limit: int = _HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> list[tuple[Assessment, int | None]]:
    """Return assessments newest-first (paginated), each paired with its score_delta vs previous.

    score_delta = this_score - previous_score (negative means improvement).
    The oldest record in each page has delta=None when it is the absolute oldest; when
    pagination cuts it off, its predecessor is outside the page so delta is also None.
    """
    result = await db.execute(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at.desc())
        .limit(limit + 1)  # fetch one extra to determine if a previous record exists
        .offset(offset)
    )
    rows: list[Assessment] = list(result.scalars().all())
    has_extra = len(rows) > limit
    page = rows[:limit]

    pairs: list[tuple[Assessment, int | None]] = []
    for i, assessment in enumerate(page):
        if i + 1 < len(page):
            delta = assessment.score - page[i + 1].score
        elif has_extra:
            # There is a predecessor outside this page — delta unknown for last row
            delta = None
        else:
            delta = None
        pairs.append((assessment, delta))
    return pairs


async def get_phq9_reminder(db: AsyncSession, user_id: int) -> PHQ9ReminderResponse:
    latest = await get_latest_phq9(db, user_id)
    if latest is None:
        return PHQ9ReminderResponse(
            due=True,
            days_since_last=None,
            next_due_in_days=0,
            last_submitted_at=None,
        )
    now = datetime.now(tz=timezone.utc)
    # Normalize created_at: tz-aware on PostgreSQL, tz-naive on SQLite — handle both
    last_at = (
        latest.created_at
        if latest.created_at.tzinfo is not None
        else latest.created_at.replace(tzinfo=timezone.utc)
    )
    days_since = (now.date() - last_at.date()).days
    next_due_in = max(0, _REMINDER_DAYS - days_since)
    return PHQ9ReminderResponse(
        due=days_since >= _REMINDER_DAYS,
        days_since_last=days_since,
        next_due_in_days=next_due_in,
        last_submitted_at=last_at,
    )
