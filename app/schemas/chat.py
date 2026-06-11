from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: int
    title: str | None
    message_count: int
    last_message_preview: str | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    sentiment: Literal["positive", "neutral", "negative"] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class ExerciseStep(BaseModel):
    order: int
    instruction: str
    duration_seconds: int | None = None


class ExerciseCard(BaseModel):
    id: str
    title: str
    description: str
    steps: list[ExerciseStep]


class EmotionAnalysis(BaseModel):
    emotion: str
    emotion_confidence: float
    depression_risk: str           # none | mild | moderate | severe
    phq_estimate: float            # 0–27 PHQ-9 equivalent
    signals: list[str] = []
