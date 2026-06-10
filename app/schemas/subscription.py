import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SubscriptionPendingRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None
    displayName: str | None
    plan: str | None
    duration: int | None
    transferDate: datetime | None
    note: str | None
    amount_vnd: int | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def amount(self) -> str:
        if self.amount_vnd is None:
            return "—"
        return f"{self.amount_vnd:,}đ"


class SubscriptionActiveRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None
    displayName: str | None
    plan: str | None
    grantedAt: datetime | None
    expiresAt: datetime | None


class SubscriptionGrantRequest(BaseModel):
    duration_months: int | None = Field(default=None, ge=1)


class PendingSubmitRequest(BaseModel):
    plan_name: str
    duration_months: int = Field(ge=1, le=24)
    amount_vnd: int = Field(ge=1)
    transfer_date: datetime
    transfer_note: str | None = None


class PendingSubmitResponse(BaseModel):
    id: uuid.UUID


class PaymentNotifyResponse(BaseModel):
    id: uuid.UUID
