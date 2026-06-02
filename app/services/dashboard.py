from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood import MoodEntry
from app.models.user import User
from app.schemas.dashboard import DashboardResponse, MoodSparkline
from app.schemas.exercise import MoodFilter
from app.services.exercise import get_recommended

_MOOD_TO_FILTER: dict[int, MoodFilter] = {
    1: MoodFilter.sad,
    2: MoodFilter.sad,
    3: MoodFilter.anxious,
    4: MoodFilter.need_energy,
    5: MoodFilter.need_energy,
}

# Vietnam standard time (no DST)
_VN_TZ = timezone(timedelta(hours=7))

# Look back this many days to compute streak (covers streaks up to 90 days)
_STREAK_LOOKBACK_DAYS = 90


def _greeting(display_name: str | None) -> str:
    local_hour = datetime.now(tz=_VN_TZ).hour
    name = display_name or "bạn"
    if local_hour < 12:
        return f"Buổi sáng tốt lành, {name}!"
    if local_hour < 18:
        return f"Buổi chiều vui vẻ, {name}!"
    return f"Buổi tối bình yên, {name}!"


def _compute_streak(entries: list[MoodEntry]) -> int:
    """Count consecutive days with a mood entry ending at the most recent date."""
    if not entries:
        return 0
    dates = sorted({e.date for e in entries}, reverse=True)
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak


async def get_dashboard(db: AsyncSession, user: User) -> DashboardResponse:
    # Use Vietnam local date so check-in state is correct at 23:xx VN time
    today = datetime.now(tz=_VN_TZ).date()
    week_start = today - timedelta(days=6)
    streak_start = today - timedelta(days=_STREAK_LOOKBACK_DAYS - 1)

    # Single query covers both sparkline window (7 days) and full streak lookback
    result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user.id, MoodEntry.date >= streak_start)
        .order_by(MoodEntry.date.desc())
    )
    all_entries: list[MoodEntry] = list(result.scalars().all())

    by_date = {e.date: e for e in all_entries}
    today_entry = by_date.get(today)

    sparkline = [
        MoodSparkline(
            date=week_start + timedelta(days=i),
            mood=by_date[week_start + timedelta(days=i)].mood
            if (week_start + timedelta(days=i)) in by_date
            else None,
        )
        for i in range(7)
    ]

    streak = _compute_streak(all_entries)

    # Use latest mood for exercise recommendations; fall back to "anxious" if no data
    if today_entry:
        mood_filter = _MOOD_TO_FILTER.get(today_entry.mood, MoodFilter.anxious)
    elif all_entries:
        mood_filter = _MOOD_TO_FILTER.get(all_entries[0].mood, MoodFilter.anxious)
    else:
        mood_filter = MoodFilter.anxious

    exercises = get_recommended(mood=mood_filter, limit=3)

    return DashboardResponse(
        greeting=_greeting(user.display_name),
        checked_in_today=today_entry is not None,
        today_mood=today_entry,  # type: ignore[arg-type]  # from_attributes handles ORM → schema
        streak_days=streak,
        mood_sparkline=sparkline,
        recommended_exercises=exercises,
    )
