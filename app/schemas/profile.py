import zoneinfo
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    avatar_url: AnyHttpUrl | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            zoneinfo.ZoneInfo(v)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Unknown timezone: {v!r}. Use IANA format, e.g. 'Asia/Ho_Chi_Minh'")
        return v
