from datetime import datetime

from pydantic import BaseModel, Field

# Placeholder hints shown in the frontend for each column
COLUMN_HINTS = {
    "situation": "Điều gì đã xảy ra? Khi nào, ở đâu, với ai?",
    "automatic_thought": "Suy nghĩ đầu tiên xuất hiện trong đầu bạn là gì?",
    "emotion": "Bạn cảm thấy gì? Mức độ mạnh từ 0–100?",
    "evidence": "Bằng chứng ủng hộ và phản bác suy nghĩ đó là gì?",
    "alternative_thought": "Một cách nhìn khác cân bằng hơn là gì?",
}


class ThoughtRecordCreate(BaseModel):
    situation: str = Field(min_length=1, max_length=2000)
    automatic_thought: str = Field(min_length=1, max_length=2000)
    emotion: str = Field(min_length=1, max_length=500)
    evidence: str | None = Field(default=None, max_length=2000)
    alternative_thought: str | None = Field(default=None, max_length=2000)


class ThoughtRecordUpdate(BaseModel):
    situation: str | None = Field(default=None, min_length=1, max_length=2000)
    automatic_thought: str | None = Field(default=None, min_length=1, max_length=2000)
    emotion: str | None = Field(default=None, min_length=1, max_length=500)
    evidence: str | None = Field(default=None, max_length=2000)
    alternative_thought: str | None = Field(default=None, max_length=2000)


class ThoughtRecordResponse(BaseModel):
    id: int
    situation: str
    automatic_thought: str
    emotion: str
    evidence: str | None
    alternative_thought: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ThoughtRecordHints(BaseModel):
    situation: str
    automatic_thought: str
    emotion: str
    evidence: str
    alternative_thought: str
