from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MoodEntryCreate(BaseModel):
    date: date
    mood: int = Field(..., ge=1, le=5)
    energy: Literal["low", "medium", "high"] | None = None
    factors: list[Annotated[str, Field(max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    note: str | None = Field(None, max_length=500)


class MoodEntryResponse(BaseModel):
    id: int
    date: date
    mood: int
    energy: Literal["low", "medium", "high"] | None
    factors: list[str]
    note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MoodTrendEntry(BaseModel):
    """One slot in the trend window. mood=None means no check-in that day."""

    date: date
    mood: int | None
    energy: Literal["low", "medium", "high"] | None
    factors: list[str]
    note: str | None


class MoodTrendResponse(BaseModel):
    period: Literal["week", "month"]
    start: date
    end: date
    entries: list[MoodTrendEntry]
    best_day: date | None
    worst_day: date | None
    average_mood: float | None


InsightType = Literal["overall_average", "day_of_week", "factor_correlation"]


class InsightItem(BaseModel):
    type: InsightType
    text: str
    # delta=None for overall_average (no comparison baseline); float for pattern-based insights
    delta: float | None = None


class InsightsResponse(BaseModel):
    total_entries: int
    has_enough_data: bool
    insights: list[InsightItem]


class HeatmapDay(BaseModel):
    date: date
    mood_score: int = Field(..., ge=1, le=5)


class HeatmapResponse(BaseModel):
    year: int
    month: int
    days: list[HeatmapDay]
