from datetime import date

from pydantic import BaseModel

from app.schemas.exercise import ExerciseResponse
from app.schemas.mood import MoodEntryResponse


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


class DailyQuoteResponse(BaseModel):
    text: str
    author: str | None = None
