from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class TrustedContact(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def name_no_pipe(cls, v: str) -> str:
        if "|" in v:
            raise ValueError("Contact name must not contain '|'")
        return v


_SignItem = Annotated[str, Field(min_length=1, max_length=255)]


class SafetyPlanUpsert(BaseModel):
    warning_signs: list[_SignItem] = Field(default_factory=list, max_length=20)
    coping_activities: list[_SignItem] = Field(default_factory=list, max_length=20)
    trusted_contacts: list[TrustedContact] = Field(default_factory=list, max_length=10)
    reasons_to_live: str | None = Field(default=None, max_length=2000)


class SafetyPlanResponse(BaseModel):
    id: int
    warning_signs: list[str]
    coping_activities: list[str]
    trusted_contacts: list[TrustedContact]
    reasons_to_live: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}
