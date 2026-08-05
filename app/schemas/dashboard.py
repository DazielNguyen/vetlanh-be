from datetime import date
from enum import Enum

from pydantic import BaseModel

from app.schemas.exercise import ExerciseResponse
from app.schemas.mood import MoodEntryResponse


class StressLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class MoodSparkline(BaseModel):
    date: date
    mood: int | None  # None = no check-in that day


class DashboardResponse(BaseModel):
    greeting: str  # e.g. "Buổi sáng tốt lành, Minh!"
    checked_in_today: bool
    today_mood: MoodEntryResponse | None  # None when not checked in
    streak_days: int
    mood_sparkline: list[MoodSparkline]  # last 7 days, oldest → newest
    recommended_exercises: list[ExerciseResponse]  # top 3 based on latest mood
    # Stress level derived from average mood this week; None when no data
    stress_level: StressLevel | None = None
    # Week-over-week mood change, e.g. "tốt hơn 12%" or "xấu hơn 8%" or None
    stress_trend_text: str | None = None


class DailyQuoteResponse(BaseModel):
    text: str
    author: str | None = None


class PersonalizedRecommendationResponse(BaseModel):
    title: str
    rationale: str
    url: str
