from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood import MoodEntry
from app.models.user import User
from app.schemas.dashboard import DailyQuoteResponse, DashboardResponse, MoodSparkline, StressLevel
from app.schemas.exercise import MoodFilter
from app.services.exercise import get_recommended

_QUOTES: list[tuple[str, str | None]] = [
    ("Chữa lành không phải đường thẳng, nhưng mỗi bước tiến đều là một chiến thắng.", None),
    ("Bạn không cần phải ổn định mọi lúc. Cho phép bản thân cảm nhận.", None),
    ("Sức mạnh không phải là không sợ hãi, mà là tiếp tục dù đang sợ.", "Nelson Mandela"),
    ("Mỗi ngày là một cơ hội mới để bắt đầu lại.", None),
    ("Chăm sóc bản thân không phải ích kỷ — đó là điều cần thiết.", None),
    ("Hơi thở luôn ở đây. Hiện tại luôn ở đây. Bạn không cô đơn.", None),
    ("Tiến bộ nhỏ vẫn là tiến bộ. Hãy tự hào về bản thân.", None),
    ("Bình yên không đến từ bên ngoài — nó bắt đầu từ bên trong bạn.", None),
    ("Bạn đã vượt qua 100% những ngày khó khăn trước đây.", None),
    ("Cảm xúc của bạn là thật và xứng đáng được lắng nghe.", None),
    ("Không cần hoàn hảo — chỉ cần tiếp tục.", None),
    ("Mỗi đêm tối rồi cũng qua đi. Bình minh luôn đến.", None),
]


def get_daily_quote() -> DailyQuoteResponse:
    # Rotate deterministically by day-of-year so everyone gets the same quote each day
    day_index = datetime.now(tz=timezone.utc).timetuple().tm_yday
    text, author = _QUOTES[day_index % len(_QUOTES)]
    return DailyQuoteResponse(text=text, author=author)


def _stress_level(avg_mood: float | None) -> StressLevel | None:
    if avg_mood is None:
        return None
    # mood 1-5: low mood = high stress
    if avg_mood >= 3.5:
        return StressLevel.low
    if avg_mood >= 2.5:
        return StressLevel.medium
    return StressLevel.high


def _trend_text(current_avg: float | None, prev_avg: float | None) -> str | None:
    if current_avg is None or prev_avg is None or prev_avg == 0:
        return None
    delta_pct = round(abs(current_avg - prev_avg) / prev_avg * 100)
    if delta_pct < 3:
        return "ổn định tuần này"
    if current_avg > prev_avg:
        return f"tốt hơn ~{delta_pct}% tuần này"
    return f"xấu hơn ~{delta_pct}% tuần này"


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


def _avg_mood(entries_by_date: dict, end_offset: int, days: int, anchor: date) -> float | None:
    """Average mood for `days` days ending `end_offset` days before anchor (inclusive)."""
    values = [
        entries_by_date[d].mood
        for i in range(days)
        if (d := anchor - timedelta(days=end_offset + i)) in entries_by_date
    ]
    return sum(values) / len(values) if values else None


async def get_dashboard(db: AsyncSession, user: User) -> DashboardResponse:
    today = datetime.now(tz=_VN_TZ).date()
    week_start = today - timedelta(days=6)
    window_start = today - timedelta(days=_STREAK_LOOKBACK_DAYS - 1)

    result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user.id, MoodEntry.date >= window_start)
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

    if today_entry:
        mood_filter = _MOOD_TO_FILTER.get(today_entry.mood, MoodFilter.anxious)
    elif all_entries:
        mood_filter = _MOOD_TO_FILTER.get(all_entries[0].mood, MoodFilter.anxious)
    else:
        mood_filter = MoodFilter.anxious

    exercises = get_recommended(mood=mood_filter, limit=3)

    current_avg = _avg_mood(by_date, end_offset=0, days=7, anchor=today)
    prev_avg = _avg_mood(by_date, end_offset=7, days=7, anchor=today)

    return DashboardResponse(
        greeting=_greeting(user.display_name),
        checked_in_today=today_entry is not None,
        today_mood=today_entry,  # type: ignore[arg-type]
        streak_days=streak,
        mood_sparkline=sparkline,
        recommended_exercises=exercises,
        stress_level=_stress_level(current_avg),
        stress_trend_text=_trend_text(current_avg, prev_avg),
    )
