from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    # nullable=True: username-only users have no password
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # "email" for email+password registration, "username" for username-only users
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, server_default="email")

    # Email verification — False until user clicks the link in their inbox
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Single-use token sent in the verification email; cleared after use
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    goals: Mapped[list] = mapped_column(ARRAY(String(50)), server_default="{}", nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True, server_default="Asia/Ho_Chi_Minh")
    # "email" | "username" — how the user registered; drives admin panel badge
    account_type: Mapped[str | None] = mapped_column(String(20), nullable=True, server_default="email")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pending_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_change_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    email_change_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessments = relationship("Assessment", back_populates="user", order_by="Assessment.created_at")
    conversations = relationship("Conversation", back_populates="user", order_by="Conversation.created_at")
    mood_entries = relationship("MoodEntry", back_populates="user", order_by="MoodEntry.date")
    journal_entries = relationship("JournalEntry", back_populates="user", order_by="JournalEntry.created_at")
    exercise_logs = relationship("UserExerciseLog", back_populates="user", order_by="UserExerciseLog.created_at")
    safety_plan = relationship("UserSafetyPlan", back_populates="user", uselist=False)
    thought_records = relationship("ThoughtRecord", back_populates="user", order_by="ThoughtRecord.created_at")
    badge_notifications = relationship("UserBadgeNotification", back_populates="user")
    notification_preference = relationship("NotificationPreference", back_populates="user", uselist=False)
