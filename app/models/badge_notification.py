"""Track which badge milestones have been shown to the user (US-027)."""

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserBadgeNotification(Base, TimestampMixin):
    __tablename__ = "user_badge_notifications"
    __table_args__ = (UniqueConstraint("user_id", "milestone_days"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    milestone_days: Mapped[int] = mapped_column(Integer, nullable=False)

    user = relationship("User", back_populates="badge_notifications")
