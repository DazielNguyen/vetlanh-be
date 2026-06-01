from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood import MoodEntry
from app.schemas.mood import MoodEntryCreate

_EDIT_WINDOW_HOURS = 1
# 1-day buffer so UTC+N clients can submit end-of-day entries without hitting a future-date error
_FUTURE_DATE_BUFFER_DAYS = 1


async def create_or_update_entry(
    db: AsyncSession, user_id: int, payload: MoodEntryCreate
) -> tuple[MoodEntry, bool]:
    """Create or update a mood entry.

    Returns (entry, created) where created=True on insert, False on update.
    Raises 409 if an entry exists and the 1-hour edit window has passed.
    Raises 422 if payload.date is more than 1 day in the future (timezone buffer).
    """
    today = datetime.now(tz=timezone.utc).date()
    if payload.date > today + timedelta(days=_FUTURE_DATE_BUFFER_DAYS):
        raise HTTPException(
            status_code=422,
            detail="Không thể tạo check-in cho ngày trong tương lai.",
        )

    result = await db.execute(
        select(MoodEntry).where(
            MoodEntry.user_id == user_id,
            MoodEntry.date == payload.date,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        entry = MoodEntry(
            user_id=user_id,
            date=payload.date,
            mood=payload.mood,
            energy=payload.energy,
            factors=payload.factors,
            note=payload.note,
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        return entry, True

    # Entry exists — check edit window
    cutoff = existing.created_at + timedelta(hours=_EDIT_WINDOW_HOURS)
    now = datetime.now(tz=timezone.utc)
    if now > cutoff:
        raise HTTPException(
            status_code=409,
            detail="Bạn chỉ có thể chỉnh sửa check-in trong vòng 1 giờ sau khi tạo.",
        )

    existing.mood = payload.mood
    existing.energy = payload.energy
    existing.factors = payload.factors
    existing.note = payload.note
    existing.updated_at = now
    await db.flush()
    await db.refresh(existing)
    return existing, False


async def list_entries(
    db: AsyncSession,
    user_id: int,
    start: date | None = None,
    end: date | None = None,
    limit: int = 90,
    offset: int = 0,
) -> list[MoodEntry]:
    query = select(MoodEntry).where(MoodEntry.user_id == user_id)
    if start:
        query = query.where(MoodEntry.date >= start)
    if end:
        query = query.where(MoodEntry.date <= end)
    query = query.order_by(MoodEntry.date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_daily_mood(db: AsyncSession, user_id: int, sentiment: str) -> None:
    """Update the user's daily mood score based on conversation sentiment.

    Placeholder — auto-aggregation rules deferred to product decision.
    # TODO(US-011 follow-up): wire to MoodEntry when aggregation rules are decided
    """
    pass
