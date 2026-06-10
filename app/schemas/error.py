import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorReportRequest(BaseModel):
    error_type: str = Field(..., max_length=100)
    # route is optional: the FE auto-reporter may not have a route available
    # (e.g., errors thrown before navigation or when window.location is absent).
    route: str | None = Field(default=None, max_length=500)
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    description: str = Field(..., max_length=2000)


class ErrorReportResponse(BaseModel):
    id: uuid.UUID


class AdminErrorRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    type: str  # maps from error_type
    route: str | None
    severity: str
    status: str
    description: str | None
