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
