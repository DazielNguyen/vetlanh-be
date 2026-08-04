import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EventName = Literal[
    "chat_message_sent",
    "mood_checkin_logged",
    "exercise_played",
    "sound_played",
    "community_action",
    "page_view",
]

# "Active" for MAU purposes — explicitly excludes page_view (viewing a page isn't "using" the app).
ACTIVE_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "chat_message_sent",
        "mood_checkin_logged",
        "exercise_played",
        "sound_played",
        "community_action",
    }
)

_METADATA_MAX_BYTES = 4096


class EventCreate(BaseModel):
    event_name: EventName
    user_id: str | None = Field(default=None, max_length=255)
    metadata: dict = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_size_limit(cls, value: dict) -> dict:
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > _METADATA_MAX_BYTES:
            raise ValueError(f"metadata exceeds {_METADATA_MAX_BYTES} bytes")
        return value


class ConversionRateResponse(BaseModel):
    joined_count: int
    converted_count: int
    conversion_rate: float


class FeatureUsageRow(BaseModel):
    event_name: str
    count: int


class MauRow(BaseModel):
    month: str
    active_users: int


class PageViewRow(BaseModel):
    date: str
    count: int
