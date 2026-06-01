from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class JournalEntryCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: str = Field(default="", max_length=10000)


class JournalEntryUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: str | None = Field(None, max_length=10000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "JournalEntryUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one of title or content must be provided")
        return self


class JournalEntryResponse(BaseModel):
    id: int
    title: str | None
    content: str
    word_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
