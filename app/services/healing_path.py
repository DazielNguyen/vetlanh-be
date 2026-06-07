from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import UserExerciseLog
from app.models.mood import MoodEntry
from app.schemas.healing_path import HealingPathResponse, HealingTask, UserStatsResponse
from app.services._streak import STREAK_LOOKBACK_DAYS, compute_streak

_VN_TZ = timezone(timedelta(hours=7))

# Number of completions required to reach 100% on each task
_MOOD_CHECKINS_FOR_FULL = 7
_EXERCISES_FOR_FULL = 5
_STREAK_DAYS_FOR_FULL = 7


async def _fetch_user_activity(db: AsyncSession, user_id: int) -> tuple[int, list[MoodEntry]]:
    """Fetch exercise count and recent mood entries in two sequential queries."""
    exercises_result = await db.execute(
        select(func.count()).select_from(UserExerciseLog).where(UserExerciseLog.user_id == user_id)
    )
    exercise_count: int = exercises_result.scalar_one()

    today = datetime.now(tz=_VN_TZ).date()
    streak_start = today - timedelta(days=STREAK_LOOKBACK_DAYS - 1)
    mood_result = await db.execute(
        select(MoodEntry).where(MoodEntry.user_id == user_id, MoodEntry.date >= streak_start)
    )
    mood_entries = list(mood_result.scalars().all())
    return exercise_count, mood_entries


async def get_user_stats(db: AsyncSession, user_id: int) -> UserStatsResponse:
    exercise_count, mood_entries = await _fetch_user_activity(db, user_id)
    today = datetime.now(tz=_VN_TZ).date()
    streak = compute_streak({e.date for e in mood_entries}, today)
    return UserStatsResponse(exercises_completed=exercise_count, streak_days=streak)


async def get_healing_path(db: AsyncSession, user_id: int) -> HealingPathResponse:
    """Return a static healing path with progress derived from real activity data.

    A full progress-tracking data model requires FE alignment first (per plan notes).
    Progress_pct is approximated from existing signals: mood check-ins and exercise logs.
    """
    exercise_count, mood_entries = await _fetch_user_activity(db, user_id)
    today = datetime.now(tz=_VN_TZ).date()
    streak = compute_streak({e.date for e in mood_entries}, today)
    mood_count = len(mood_entries)

    task1_pct = min(100, mood_count * 100 // _MOOD_CHECKINS_FOR_FULL)
    task2_pct = min(100, exercise_count * 100 // _EXERCISES_FOR_FULL)
    task3_pct = min(100, streak * 100 // _STREAK_DAYS_FOR_FULL)

    tasks = [
        HealingTask(
            id="mood-tracking",
            title="Theo dõi cảm xúc",
            subtitle="Kiểm tra tâm trạng mỗi ngày để hiểu bản thân",
            progress_pct=task1_pct,
            status="active",
        ),
        HealingTask(
            id="breathing-practice",
            title="Luyện thở chánh niệm",
            subtitle="Thực hành bài tập thở để giảm lo âu",
            progress_pct=task2_pct,
            status="active" if task1_pct >= 30 else "locked",
            unlock_label=None if task1_pct >= 30 else "Hoàn thành 3 lần check-in",
        ),
        HealingTask(
            id="daily-streak",
            title="Xây dựng thói quen",
            subtitle="Duy trì chuỗi ngày liên tiếp",
            progress_pct=task3_pct,
            status="active" if task2_pct >= 30 else "upcoming",
            unlock_label=None if task2_pct >= 30 else "Ngày 3",
        ),
    ]

    return HealingPathResponse(tasks=tasks)
