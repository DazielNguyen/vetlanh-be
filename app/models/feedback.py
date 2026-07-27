from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(sa.String(20)), nullable=False)
    positive_comment: Mapped[str | None] = mapped_column(sa.String(1500), nullable=True)
    improvement_comment: Mapped[str] = mapped_column(sa.String(2000), nullable=False)
    allow_contact: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    source_page: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    app_version: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    # new | reviewing | planned | resolved | dismissed
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, server_default="new")
    # Admin-only note, never exposed to the submitting user.
    internal_note: Mapped[str | None] = mapped_column(sa.String(4000), nullable=True)


class FeedbackAuditLog(Base):
    __tablename__ = "feedback_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(
        sa.ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL (not CASCADE): the audit trail must survive the admin account being deleted.
    admin_user_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    old_status: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
