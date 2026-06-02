"""Badge computation and notification tracking for US-027."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badge_notification import UserBadgeNotification
from app.models.mood import MoodEntry
from app.schemas.badge import BadgeOut, BadgesResponse

_MILESTONES: list[tuple[int, str, str]] = [
    (3, "first-flame", "Ngọn lửa đầu tiên"),
    (7, "week-warrior", "Chiến binh một tuần"),
    (21, "habit-builder", "Xây dựng thói quen"),
    (30, "monthly-champion", "Nhà vô địch tháng"),
    (60, "resilience-master", "Bậc thầy kiên cường"),
]

_STREAK_LOOKBACK_DAYS = 90


def _compute_streak(entries: list[MoodEntry]) -> int:
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


async def get_badges(db: AsyncSession, user_id: int) -> BadgesResponse:
    lookback = date.today() - timedelta(days=_STREAK_LOOKBACK_DAYS - 1)
    result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user_id, MoodEntry.date >= lookback)
        .order_by(MoodEntry.date.desc())
    )
    entries = list(result.scalars().all())
    streak = _compute_streak(entries)

    notified_result = await db.execute(
        select(UserBadgeNotification.milestone_days).where(
            UserBadgeNotification.user_id == user_id
        )
    )
    already_notified: set[int] = set(notified_result.scalars().all())

    badges: list[BadgeOut] = []
    new_milestones: list[int] = []

    for days, slug, label in _MILESTONES:
        unlocked = streak >= days
        is_new = unlocked and days not in already_notified
        if is_new:
            new_milestones.append(days)
        badges.append(BadgeOut(slug=slug, label=label, milestone_days=days, unlocked=unlocked, is_new=is_new))

    # Persist new milestone notifications so they won't be "new" again next call
    for days in new_milestones:
        db.add(UserBadgeNotification(user_id=user_id, milestone_days=days))
    if new_milestones:
        await db.flush()

    return BadgesResponse(streak_days=streak, badges=badges)
