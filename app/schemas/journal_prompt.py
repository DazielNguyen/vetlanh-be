"""Schemas for US-029 — Journal prompts."""

from typing import Literal

from pydantic import BaseModel

TopicLiteral = Literal["work_stress", "relationships", "self_compassion", "gratitude"]


class JournalPromptOut(BaseModel):
    id: int
    topic: str
    text: str


class DailyPromptResponse(BaseModel):
    prompt: JournalPromptOut
    # Topics available for filtering
    topics: list[str]
