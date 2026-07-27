from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "interface",
    "performance",
    "journal",
    "assessment",
    "exercises",
    "library",
    "audio",
    "assistant",
    "settings",
    "safety",
    "other",
]
Status = Literal["new", "reviewing", "planned", "resolved", "dismissed"]
SubscriptionStatus = Literal["none", "pro", "expired"]

FEEDBACK_ID_PREFIX = "fdb_"


def format_feedback_id(raw_id: int) -> str:
    return f"{FEEDBACK_ID_PREFIX}{raw_id}"


def parse_feedback_id(formatted_id: str) -> int | None:
    """Return the numeric id, or None if formatted_id isn't a valid feedback id."""
    if not formatted_id.startswith(FEEDBACK_ID_PREFIX):
        return None
    try:
        return int(formatted_id[len(FEEDBACK_ID_PREFIX) :])
    except ValueError:
        return None


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    categories: list[Category] = Field(min_length=1, max_length=5)
    positive_comment: str | None = Field(default=None, max_length=1500)
    improvement_comment: str = Field(min_length=5, max_length=2000)
    allow_contact: bool = False
    source_page: str | None = Field(default=None, max_length=500)
    app_version: str | None = Field(default=None, max_length=50)

    @field_validator("categories")
    @classmethod
    def _unique_categories(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("categories must not contain duplicates")
        return value

    @field_validator("source_page")
    @classmethod
    def _relative_path_only(cls, value: str | None) -> str | None:
        # Must store a bare path/query, never a full URL — a full URL could carry
        # an auth token in its query string (session links, magic links, etc).
        if value is None:
            return value
        # "//host/path" is protocol-relative — browsers resolve it as an absolute
        # URL to an external host, same risk as a full "https://" URL.
        if "://" in value or value.startswith("//") or not value.startswith("/"):
            raise ValueError("source_page must be a relative path (e.g. /services/settings)")
        return value


class FeedbackResponse(BaseModel):
    id: str
    rating: int
    categories: list[str]
    positive_comment: str | None
    improvement_comment: str
    allow_contact: bool
    source_page: str | None
    app_version: str | None
    status: str
    created_at: datetime


class FeedbackUserSummary(BaseModel):
    id: int
    display_name: str | None
    email: str | None
    subscription_status: SubscriptionStatus


class AdminFeedbackRow(BaseModel):
    id: str
    rating: int
    categories: list[str]
    positive_comment: str | None
    improvement_comment: str
    allow_contact: bool
    source_page: str | None
    app_version: str | None
    status: str
    internal_note: str | None
    created_at: datetime
    user: FeedbackUserSummary


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackRow]
    page: int
    page_size: int
    total: int


class CategoryCount(BaseModel):
    category: str
    count: int


class AdminFeedbackStatsResponse(BaseModel):
    total: int
    average_rating: float
    unresolved: int
    last_30_days: int
    rating_distribution: dict[str, int]
    top_categories: list[CategoryCount]


class AdminFeedbackUpdate(BaseModel):
    status: Status | None = None
    internal_note: str | None = Field(default=None, max_length=4000)
