import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    # Canonical active-subscription filter: status='active' AND expires_at > now().
    # Never trust status='active' alone — expired rows keep their status until
    # a background job runs (or we never run one). Use the conjunction everywhere.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="pending"
    )  # pending | active | rejected | expired
    plan_name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    duration_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    amount_vnd: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    transfer_date: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    transfer_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])
