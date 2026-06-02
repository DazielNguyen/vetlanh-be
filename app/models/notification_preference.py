"""User notification preferences for daily mood check-in reminders (US-031)."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class NotificationPreference(Base, TimestampMixin):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # HH:MM format in user's local time, e.g. "21:00"
    reminder_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="21:00")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Quiet hours — no notifications sent between quiet_start and quiet_end (HH:MM)
    quiet_start: Mapped[str] = mapped_column(String(5), nullable=False, server_default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), nullable=False, server_default="07:00")
    # Exercise reminder (US-032)
    exercise_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    exercise_reminder_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="08:00")

    user = relationship("User", back_populates="notification_preference")
