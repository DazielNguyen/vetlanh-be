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
    status: Literal["processing", "ready", "unavailable"] = "unavailable"
    analysis_for_entry_id: str | None = None
    total_entries: int
    has_enough_data: bool
    generated_by: Literal["rules", "agent"] = "rules"
    generated_at: datetime | None = None
    reflection: "MoodReflection | None" = None
    next_action: "MoodNextAction | None" = None
    follow_up_prompt: str | None = None
    insights: list[InsightItem]


class MoodReflection(BaseModel):
    acknowledgement: str = Field(min_length=1, max_length=140)
    observation: str = Field(min_length=1, max_length=260)
    evidence: str | None = Field(default=None, max_length=100)
    confidence: Literal["low", "medium", "high"]


class MoodNextAction(BaseModel):
    type: Literal["exercise", "journal", "chat", "rest"]
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=120)
    url: str = Field(pattern=r"^/[^/].*")


class AgentMoodOutput(BaseModel):
    """Strict model-output envelope; confidence/evidence are supplied by the backend."""

    acknowledgement: str = Field(min_length=1, max_length=140)
    observation: str = Field(min_length=1, max_length=260)
    action_title: str | None = Field(default=None, max_length=80)
    action_description: str | None = Field(default=None, max_length=120)
    follow_up_prompt: str | None = Field(default=None, max_length=260)

    model_config = {"extra": "forbid"}


class HeatmapDay(BaseModel):
    date: date
    mood_score: int = Field(..., ge=1, le=5)


class HeatmapResponse(BaseModel):
    year: int
    month: int
    days: list[HeatmapDay]


class MoodSummaryEntry(BaseModel):
    date: date
    sentiment_score: int = Field(..., ge=1, le=5)

    model_config = {"from_attributes": True}


class MoodFactor(BaseModel):
    key: str
    label: str
