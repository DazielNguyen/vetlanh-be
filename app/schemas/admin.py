from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    monthly_revenue_vnd: int
    unresolved_errors: int


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None
    displayName: str | None
    accountType: str | None
    subscriptionStatus: str  # "Pro" | "Expired" | "None"
    subscriptionExpiry: datetime | None
    joinDate: datetime
    lastActiveAt: datetime | None
    isVerified: bool
    isActive: bool


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    limit: int
