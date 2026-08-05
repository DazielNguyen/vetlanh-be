"""Rule-based personalized dashboard recommendation — no LLM, no new persistence.

Signal precedence (first match wins): PHQ-9 Moderate/Severe within the last
30 days > mood-trend decline > PHQ-9 Mild > most recent mood entry.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.mood import MoodEntry
from app.schemas.exercise import MoodFilter
from app.services.exercise import get_exercise, get_recommended

# Vietnam standard time (no DST) — mirrors app/services/dashboard.py's anchor.
_VN_TZ = timezone(timedelta(hours=7))

_MIN_RECENT_ENTRIES = 3
_PHQ9_RECENCY_DAYS = 30
# Same week-over-week delta threshold already tuned for the dashboard's stress trend text.
_TREND_DELTA_PCT = 3

_MOOD_TO_FILTER: dict[int, MoodFilter] = {
    1: MoodFilter.sad,
    2: MoodFilter.sad,
    3: MoodFilter.anxious,
    4: MoodFilter.need_energy,
    5: MoodFilter.need_energy,
}

# Reserved exclusively for the PHQ-9 Moderate/Severe branch — never an activating
# ("need_energy") exercise from the general mood-tag catalog.
_CALMING_ALLOW_LIST = [
    "box-breathing",
    "breathing-4-7-8",
    "grounding-54321",
    "meditation-anxiety",
]

# Fail loudly at import time if a future catalog edit removes one of these slugs —
# silently falling through to a lower-precedence branch could pick an energizing
# exercise for a Moderate/Severe user instead.
assert all(get_exercise(slug) is not None for slug in _CALMING_ALLOW_LIST), (
    "One or more _CALMING_ALLOW_LIST slugs no longer exist in the exercise catalog"
)

# Closed set of rationale sentences — never interpolate scores/severity/journal text.
_RATIONALE = {
    "phq9_high": "Một bài tập nhẹ nhàng có thể giúp bạn lấy lại cảm giác bình tĩnh lúc này.",
    "trend_decline": "Vì tuần này tâm trạng của bạn có phần chùng xuống so với tuần trước.",
    "phq9_mild": "Một bài tập ngắn có thể giúp bạn cảm thấy nhẹ nhõm hơn.",
    "fallback": "Dựa trên cảm xúc gần đây nhất của bạn, đây là gợi ý dành cho bạn.",
}


@dataclass
class RecommendationResult:
    title: str
    rationale: str
    url: str


def _build_url(slug: str) -> str:
    """Reuse the exact FE Next.js route template shipped in mood_analysis.py's _safe_action."""
    return f"/services/exercises/{slug}"


def _avg_mood(
    entries_by_date: dict[date, MoodEntry], end_offset: int, days: int, anchor: date
) -> float | None:
    values = [
        entries_by_date[d].mood
        for i in range(days)
        if (d := anchor - timedelta(days=end_offset + i)) in entries_by_date
    ]
    return sum(values) / len(values) if values else None


def _trend_declined(current_avg: float | None, prev_avg: float | None) -> bool:
    if current_avg is None or prev_avg is None or prev_avg == 0:
        return False
    delta_pct = abs(current_avg - prev_avg) / prev_avg * 100
    return delta_pct >= _TREND_DELTA_PCT and current_avg < prev_avg


def _pick_calming_exercise() -> RecommendationResult | None:
    for slug in _CALMING_ALLOW_LIST:
        exercise = get_exercise(slug)
        if exercise is not None:
            return RecommendationResult(
                title=exercise.title,
                rationale=_RATIONALE["phq9_high"],
                url=_build_url(exercise.slug),
            )
    return None


def _pick_by_mood(mood_value: int, rationale_key: str) -> RecommendationResult | None:
    mood_filter = _MOOD_TO_FILTER.get(mood_value, MoodFilter.anxious)
    exercises = get_recommended(mood=mood_filter, limit=1)
    if not exercises:
        return None
    exercise = exercises[0]
    return RecommendationResult(
        title=exercise.title,
        rationale=_RATIONALE[rationale_key],
        url=_build_url(exercise.slug),
    )


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def get_personalized_recommendation(
    db: AsyncSession, user_id: int
) -> RecommendationResult | None:
    today = datetime.now(tz=_VN_TZ).date()
    window_start = today - timedelta(days=13)  # two weeks, for the trend comparison

    mood_result = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == user_id, MoodEntry.date >= window_start)
        .order_by(MoodEntry.date.desc())
    )
    entries = list(mood_result.scalars().all())
    by_date = {e.date: e for e in entries}
    recent_count = sum(1 for e in entries if e.date >= today - timedelta(days=6))

    assessment_result = await db.execute(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    )
    latest_assessment = assessment_result.scalar_one_or_none()

    eligible = recent_count >= _MIN_RECENT_ENTRIES or latest_assessment is not None
    if not eligible:
        return None

    now = datetime.now(tz=timezone.utc)

    # 1. PHQ-9 Moderate/Severe taken within the last 30 days — highest precedence.
    # Must never fall through to a lower-precedence branch on failure: a lower
    # branch could pick an energizing exercise, violating the calming-only guarantee.
    if latest_assessment is not None and latest_assessment.severity in ("Moderate", "Severe"):
        taken_at = _aware_utc(latest_assessment.created_at)
        if now - taken_at <= timedelta(days=_PHQ9_RECENCY_DAYS):
            return _pick_calming_exercise()

    # 2. Mood-trend decline.
    current_avg = _avg_mood(by_date, end_offset=0, days=7, anchor=today)
    prev_avg = _avg_mood(by_date, end_offset=7, days=7, anchor=today)
    if _trend_declined(current_avg, prev_avg) and entries:
        result = _pick_by_mood(entries[0].mood, "trend_decline")
        if result is not None:
            return result

    # 3. PHQ-9 Mild.
    if latest_assessment is not None and latest_assessment.severity == "Mild":
        mood_value = entries[0].mood if entries else 3
        result = _pick_by_mood(mood_value, "phq9_mild")
        if result is not None:
            return result

    # 4. Fallback: most recent mood entry.
    if entries:
        result = _pick_by_mood(entries[0].mood, "fallback")
        if result is not None:
            return result

    return None
