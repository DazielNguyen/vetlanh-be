import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood import MoodEntry
from app.schemas.mood import HeatmapDay, HeatmapResponse, MoodEntryCreate, MoodFactor, MoodSummaryEntry, MoodTrendEntry, MoodTrendResponse

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
    if start is not None:
        query = query.where(MoodEntry.date >= start)
    if end is not None:
        query = query.where(MoodEntry.date <= end)
    query = query.order_by(MoodEntry.date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_trend(
    db: AsyncSession, user_id: int, period: Literal["week", "month"]
) -> MoodTrendResponse:
    today = datetime.now(tz=timezone.utc).date()
    days = 7 if period == "week" else 30
    start = today - timedelta(days=days - 1)

    result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user_id, MoodEntry.date >= start, MoodEntry.date <= today)
        .order_by(MoodEntry.date.asc())
    )
    db_entries: list[MoodEntry] = list(result.scalars().all())
    by_date = {e.date: e for e in db_entries}

    slots: list[MoodTrendEntry] = []
    for i in range(days):
        d = start + timedelta(days=i)
        entry = by_date.get(d)
        slots.append(
            MoodTrendEntry(
                date=d,
                mood=entry.mood if entry else None,
                energy=entry.energy if entry else None,
                factors=entry.factors if entry else [],
                note=entry.note if entry else None,
            )
        )

    filled = [s for s in slots if s.mood is not None]
    best_day = min(filled, key=lambda s: (-s.mood, s.date)).date if filled else None  # type: ignore[arg-type]
    worst_day = min(filled, key=lambda s: (s.mood, s.date)).date if filled else None  # type: ignore[arg-type]
    average_mood = round(sum(s.mood for s in filled) / len(filled), 2) if filled else None  # type: ignore[arg-type]

    return MoodTrendResponse(
        period=period,
        start=start,
        end=today,
        entries=slots,
        best_day=best_day,
        worst_day=worst_day,
        average_mood=average_mood,
    )


async def get_heatmap(db: AsyncSession, user_id: int, year: int, month: int) -> HeatmapResponse:
    """Return sparse list of days that have a mood entry for the given year/month."""
    _, last_day = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)

    result = await db.execute(
        select(MoodEntry.date, MoodEntry.mood)
        .where(MoodEntry.user_id == user_id, MoodEntry.date >= start, MoodEntry.date <= end)
        .order_by(MoodEntry.date)
    )
    rows = result.all()
    days = [HeatmapDay(date=row.date, mood_score=row.mood) for row in rows]
    return HeatmapResponse(year=year, month=month, days=days)


_VN_TZ = timezone(timedelta(hours=7))


async def get_mood_summary(
    db: AsyncSession, user_id: int, days: int = 7
) -> list[MoodSummaryEntry]:
    """Return mood entries for the last N days, sparse (only days with entries).

    Uses VN local date so the window matches the user's calendar day, consistent
    with how the dashboard computes checked_in_today.
    """
    today = datetime.now(tz=_VN_TZ).date()
    start = today - timedelta(days=days - 1)
    result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user_id, MoodEntry.date >= start, MoodEntry.date <= today)
        .order_by(MoodEntry.date.asc())
    )
    entries = list(result.scalars().all())
    return [MoodSummaryEntry(date=e.date, sentiment_score=e.mood) for e in entries]


_MOOD_FACTORS: list[MoodFactor] = [
    MoodFactor(key="work", label="Công việc"),
    MoodFactor(key="sleep", label="Giấc ngủ"),
    MoodFactor(key="exercise", label="Tập thể dục"),
    MoodFactor(key="diet", label="Ăn uống"),
    MoodFactor(key="relationships", label="Mối quan hệ"),
    MoodFactor(key="weather", label="Thời tiết"),
    MoodFactor(key="health", label="Sức khỏe"),
    MoodFactor(key="finance", label="Tài chính"),
    MoodFactor(key="study", label="Học tập"),
]


def get_mood_factors() -> list[MoodFactor]:
    return _MOOD_FACTORS


async def update_daily_mood(db: AsyncSession, user_id: int, sentiment: str) -> None:
    """Update the user's daily mood score based on conversation sentiment.

    Placeholder — auto-aggregation rules deferred to product decision.
    # TODO(US-011 follow-up): wire to MoodEntry when aggregation rules are decided
    """
    pass
