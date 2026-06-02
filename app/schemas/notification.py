"""Schemas for US-031 — Notification preferences."""

import re

from pydantic import BaseModel, Field, field_validator

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_time(v: str) -> str:
    if not _TIME_RE.match(v):
        raise ValueError("Time must be HH:MM format")
    hh, mm = int(v[:2]), int(v[3:])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Invalid time value")
    return v


class NotificationPreferenceUpdate(BaseModel):
    reminder_time: str | None = Field(default=None)
    enabled: bool | None = Field(default=None)
    quiet_start: str | None = Field(default=None)
    quiet_end: str | None = Field(default=None)
    exercise_enabled: bool | None = Field(default=None)
    exercise_reminder_time: str | None = Field(default=None)

    @field_validator("reminder_time", "quiet_start", "quiet_end", "exercise_reminder_time", mode="before")
    @classmethod
    def validate_time_fields(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_time(v)


class NotificationPreferenceOut(BaseModel):
    model_config = {"from_attributes": True}

    reminder_time: str
    enabled: bool
    quiet_start: str
    quiet_end: str
    exercise_enabled: bool
    exercise_reminder_time: str


class ShouldNotifyResponse(BaseModel):
    should_notify: bool
    # Reason is informational for debugging (not shown in UI)
    reason: str
