from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReflectionType(str, Enum):
    ALL = "all"
    JOURNAL = "journal"
    THOUGHT_RECORD = "thought_record"


class ReflectionItem(BaseModel):
    id: str
    resource_id: str
    type: ReflectionType
    title: str
    preview: str
    emotion: str | None = Field(default=None, exclude_if=lambda value: value is None)
    created_at: datetime
    updated_at: datetime


class ReflectionFeedResponse(BaseModel):
    items: list[ReflectionItem]
    next_cursor: str | None = None
