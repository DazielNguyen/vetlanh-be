from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CommunityMatchResponse(BaseModel):
    match_id: str
    partner_handle: str
    matched_at: datetime

    model_config = ConfigDict(alias_generator=lambda value: _to_camel(value), populate_by_name=True)


class CommunityStatusResponse(BaseModel):
    status: Literal["opted_out", "waiting", "matched"]
    match: CommunityMatchResponse | None = None


class CommunityMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content must not be blank")
        return value


class CommunityMessageResponse(BaseModel):
    id: str
    match_id: str
    content: str
    is_mine: bool
    created_at: datetime

    model_config = ConfigDict(alias_generator=lambda value: _to_camel(value), populate_by_name=True)


class CommunityReportCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CommunityReportResponse(BaseModel):
    id: str
    match_id: str
    reporter_handle: str
    reported_handle: str
    reason: str | None
    reported_at: datetime
    sla_deadline: datetime
    status: Literal["open", "resolved"]

    model_config = ConfigDict(alias_generator=lambda value: _to_camel(value), populate_by_name=True)


class CommunityFeaturedResponse(BaseModel):
    message: str
    author_display: str
    active_users_count: int
